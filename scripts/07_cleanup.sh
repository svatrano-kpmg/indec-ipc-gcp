#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/_env.sh"

echo ">> Pausando/eliminando Scheduler..."
gcloud scheduler jobs delete "${SCHEDULER_JOB}" --location="${SCHEDULER_LOCATION}" --quiet || true

echo ">> Eliminando CFs..."
gcloud functions delete "${CF_GOLD_TRIGGER}" --region "${REGION}" --quiet || true
gcloud functions delete "${CF_SILVER}" --region "${REGION}" --quiet || true

echo ">> Eliminando servicio Cloud Run..."
gcloud run services delete "${RUN_SERVICE}" --region "${REGION}" --quiet || true

echo ">> (Opcional) borrar topics y bucket (cuidado: datos!)"
# gcloud pubsub topics delete "${TOPIC_CURATED}" --quiet || true
# gcloud pubsub topics delete "${TOPIC_RAW}" --quiet || true
# gsutil rm -r "gs://${RAW_BUCKET}" || true

echo ">> Cleanup OK."
