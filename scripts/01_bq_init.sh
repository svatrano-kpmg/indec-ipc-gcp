#!/binbin/bash
source scripts/_env.sh
set -euo pipefail

echo "--- Creando Datasets BQ ---"
bq mk --location=${REGION} --dataset ${PROJECT_ID}:${BQ_DS_SILVER} || echo "Dataset ${BQ_DS_SILVER} ya existe."
bq mk --location=${REGION} --dataset ${PROJECT_ID}:${BQ_DS_GOLD} || echo "Dataset ${BQ_DS_GOLD} ya existe."

echo "--- Ejecutando DDLs ---"
bq query --use_legacy_sql=false < bq/ddl_silver.sql
bq query --use_legacy_sql=false < bq/ddl_gold_indices.sql
bq query --use_legacy_sql=false < bq/ddl_gold_tarifario.sql

echo "--- Creando Stored Procedures ---"
bq query --use_legacy_sql=false < bq/sp_merge_gold_indices.sql
bq query --use_legacy_sql=false < bq/sp_cuadro_tarifario.sql

echo "--- BQ Init completado ---"