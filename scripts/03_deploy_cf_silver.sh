#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/_env.sh"

echo ">> Deploy CF Silver (Gen2)..."
gcloud functions deploy "${CF_SILVER}" \
  --gen2 \
  --region "${REGION}" \
  --runtime python311 \
  --entry-point pubsub_handler \
  --trigger-topic "${TOPIC_RAW}" \
  --set-env-vars PROJECT_ID="${PROJECT}",SILVER_DATASET="${SILVER_DATASET}",SILVER_TABLE="${SILVER_TABLE}",TOPIC_CURATED_DONE="${TOPIC_CURATED}" \
  --source ./cf-silver

echo ">> CF Silver OK."
