#!/binbin/bash
source scripts/_env.sh
set -euo pipefail

echo "--- Habilitando APIs ---"
gcloud services enable run.googleapis.com \
  pubsub.googleapis.com \
  bigquery.googleapis.com \
  cloudscheduler.googleapis.com \
  cloudbuild.googleapis.com \
  eventarc.googleapis.com \
  iam.googleapis.com

echo "--- Creando SAs (si no existen) ---"
gcloud iam service-accounts create sa-scheduler-indec \
  --display-name="SA for INDEC Scheduler" || echo "SA sa-scheduler-indec ya existe."

echo "--- Creando Bucket (si no existe) ---"
gcloud storage buckets create gs://${GCS_RAW_BUCKET} --location=${REGION} || echo "Bucket gs://${GCS_RAW_BUCKET} ya existe."

echo "--- Creando Topics Pub/Sub ---"
gcloud pubsub topics create ${TOPIC_RAW} || echo "Topic ${TOPIC_RAW} ya existe."
gcloud pubsub topics create ${TOPIC_CURATED} || echo "Topic ${TOPIC_CURATED} ya existe."
gcloud pubsub topics create ${TOPIC_GOLD} || echo "Topic ${TOPIC_GOLD} ya existe."
gcloud pubsub topics create ${TOPIC_END} || echo "Topic ${TOPIC_END} ya existe."

echo "--- Creando Topics DLQ ---"
gcloud pubsub topics create ${DLQ_RAW} || echo "Topic ${DLQ_RAW} ya existe."
gcloud pubsub topics create ${DLQ_CURATED} || echo "Topic ${DLQ_CURATED} ya existe."
gcloud pubsub topics create ${DLQ_GOLD} || echo "Topic ${DLQ_GOLD} ya existe."

echo "--- Asignando permisos a SA Compute (para que las CF/Run funcionen) ---"
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${SA_COMPUTE}" \
  --role="roles/pubsub.publisher"
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${SA_COMPUTE}" \
  --role="roles/bigquery.dataEditor"
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${SA_COMPUTE}" \
  --role="roles/bigquery.jobUser"
gcloud storage buckets add-iam-policy-binding gs://${GCS_RAW_BUCKET} \
  --member="serviceAccount:${SA_COMPUTE}" \
  --role="roles/storage.objectCreator"
gcloud storage buckets add-iam-policy-binding gs://${GCS_RAW_BUCKET} \
  --member="serviceAccount:${SA_COMPUTE}" \
  --role="roles/storage.objectViewer"

echo "--- Bootstrap completado ---"