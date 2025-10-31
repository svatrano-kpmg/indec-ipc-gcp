#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/_env.sh"

echo ">> Test: llamada directa a Cloud Run con OIDC (ejemplo 2016-12)..."
RUN_URL=$(gcloud run services describe "${RUN_SERVICE}" --region "${REGION}" --format='value(status.url)')
ID_TOKEN=$(gcloud auth print-identity-token --audiences="${RUN_URL}")
curl -i -H "Authorization: Bearer ${ID_TOKEN}" "${RUN_URL}/run?period=2016-12"

echo ">> Esperar 10-20s y validar en BigQuery (conteo por archivo)..."
bq query --use_legacy_sql=false --format=prettyjson <<EOF
SELECT archivo, COUNT(*) AS n, MIN(anio) AS min_anio, MAX(anio) AS max_anio
FROM \`${PROJECT}.${SILVER_DATASET}.${SILVER_TABLE}\`
GROUP BY archivo
ORDER BY archivo DESC
EOF

echo ">> Test: replay directo del topic raw.done (si necesitás reprocesar un archivo ya en RAW)..."
gcloud pubsub topics publish "${TOPIC_RAW}" --message='{
  "project_id":"'"${PROJECT}"'",
  "gcs_uri":"gs://'"${RAW_BUCKET}"'/indec/ipc/2016/12/sh_ipc_12_16.xls",
  "archivo":"sh_ipc_12_16.xls",
  "anio":2016,
  "mes":12,
  "source_url":"https://www.indec.gob.ar/ftp/cuadros/economia/sh_ipc_12_16.xls"
}'

echo ">> Validar MERGE en Gold..."
bq query --use_legacy_sql=false --format=prettyjson <<EOF
SELECT indices_id_indice, anio, mes, valor
FROM \`${PROJECT}.${GOLD_DATASET}.${GOLD_TABLE}\`
WHERE indices_id_indice=1
ORDER BY anio, mes
LIMIT 20;
EOF

echo ">> E2E tests ejecutados."
