-- Dataset Silver en us-central1
CREATE SCHEMA IF NOT EXISTS `tgs-sandbox.tgs_sandbox_curated`
OPTIONS(location="us-central1");

-- Tabla Silver (particionada por load_ts; cluster por anio, mes)
CREATE TABLE IF NOT EXISTS `tgs-sandbox.tgs_sandbox_curated.indec_ipc` (
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
