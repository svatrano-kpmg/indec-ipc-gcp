#!/bin/bash
source scripts/_env.sh
set -euo pipefail

# 1. Crear Bucket de Staging para Dataproc (si no existe)
echo "--- Verificando Bucket para Scripts Dataproc: gs://${GCS_DATAPROC_BUCKET} ---"
if ! gcloud storage buckets describe gs://${GCS_DATAPROC_BUCKET} &>/dev/null; then
    echo "Creando bucket gs://${GCS_DATAPROC_BUCKET}..."
    gcloud storage buckets create gs://${GCS_DATAPROC_BUCKET} --location=${REGION}
else
    echo "El bucket ya existe."
fi

# 2. Subir el script Worker y requirements a GCS
echo "--- Subiendo scripts de Dataproc a GCS ---"
# Asumimos que la carpeta local se llama dp-downloader
gsutil cp dp-downloader/download_script.py gs://${GCS_DATAPROC_BUCKET}/scripts/calculotarifario/download_script.py
gsutil cp dp-downloader/requirements.txt gs://${GCS_DATAPROC_BUCKET}/scripts/calculotarifario/requirements.txt

echo "Scripts subidos a: gs://${GCS_DATAPROC_BUCKET}/scripts/"

# 3. Desplegar la Cloud Function Launcher
echo "--- Desplegando CF Launcher: ${CF_DOWNLOADER_LAUNCHER} ---"

# Nota: Se inyectan las URIs de los scripts como variables de entorno
gcloud functions deploy ${CF_DOWNLOADER_LAUNCHER} \
    --gen2 \
    --region=${REGION} \
    --runtime=python311 \
    --source=cf-indec-downloader-dataproc/ \
    --entry-point=launch_dataproc_job \
    --service-account=${SA_RUN} \
    --trigger-http \
    --no-allow-unauthenticated \
    --set-env-vars="PROJECT_ID=${PROJECT_ID},REGION=${REGION},SCRIPT_URI=gs://${GCS_DATAPROC_BUCKET}/scripts/calculotarifario/download_script.py,REQS_URI=gs://${GCS_DATAPROC_BUCKET}/scripts/calculotarifario/requirements.txt,PUB_SUB_TOPIC=${TOPIC_RAW},GCS_BUCKET=${GCS_RAW_BUCKET}"

# 4. Dar permisos al Scheduler para invocar esta función
echo "--- Asignando rol invoker a la Service Account del Scheduler ---"
gcloud functions add-iam-policy-binding ${CF_DOWNLOADER_LAUNCHER} \
    --region=${REGION} \
    --member="serviceAccount:${SA_SCHEDULER}" \
    --role="roles/cloudfunctions.invoker"

# En Gen2, a veces también se requiere permiso sobre el servicio Run subyacente
gcloud run services add-iam-policy-binding ${CF_DOWNLOADER_LAUNCHER} \
    --region=${REGION} \
    --member="serviceAccount:${SA_SCHEDULER}" \
    --role="roles/run.invoker"

echo "--- Despliegue de Launcher y Scripts completado ---"