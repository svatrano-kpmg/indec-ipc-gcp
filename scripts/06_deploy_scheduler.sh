#!/binbin/bash
source ./_env.sh
set -euo pipefail

# Asegurarse de que las variables necesarias existan
if [ -z "${CF_DOWNLOADER_LAUNCHER}" ] || [ -z "${DATAPROC_CLUSTER}" ]; then
    echo "Error: Variables CF_DOWNLOADER_LAUNCHER o DATAPROC_CLUSTER no definidas en _env.sh"
    exit 1
fi

echo "--- Obteniendo URL de la Cloud Function Launcher ---"
# Para Cloud Functions Gen 2, la URL está en serviceConfig.uri
LAUNCHER_URL=$(gcloud functions describe ${CF_DOWNLOADER_LAUNCHER} \
    --gen2 \
    --project=${PROJECT_INTAKE} \
    --region=${REGION} \
    --format='value(serviceConfig.uri)')

if [ -z "${LAUNCHER_URL}" ]; then
  echo "Error: No se pudo obtener la URL de la función ${CF_DOWNLOADER_LAUNCHER}. ¿Está desplegada?"
  exit 1
fi

echo "URL de invocación detectada: ${LAUNCHER_URL}"

echo "--- Creando Job de Scheduler (IPC) ---"
# Usamos || true para que no falle si el job ya existe (intentará actualizarlo o fallará y seguiremos)
# Pero 'jobs create' falla si existe. Mejor borrarlos primero o usar 'jobs update' si quisieras lógica idempotente compleja.
# Aquí asumimos limpieza previa o borrado simple:
gcloud scheduler jobs delete job-indec-ipc --location=${REGION} --project=${PROJECT_INTAKE} --quiet || echo "Job IPC no existía"

gcloud scheduler jobs create http job-indec-ipc \
    --location=${REGION} \
    --project=${PROJECT_INTAKE} \
    --schedule="5 10 1 * *" \
    --uri="${LAUNCHER_URL}" \
    --http-method=POST \
    --time-zone "America/Argentina/Buenos_Aires" \
    --oidc-service-account-email=${SA_SCHEDULER} \
    --headers="Content-Type=application/json" \
    --message-body='{
        "codigo_descarga": "IPC",
        "url_descarga": "https://www.indec.gob.ar/ftp/cuadros/economia/serie_ipc_divisiones.csv",
        "nombre_carpeta_gcs": "ipc",
        "nombre_procedure_gold": "ds_datos_tableros.sp_merge_lkp_indices_ajuste",
        "cluster_name": "'"${DATAPROC_CLUSTER}"'"
    }'

echo "--- Creando Job de Scheduler (IPIM) ---"
gcloud scheduler jobs delete job-indec-ipim --location=${REGION} --quiet || echo "Job IPIM no existía"

gcloud scheduler jobs create http job-indec-ipim \
    --location=${REGION} \
    --project=${PROJECT_INTAKE} \
    --schedule="5 10 1 * *" \
    --uri="${LAUNCHER_URL}" \
    --http-method=POST \
    --time-zone "America/Argentina/Buenos_Aires" \
    --oidc-service-account-email=${SA_SCHEDULER} \
    --headers="Content-Type=application/json" \
    --message-body='{
        "codigo_descarga": "IPIM",
        "url_descarga": "https://www.indec.gob.ar/ftp/cuadros/economia/indice_ipim.csv",
        "nombre_carpeta_gcs": "ipim",
        "nombre_procedure_gold": "ds_datos_tableros.sp_merge_lkp_indices_ajuste",
        "cluster_name": "'"${DATAPROC_CLUSTER}"'"
    }'

echo "--- Despliegue de Scheduler completado ---"




echo "--- Creando Job de Scheduler para cloud run(IPC) ---"
# URL del servicio (si ya está desplegado)
export SERVICE_URL=$(gcloud run services describe $CR_DOWNLOADER \
  --region $REGION --project $PROJECT_INTAKE \
  --format='value(status.url)')

# Lunes 10:05 AM (zona Argentina)
export SCHEDULE="5 10 * * 1"

# Payload con los TAGS adicionales
read -r -d '' PAYLOAD <<'JSON'
{
  "url_descarga": "https://www.indec.gob.ar/ftp/cuadros/economia/serie_ipc_divisiones.csv",
  "GCS_BUCKET": "raw-zone-lakehouse/indec/ipc/",
  "project_lake": "prj-data-lakehouse-dev",
  "codigo_descarga": "IPC",
  "nombre_procedure_gold": "DS_ASUNTOS_REGULATORIOS_SANDBOX.sp_merge_lkp_indices_ajuste"
}
JSON

gcloud scheduler jobs delete indec-ipc-cr-downloader --location=${REGION} --quiet || echo "Job IPC no existía"

gcloud scheduler jobs create http indec-ipc-cr-downloader \
    --location=${REGION} \
    --project=${PROJECT_INTAKE} \
    --schedule="${SCHEDULE}" \
    --uri="${SERVICE_URL}" \
    --time-zone "America/Argentina/Buenos_Aires" \
    --http-method=POST \
    --oidc-service-account-email=${SA_SCHEDULER} \
    --headers="Content-Type=application/json" \
    --message-body="$PAYLOAD"





echo "--- Creando Job de Scheduler para cloud run(IPIM) ---"
# URL del servicio (si ya está desplegado)
export SERVICE_URL=$(gcloud run services describe $CR_DOWNLOADER \
  --region $REGION --project $PROJECT_INTAKE \
  --format='value(status.url)')

# Lunes 10:05 AM (zona Argentina)
export SCHEDULE="10 10 * * 1"

# Payload con los TAGS adicionales
read -r -d '' PAYLOAD <<'JSON'
{
"codigo_descarga": "IPIM",
"url_descarga": "https://www.indec.gob.ar/ftp/cuadros/economia/indice_ipim.csv",
"GCS_BUCKET": "raw-zone-lakehouse/indec/ipim/",
"project_lake": "prj-data-lakehouse-dev",
"nombre_procedure_gold": "DS_ASUNTOS_REGULATORIOS_SANDBOX.sp_merge_lkp_indices_ajuste"
}
JSON

gcloud scheduler jobs delete indec-ipim-cr-downloader --location=${REGION} --quiet || echo "Job IPC no existía"

gcloud scheduler jobs create http indec-ipim-cr-downloader \
    --location=${REGION} \
    --project=${PROJECT_INTAKE} \
    --schedule="${SCHEDULE}" \
    --uri="${SERVICE_URL}" \
    --time-zone "America/Argentina/Buenos_Aires" \
    --http-method=POST \
    --oidc-service-account-email=${SA_SCHEDULER} \
    --headers="Content-Type=application/json" \
    --message-body="$PAYLOAD"
