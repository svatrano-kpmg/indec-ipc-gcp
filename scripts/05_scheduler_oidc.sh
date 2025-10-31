#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/_env.sh"

echo ">> Crear SA del Scheduler (si no existe)..."
gcloud iam service-accounts describe "${SCHEDULER_SA}@${PROJECT}.iam.gserviceaccount.com" >/dev/null 2>&1 || \
 gcloud iam service-accounts create "${SCHEDULER_SA}" \
  --display-name "Scheduler SA for INDEC IPC job"

echo ">> Conceder roles/run.invoker a la SA sobre el servicio de Run..."
gcloud run services add-iam-policy-binding "${RUN_SERVICE}" \
  --region "${REGION}" \
  --member="serviceAccount:${SCHEDULER_SA}@${PROJECT}.iam.gserviceaccount.com" \
  --role="roles/run.invoker"

RUN_URL=$(gcloud run services describe "${RUN_SERVICE}" --region "${REGION}" --format='value(status.url)')

echo ">> Crear Cloud Scheduler job con OIDC..."
gcloud scheduler jobs delete "${SCHEDULER_JOB}" --location="${SCHEDULER_LOCATION}" --quiet || true

gcloud scheduler jobs create http "${SCHEDULER_JOB}" \
  --location="${SCHEDULER_LOCATION}" \
  --schedule="0 8 15 * *" \
  --time-zone="${TIME_ZONE}" \
  --uri="${RUN_URL}/run" \
  --http-method=GET \
  --oidc-service-account-email="${SCHEDULER_SA}@${PROJECT}.iam.gserviceaccount.com"

echo ">> Probar ejecución del Scheduler..."
gcloud scheduler jobs run "${SCHEDULER_JOB}" --location="${SCHEDULER_LOCATION}"

echo ">> Scheduler OK."
