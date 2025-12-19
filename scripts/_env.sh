#!/bin/bash
export PROJECT_ID="tgs-sandbox"
export REGION="us-central1"

# SAs (Mantenemos la SA del Scheduler)
export SA_SCHEDULER="sa-scheduler-indec@${PROJECT_ID}.iam.gserviceaccount.com"
# Usaremos la SA de Compute por defecto para los servicios, por simplicidad
export SA_COMPUTE="${PROJECT_ID}@compute-system.iam.gserviceaccount.com" 

# GCS
export GCS_RAW_BUCKET="${PROJECT_ID}-raw"
export GCS_DATAPROC_BUCKET="${PROJECT_ID}-dataproc-staging" # NUEVO

# Pub/Sub Topics
export TOPIC_RAW="raw.done"
export TOPIC_CURATED="curated.done"
export TOPIC_GOLD="gold.done"
export TOPIC_END="end.done"

# Pub/Sub DLQs
export DLQ_RAW="${TOPIC_RAW}-dlq"
export DLQ_CURATED="${TOPIC_CURATED}-dlq"
export DLQ_GOLD="${TOPIC_GOLD}-dlq"

# Dataproc
export DATAPROC_CLUSTER="sqlserver-cluster"
export CF_DOWNLOADER_LAUNCHER="cf-indec-downloader-launcher"

# BigQuery
export BQ_DS_SILVER="tgs_sandbox_curated"
export BQ_TBL_SILVER="indec_ipc"
export BQ_DS_GOLD="ds_datos_tableros"

# Cloud Run / Functions (Nuevos nombres)
export CR_DOWNLOADER="cr-indec-downloader"
export CF_SILVER="cf-indec-silver-transformer"
export CF_GOLD="cf-indec-gold-trigger"
export CF_CUADRO="cf-indec-cuadro-tarifario"

# Cloud Function Silver filters (estan en las variables de entorno pero la pongo igual)
export FILTER_IPC_DESC="NIVEL GENERAL"
export FILTER_IPC_REGION="Nacional"
export FILTER_IPIM_APERTURA="ng_nivel_general"

# Entry points
export ENTRY_POINT_DOWNLOADER="download_data"
export ENTRY_POINT="process_raw_to_silver"
export ENTRY_POINT_GOLD="process_silver_to_gold"
export ENTRY_POINT_CUADRO="process_gold_to_cuadro"
# export SA_COMPUTE="969553573595-compute@developer.gserviceaccount.com" # Asumiendo que usa esta SA
