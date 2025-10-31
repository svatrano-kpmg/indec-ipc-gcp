#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/_env.sh"

echo ">> Build imagen Cloud Run..."
gcloud builds submit ./cloud-run-downloader --tag "${RUN_IMAGE}"

echo ">> Deploy servicio Cloud Run (privado, sin --allow-unauthenticated)..."
gcloud run deploy "${RUN_SERVICE}" \
  --image "${RUN_IMAGE}" \
  --region "${REGION}" \
  --platform managed \
  --set-env-vars PROJECT_ID="${PROJECT}",RAW_BUCKET="${RAW_BUCKET}",TOPIC_RAW_DONE="${TOPIC_RAW}"

echo ">> Run URL:"
gcloud run services describe "${RUN_SERVICE}" --region "${REGION}" --format='value(status.url)'

echo ">> Removiendo binding público si existía..."
gcloud run services remove-iam-policy-binding "${RUN_SERVICE}" \
  --region "${REGION}" \
  --member="allUsers" \
  --role="roles/run.invoker" || true

echo ">> Cloud Run OK."
