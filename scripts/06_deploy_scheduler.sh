#!/binbin/bash
source scripts/_env.sh
set -euo pipefail

echo "--- Obteniendo URL del Cloud Run Downloader ---"
CR_DOWNLOADER_URL=$(gcloud run services describe ${CR_DOWNLOADER} --platform=managed --region=${REGION} --format='value(status.url)')

if [ -z "${CR_DOWNLOADER_URL}" ]; then
  echo "Error: No se pudo obtener la URL de ${CR_DOWNLOADER}"
  exit 1
fi

echo "URL de invocación: ${CR_DOWNLOADER_URL}"

echo "--- Creando Job de Scheduler (IPC) ---"
gcloud scheduler jobs create http job-indec-ipc \
  --schedule="5 10 1 * *" \
  --time-zone="America/Argentina/Buenos_Aires" \
  --uri="${CR_DOWNLOADER_URL}" \
  --http-method="POST" \
  --message-body='{
      "codigo_descarga": "IPC",
      "url_descarga": "https://www.indec.gob.ar/ftp/cuadros/economia/serie_ipc_divisiones.csv",
      "nombre_carpeta_gcs": "ipc",
      "nombre_procedure_gold": "ds_datos_tableros.sp_merge_lkp_indices_ajuste"
    }' \
  --oidc-service-account-email="${SA_SCHEDULER}" || echo "Job job-indec-ipc ya existe."

echo "--- Creando Job de Scheduler (IPIM) ---"
gcloud scheduler jobs create http job-indec-ipim \
  --schedule="5 10 1 * *" \
  --time-zone="America/Argentina/Buenos_Aires" \
  --uri="${CR_DOWNLOADER_URL}" \
  --http-method="POST" \
  --message-body='{
      "codigo_descarga": "IPIM",
      "url_descarga": "https://www.indec.gob.ar/ftp/cuadros/economia/indice_ipim.csv",
      "nombre_carpeta_gcs": "ipim",
      "nombre_procedure_gold": "ds_datos_tableros.sp_merge_lkp_indices_ajuste"
    }' \
  --oidc-service-account-email="${SA_SCHEDULER}" || echo "Job job-indec-ipim ya existe."

echo "--- Creación de Schedulers completada ---"