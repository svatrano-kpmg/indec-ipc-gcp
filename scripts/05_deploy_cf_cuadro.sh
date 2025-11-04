#!/binbin/bash
source scripts/_env.sh
set -euo pipefail

echo "--- Desplegando CF Cuadro Tarifario: ${CF_CUADRO} ---"
gcloud run deploy ${CF_CUADRO} \
  --source=cf-cuadro-tarifario/ \
  --platform=managed \
  --region=${REGION} \
  --no-allow-unauthenticated \
  --entry-point=check_and_run_cuadro_tarifario \
  --service-account=${SA_COMPUTE} \
  --set-env-vars="PROJECT_ID=${PROJECT_ID},BQ_DATASET=${BQ_DS_GOLD},BQ_LOCATION=${REGION},PUB SUB_TOPIC_OUT=${TOPIC_END}" \
  --trigger-topic=${TOPIC_GOLD} \
  --trigger-retry \
  --trigger-dead-letter-topic=${DLQ_GOLD}

echo "--- Despliegue de CF Cuadro Tarifario completado ---"