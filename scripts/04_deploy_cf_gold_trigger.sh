#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/_env.sh"

echo ">> Deploy CF Gold Trigger (Gen2)..."
gcloud functions deploy "${CF_GOLD_TRIGGER}" \
  --gen2 \
  --region "${REGION}" \
  --runtime python311 \
  --entry-point pubsub_handler \
  --trigger-topic "${TOPIC_CURATED}" \
  --set-env-vars PROJECT_ID="${PROJECT}",PROC_FQN="${SP_FQN}" \
  --source ./cf-gold-trigger

echo ">> CF Gold Trigger OK."
