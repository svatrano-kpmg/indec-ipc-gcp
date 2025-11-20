CREATE OR REPLACE PROCEDURE `tgs-sandbox.ds_datos_tableros.sp_merge_lkp_indices_ajuste`(
  p_codigo_descarga STRING -- Parámetro de entrada (ej: 'IPC' o 'IPIM')
)
BEGIN
  MERGE `tgs-sandbox.ds_datos_tableros.lkp_indices_ajuste` AS T
  USING (
    SELECT
      CASE p_codigo_descarga
        WHEN 'IPC' THEN 1
        WHEN 'IPIM' THEN 2
        ELSE NULL
      END AS indices_id_indice,
      anio,
      mes,
      valor
    FROM `tgs-sandbox.tgs_sandbox_curated.indec_ipc`
    WHERE archivo = p_codigo_descarga -- Filtra SÓLO este archivo
      AND anio IS NOT NULL AND mes IS NOT NULL AND valor IS NOT NULL
  ) AS S
  ON T.indices_id_indice = S.indices_id_indice
     AND T.anio = S.anio
     AND T.mes = S.mes
  
  WHEN MATCHED THEN
    UPDATE SET 
      valor = S.valor,
      gold_load_ts = CURRENT_TIMESTAMP()

  WHEN NOT MATCHED THEN
    INSERT (
      ft_ajustes_cod_ajuste, 
      indices_id_indice, 
      anio, 
      mes, 
      valor,
      gold_load_ts
    )
    VALUES (
      NULL, 
      S.indices_id_indice, 
      S.anio, 
      S.mes, 
      S.valor,
      CURRENT_TIMESTAMP()
    );
END;