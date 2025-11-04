-- Tabla lkp_demanda
CREATE TABLE IF NOT EXISTS `tgs-sandbox.ds_datos_tableros.lkp_demanda`
(
  cod_demanda INT64 NOT NULL,
  dim_tramo_cod_tramo INT64 NOT NULL,
  dim_tipo_servicio_cod_servicio INT64 NOT NULL,
  unidad STRING,
  mercado STRING,
  anio INT64,
  mes INT64,
  valor_demanda FLOAT64
);

-- Tabla lkp_escalones
CREATE TABLE IF NOT EXISTS `tgs-sandbox.ds_datos_tableros.lkp_escalones`
(
  cod_escalon INT64 NOT NULL,
  unidad STRING,
  anio INT64,
  mes INT64,
  tarifa FLOAT64,
  dim_tramo_cod_tramo INT64 NOT NULL,
  dim_tipo_servicio_cod_servicio INT64 NOT NULL
);
-- Tabla lkp_gas_retenido
CREATE TABLE IF NOT EXISTS `tgs-sandbox.ds_datos_tableros.lkp_gas_retenido`
(
  cod_retenido INT64 NOT NULL,
  valor FLOAT64,
  cod_tramo int64,
  mes INT64,
  anio INT64
);