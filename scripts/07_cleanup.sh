#!/binbin/bash
source scripts/_env.sh
set -euo pipefail

echo "--- Eliminando Schedulers ---"
gcloud scheduler jobs delete job-indec-ipc --quiet || true
gcloud scheduler jobs delete job-indec-ipim --quiet || true

echo "--- Eliminando Cloud Functions / Run ---"
gcloud run services delete ${CR_DOWNLOADER} --region=${REGION} --platform=managed --quiet || true
gcloud run services delete ${CF_SILVER} --region=${REGION} --platform=managed --quiet || true
gcloud run services delete ${CF_GOLD} --region=${REGION} --platform=managed --quiet || true
gcloud run services delete ${CF_CUADRO} --region=${REGION} --platform=managed --quiet || true

echo "--- Eliminando Topics Pub/Sub (incl. DLQs) ---"
gcloud pubsub topics delete ${TOPIC_RAW} --quiet || true
gcloud pubsub topics delete ${TOPIC_CURATED} --quiet || true
gcloud pubsub topics delete ${TOPIC_GOLD} --quiet || true
gcloud pubsub topics delete ${TOPIC_END} --quiet || true
gcloud pubsub topics delete ${DLQ_RAW} --quiet || true
gcloud pubsub topics delete ${DLQ_CURATED} --quiet || true
gcloud pubsub topics delete ${DLQ_GOLD} --quiet || true

echo "--- Eliminando BQ Datasets (CON DATOS) ---"
bq rm -r -f ${PROJECT_ID}:${BQ_DS_SILVER} || true
bq rm -r -f ${PROJECT_ID}:${BQ_DS_GOLD} || true

echo "--- Eliminando GCS Bucket (CON DATOS) ---"
gcloud storage rm -r gs://${GCS_RAW_BUCKET} || true

echo "--- Eliminando SA Scheduler ---"
gcloud iam service-accounts delete ${SA_SCHEDULER} --quiet || true

echo "--- Limpieza completada ---"