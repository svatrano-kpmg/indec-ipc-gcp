#!/bin/bash
# export PROJECT_ID="tgs-sandbox"
export REGION="us-central1"

# export PROJECT_ID="prj-data-process-dev"
export PROJECT_ID="prj-data-intake-dev"
# --- 1. DEFINICIÓN DE PROYECTOS ---
export PROJECT_INTAKE="prj-data-intake-dev"    # Scheduler, Launcher CF, Dataproc
export PROJECT_PROCESS="prj-data-process-dev"  # Pub/Sub, Funciones (Silver/Gold)
export PROJECT_LAKE="prj-data-lakehouse-dev"   # Storage Raw, BigQuery

# SAs (Mantenemos la SA del Scheduler)
export SA_SCHEDULER="sa-scheduler@${PROJECT_ID}.iam.gserviceaccount.com"
# Usaremos la SA de Compute por defecto para los servicios, por simplicidad
# export SA_COMPUTE="${PROJECT_ID}@compute-system.iam.gserviceaccount.com" 
export SA_RUN="sa-dataproc@${PROJECT_INTAKE}.iam.gserviceaccount.com"
export SA_COMPUTE="sa-function@${PROJECT_PROCESS}.iam.gserviceaccount.com"
# export SA_FUNCTION="sa-cloud-function@prj-data-intake-dev.iam.gserviceaccount.com"

# GCS
# export GCS_RAW_BUCKET="${PROJECT_ID}-raw"
export GCS_DATAPROC_BUCKET="script-pipelines-dataproc" # NUEVO
export GCS_RAW_BUCKET="raw-zone-lakehouse"
# export GCS_DATAPROC_BUCKET="${GCS_RAW_BUCKET}"

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
export DATAPROC_PROJECT_ID="${PROJECT_INTAKE}"
export DATAPROC_CLUSTER="sqlserver-cluster"
export CF_DOWNLOADER_LAUNCHER="cf-indec-downloader-launcher"

# BigQuery
export BQ_PROJECT_ID="${PROJECT_LAKE}"
export BQ_DS_SILVER="DS_ASUNTOS_REGULATORIOS_SANDBOX"
export BQ_TBL_SILVER="indec_ipc"
export BQ_DS_GOLD="DS_ASUNTOS_REGULATORIOS_SANDBOX"

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
