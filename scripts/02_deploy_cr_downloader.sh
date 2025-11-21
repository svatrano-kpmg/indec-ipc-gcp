#!/binbin/bash
source scripts/_env.sh
set -euo pipefail

echo "--- Desplegando Cloud Run (Downloader): ${CR_DOWNLOADER} ---"
gcloud run deploy ${CR_DOWNLOADER} \
  --source=cr-downloader/ \
  --platform=managed \
  --region=${REGION} \
  --no-allow-unauthenticated \
  --service-account=${SA_COMPUTE} \
  --set-env-vars="PROJECT_ID=${PROJECT_ID},GCS_BUCKET=${GCS_RAW_BUCKET},PUB SUB_TOPIC=${TOPIC_RAW}"
  
echo "--- Dando permisos al Scheduler (OIDC) para invocar ${CR_DOWNLOADER} ---"
# no lo pude ejecutar por problemas con las credenciales del gcloud 
gcloud run services add-iam-policy-binding ${CR_DOWNLOADER} \
  --region=${REGION} \
  --platform=managed \
  --member="serviceAccount:${SA_SCHEDULER}" \
  --role="roles/run.invoker"

echo "--- Despliegue de Downloader completado ---"echo "--- Desplegando Cloud Run (Downloader): ${CR_DOWNLOADER} ---"