#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/_env.sh"

gcloud config set project "${PROJECT}"

echo ">> Habilitando APIs..."
gcloud services enable \
  run.googleapis.com cloudfunctions.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com pubsub.googleapis.com storage.googleapis.com \
  bigquery.googleapis.com cloudscheduler.googleapis.com eventarc.googleapis.com \
  logging.googleapis.com

echo ">> Creando bucket RAW (si no existe)..."
 gsutil ls -b "gs://${RAW_BUCKET}" >/dev/null 2>&1 || gsutil mb -l "${REGION}" "gs://${RAW_BUCKET}"
 gsutil versioning set on "gs://${RAW_BUCKET}"

echo ">> Creando topics Pub/Sub (si no existen)..."
gcloud pubsub topics describe "${TOPIC_RAW}" >/dev/null 2>&1 || gcloud pubsub topics create "${TOPIC_RAW}"
gcloud pubsub topics describe "${TOPIC_CURATED}" >/dev/null 2>&1 || gcloud pubsub topics create "${TOPIC_CURATED}"

echo ">> Bootstrap OK."
