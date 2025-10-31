#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/_env.sh"

echo ">> Creando dataset Silver (si no existe)..."
bq --location="${REGION}" mk --dataset --description "Silver curated data" \
  "${PROJECT}:${SILVER_DATASET}" 2>/dev/null || true

echo ">> Creando tabla Silver (particionada/clusterizada)..."
bq query --use_legacy_sql=false <<EOF
CREATE TABLE IF NOT EXISTS \`${PROJECT}.${SILVER_DATASET}.${SILVER_TABLE}\` (
  periodo STRING,
  anio INT64,
  mes INT64,
  valor FLOAT64,
  archivo STRING,
  gcs_uri STRING,
  source_url STRING,
  load_ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
PARTITION BY DATE(load_ts)
CLUSTER BY anio, mes;
EOF

echo ">> Creando/actualizando Stored Procedure de Gold..."
bq query --use_legacy_sql=false <<EOF
CREATE OR REPLACE PROCEDURE \`${SP_FQN}\`(p_archivo STRING)
BEGIN
  MERGE \`${PROJECT}.${GOLD_DATASET}.${GOLD_TABLE}\` T
  USING (
    SELECT
      1 AS indices_id_indice,
      anio,
      mes,
      valor
    FROM \`${PROJECT}.${SILVER_DATASET}.${SILVER_TABLE}\`
    WHERE archivo = p_archivo
      AND anio IS NOT NULL AND mes IS NOT NULL AND valor IS NOT NULL
  ) S
  ON T.indices_id_indice = S.indices_id_indice
     AND T.anio = S.anio
     AND T.mes = S.mes
  WHEN MATCHED THEN
    UPDATE SET valor = S.valor
  WHEN NOT MATCHED THEN
    INSERT (ft_ajustes_cod_ajuste, indices_id_indice, anio, mes, valor)
    VALUES (NULL, S.indices_id_indice, S.anio, S.mes, S.valor);
END;
EOF

echo ">> BigQuery OK."
