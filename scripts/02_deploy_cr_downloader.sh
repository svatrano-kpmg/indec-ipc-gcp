#!/binbin/bash
source scripts/_env.sh
set -euo pipefail

echo "--- Desplegando Cloud Run (Downloader): ${CR_DOWNLOADER} ---"

export SERVICE_NAME=${CR_DOWNLOADER}
export AR_REPO="cloud-run-source-deploy"
export IMAGE="us-central1-docker.pkg.dev/$PROJECT_ID/$AR_REPO/$SERVICE_NAME:1.1.8"

# Build

gcloud auth configure-docker $REGION-docker.pkg.dev --project $PROJECT_INTAKE
gcloud builds submit --tag $IMAGE --project ${PROJECT_INTAKE}

# Deploy en Cloud Run (auth-only)
gcloud run deploy $SERVICE_NAME \
  --image $IMAGE \
  --region $REGION \
  --platform managed \
  --service-account $SA_RUN \
  --no-allow-unauthenticated \
  --project $PROJECT_INTAKE
# Se quita porque ahora se reciben en el payload
#  --set-env-vars PUBSUB_PROJECT_ID=${PROJECT_PROCESS},PUBSUB_TOPIC_RAW=${TOPIC_RAW} \


echo "--- Dando permisos al Scheduler (OIDC) para invocar ${CR_DOWNLOADER} ---"
# no lo pude ejecutar por problemas con las credenciales del gcloud 
gcloud run services add-iam-policy-binding ${CR_DOWNLOADER} \
  --region=${REGION} \
  --platform=managed \
  --member="serviceAccount:${SA_SCHEDULER}" \
  --role="roles/run.invoker"

echo "--- Despliegue de Downloader completado ---"echo "--- Desplegando Cloud Run (Downloader): ${CR_DOWNLOADER} ---"