#!/binbin/bash
source scripts/_env.sh
set -euo pipefail

echo "--- Desplegando CF Silver: ${CF_SILVER} ---"
# gcloud run deploy ${CF_SILVER} \
#   --source=cf-silver-transformer/ \
#   --platform=managed \
#   --region=${REGION} \
#   --no-allow-unauthenticated \
#   --entry-point=process_raw_to_silver \
#   --service-account=${SA_COMPUTE} \
#   --set-env-vars="PROJECT_ID=${PROJECT_ID},BQ_DATASET=${BQ_DS_SILVER},BQ_TABLE=${BQ_TBL_SILVER},PUB SUB_TOPIC_OUT=${TOPIC_CURATED},FILTER_IPC_DESC=NIVEL GENERAL,FILTER_IPC_REGION=Nacional,FILTER_IPIM_APERTURA=ng_nivel_general" \
#   --trigger-topic=${TOPIC_RAW} \
#   --trigger-retry \
#   --trigger-dead-letter-topic=${DLQ_RAW}

gcloud functions deploy ${CF_SILVER} \
    --gen2 \
    --region=${REGION} \
    --runtime=python311 \
    --source=cf-silver-transformer/ \
    --entry-point=${ENTRY_POINT} \
    --service-account=${SA_COMPUTE} \
    --trigger-topic=${TOPIC_RAW} \
    --set-env-vars="PROJECT_ID=${PROJECT_ID},BQ_DATASET=${BQ_DS_SILVER},BQ_TABLE=${BQ_TBL_SILVER},PUB_SUB_TOPIC_OUT=${TOPIC_CURATED},FILTER_IPC_DESC='${FILTER_IPC_DESC}',FILTER_IPC_REGION='${FILTER_IPC_REGION}',FILTER_IPIM_APERTURA='${FILTER_IPIM_APERTURA}'" \
    --memory=512MiB \
    --retry 

echo "--- Despliegue de CF Silver completado ---"