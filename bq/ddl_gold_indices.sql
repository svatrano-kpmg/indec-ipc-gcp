CREATE SCHEMA IF NOT EXISTS `tgs-sandbox.ds_datos_tableros`
OPTIONS(location="us-central1");

CREATE TABLE IF NOT EXISTS `tgs-sandbox.ds_datos_tableros.lkp_indices_ajuste` (
  ft_ajustes_cod_ajuste INT64, 
  indices_id_indice INT64, -- 1 para 'IPC' o 2 para 'IPIM'
  anio INT64,
  mes INT64,
  valor FLOAT64,
  gold_load_ts TIMESTAMP
);