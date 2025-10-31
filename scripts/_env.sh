#!/usr/bin/env bash
set -euo pipefail

export PROJECT="tgs-sandbox"
export REGION="us-central1"

export RAW_BUCKET="tgs-sandbox-raw"

export TOPIC_RAW="raw.done"
export TOPIC_CURATED="curated.done"

export SILVER_DATASET="tgs_sandbox_curated"
export SILVER_TABLE="indec_ipc"

export GOLD_DATASET="ds_datos_tableros"
export GOLD_TABLE="lkp_indices_ajuste"
export SP_FQN="${PROJECT}.${GOLD_DATASET}.sp_merge_lkp_indices_ajuste"

export RUN_SERVICE="cr-indec-ipc-downloader"
export RUN_IMAGE="gcr.io/${PROJECT}/${RUN_SERVICE}:latest"

export CF_SILVER="cf-indec-ipc-silver"
export CF_GOLD_TRIGGER="cf-indec-ipc-gold-trigger"

export SCHEDULER_SA="sa-scheduler-indec"
export SCHEDULER_JOB="indec-ipc-monthly"
export SCHEDULER_LOCATION="us-central1"
export TIME_ZONE="America/Argentina/Buenos_Aires"
