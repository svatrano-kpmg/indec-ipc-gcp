#!/binbin/bash
source scripts/_env.sh
set -euo pipefail

echo "--- Desplegando CF Cuadro Tarifario: ${CF_CUADRO} ---"

gcloud functions deploy ${CF_CUADRO} \
    --gen2 \
    --region=${REGION} \
    --runtime=python311 \
    --source=cf-cuadro-tarifario/ \
    --no-allow-unauthenticated \
    --trigger-topic=${TOPIC_GOLD} \
    --service-account=${SA_COMPUTE} \
    --set-env-vars="BQ_PROJECT_ID=${PROJECT_LAKE},PROJECT_ID=${PROJECT_PROCESS},BQ_DATASET=${BQ_DS_GOLD},BQ_LOCATION=${REGION},PUB_SUB_TOPIC_OUT=${TOPIC_END}" \
    --entry-point=check_and_run_cuadro_tarifario \
    --retry 

echo "--- Despliegue de CF Cuadro Tarifario completado ---"