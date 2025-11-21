#!/binbin/bash
source scripts/_env.sh
set -euo pipefail

echo "--- Desplegando CF Gold: ${CF_GOLD} ---"
# gcloud run deploy ${CF_GOLD} \
#   --source=cf-gold-trigger/ \
#   --platform=managed \
#   --region=${REGION} \
#   --no-allow-unauthenticated \
#   --entry-point=call_gold_sp \
#   --service-account=${SA_COMPUTE} \
#   --set-env-vars="PROJECT_ID=${PROJECT_ID},BQ_LOCATION=${REGION},PUB SUB_TOPIC_OUT=${TOPIC_GOLD}" \
#   --trigger-topic=${TOPIC_CURATED} \
#   --trigger-retry \
#   --trigger-dead-letter-topic=${DLQ_CURATED}

gcloud functions deploy ${CF_GOLD} \
    --gen2 \
    --region=${REGION} \
    --runtime=python311 \
    --source=cf-gold-trigger/ \
    --no-allow-unauthenticated \
    --trigger-topic=${TOPIC_CURATED} \
    --service-account=${SA_COMPUTE} \
    --set-env-vars="PROJECT_ID=${PROJECT_ID},BQ_LOCATION=${REGION},PUB_SUB_TOPIC_OUT=${TOPIC_GOLD}" \
    --entry-point=call_gold_sp \
    --retry 

echo "--- Despliegue de CF Gold completado ---"