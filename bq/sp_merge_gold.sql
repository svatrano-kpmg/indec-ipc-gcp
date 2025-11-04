CREATE OR REPLACE PROCEDURE `tgs-sandbox.ds_datos_tableros.sp_merge_lkp_indices_ajuste`(p_archivo STRING)
BEGIN
  MERGE `tgs-sandbox.ds_datos_tableros.lkp_indices_ajuste` T
  USING (
    SELECT
      1 AS indices_id_indice,
      anio,
      mes,sp_merge_gold_indices.sql
      valor
    FROM `tgs-sandbox.tgs_sandbox_curated.indec_ipc`
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
