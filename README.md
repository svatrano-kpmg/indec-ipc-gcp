# INDEC IPC — Data Workflow en GCP (Medallion Architecture)

**Objetivo:** Automatizar la ingesta mensual del archivo `sh_ipc_MM_YY.xls` del INDEC, almacenarlo en **RAW (GCS)**, parsearlo para construir duplas `(periodo; valor)` del **Nivel general**, y cargar los datos en:
- **Silver (BigQuery):** `tgs-sandbox.tgs_sandbox_curated.indec_ipc`
- **Gold (BigQuery):** `tgs-sandbox.ds_datos_tableros.lkp_indices_ajuste`, mediante **MERGE** ejecutado por **Stored Procedure**, **solo con lo nuevo** del archivo recibido.

## 🔷 Arquitectura

```
Cloud Scheduler (OIDC, mensual)
        │  HTTP (OIDC)
        ▼
Cloud Run: cr-indec-ipc-downloader (privado)
  ├─ Descarga sh_ipc_MM_YY.xls (INDEC)
  ├─ Guarda en GCS RAW: gs://tgs-sandbox-raw/indec/ipc/YYYY/MM/...
  └─ Pub/Sub topic: raw.done {archivo, gcs_uri, ...}
        │
        ▼
Cloud Functions Gen2: cf-indec-ipc-silver (trigger: raw.done)
  ├─ Lee XLS desde GCS
  ├─ Detecta hoja "Índices IPC Cobertura Nacional"
  ├─ Autodetecta fila de periodos y "Nivel general"
  ├─ Extrae (anio, mes, valor) con YY→2000+YY
  ├─ Inserta en BQ Silver: tgs_sandbox_curated.indec_ipc
  └─ Pub/Sub topic: curated.done {archivo, n_rows, ...}
        │
        ▼
Cloud Functions Gen2: cf-indec-ipc-gold-trigger (trigger: curated.done)
  └─ CALL BQ SP: ds_datos_tableros.sp_merge_lkp_indices_ajuste(archivo)
         │
         ▼
BigQuery: MERGE → ds_datos_tableros.lkp_indices_ajuste
  - ft_ajustes_cod_ajuste = NULL
  - indices_id_indice = 1
  - anio, mes, valor desde Silver (solo archivo recibido)
```

## 📦 Componentes (IDs finales)
- **Proyecto:** `tgs-sandbox`
- **Región (Run/CF2/BQ):** `us-central1`
- **RAW (GCS):** `gs://tgs-sandbox-raw`
- **Topics (Pub/Sub):** `raw.done`, `curated.done`
- **Silver (BQ):** dataset `tgs_sandbox_curated`, tabla `indec_ipc`
- **Gold (BQ):** `ds_datos_tableros.lkp_indices_ajuste`
- **Stored Procedure (BQ):** `ds_datos_tableros.sp_merge_lkp_indices_ajuste(p_archivo STRING)`
- **Cloud Run:** `cr-indec-ipc-downloader` (privado, invocado por OIDC)
- **CF Silver (Gen2):** `cf-indec-ipc-silver` (trigger: `raw.done`)
- **CF Gold Trigger (Gen2):** `cf-indec-ipc-gold-trigger` (trigger: `curated.done`)
- **Scheduler SA:** `sa-scheduler-indec@tgs-sandbox.iam.gserviceaccount.com`
- **Scheduler job:** `indec-ipc-monthly` (loc: `us-central1`)

## 🗂️ Data Source
**URL base:** `https://www.indec.gob.ar/ftp/cuadros/economia/sh_ipc_MM_YY.xls`  
`MM`: mes (2 dígitos) · `YY`: últimos 2 dígitos (interpretados como `2000+YY`).

**Hoja objetivo:** contiene el texto **“Índices IPC Cobertura Nacional”**.  
**Layout variable** (encabezados de período):
- **Fecha Excel** (ctype=DATE) o **serial Excel** (NUMBER)
- Texto `mmm-yy`, `mmm-yyyy`
- Texto con **slashes** `dd/mm/yyyy`, `mm/yyyy` (suele ser `MM/01/YYYY`)

**Fila de valores:** la de **“Nivel general”** en la columna A.

## 🧱 Modelo de datos

### Silver: `tgs_sandbox_curated.indec_ipc`
- `periodo` STRING (normalizado `mmm-yy`, p.ej. `dic-16`)
- `anio` INT64
- `mes` INT64
- `valor` FLOAT64
- `archivo` STRING
- `gcs_uri` STRING
- `source_url` STRING
- `load_ts` TIMESTAMP (DEFAULT CURRENT_TIMESTAMP)

**Particionamiento:** `DATE(load_ts)`  
**Clustering:** `(anio, mes)`

### Gold: `ds_datos_tableros.lkp_indices_ajuste`
- `ft_ajustes_cod_ajuste` INT64 ← **NULL**
- `indices_id_indice` INT64 ← **1**
- `anio` INT64
- `mes` INT64
- `valor` FLOAT64

**MERGE** idempotente por `(indices_id_indice, anio, mes)`  
**Alcance:** **solo** filas de Silver con `archivo = p_archivo`.

## 🔐 IAM mínimo
- **Cloud Run SA:** `roles/storage.objectAdmin`, `roles/pubsub.publisher`, `roles/logging.logWriter`
- **CF Silver SA:** `roles/storage.objectViewer` (RAW), `roles/bigquery.dataEditor` (Silver), `roles/bigquery.jobUser`, `roles/pubsub.publisher` (curated.done), `roles/logging.logWriter`
- **CF Gold Trigger SA:** `roles/bigquery.jobUser`, `roles/bigquery.dataEditor` (en `ds_datos_tableros`), `roles/logging.logWriter`
- **Scheduler SA:** `roles/run.invoker` **sobre el servicio de Run**.

> **Cloud Run privado** (no `allUsers`); Scheduler invoca con **OIDC**.

## 🚀 Despliegue — orden sugerido

```bash
chmod +x scripts/*.sh

bash scripts/00_bootstrap.sh
bash scripts/01_bq_init.sh
bash scripts/02_deploy_run.sh
bash scripts/03_deploy_cf_silver.sh
bash scripts/04_deploy_cf_gold_trigger.sh
bash scripts/05_scheduler_oidc.sh
bash scripts/06_test_e2e.sh
```

## 🧪 Pruebas rápidas

- **Forzar Scheduler**:
  ```bash
  gcloud scheduler jobs run indec-ipc-monthly --location=us-central1
  ```
- **Llamada directa (privado con OIDC)**:
  ```bash
  RUN_URL=$(gcloud run services describe cr-indec-ipc-downloader --region us-central1 --format='value(status.url)')
  ID_TOKEN=$(gcloud auth print-identity-token --audiences="${RUN_URL}")
  curl -i -H "Authorization: Bearer ${ID_TOKEN}" "${RUN_URL}/run?period=2025-10"
  ```

## 📊 Monitoreo y Alertas (sugerencias)
- Logs-based (CF/Run): alerta si `severity>=ERROR`.
- BigQuery jobs: alerta si `errorResult` en job.
- Scheduler: alerta por intentos `FAILED`.

## 🧯 Troubleshooting
- **403 Run**: faltan permisos `roles/run.invoker` a la SA del Scheduler o falta token OIDC.
- **0 filas en Silver**: layout cambió. Revisar logs:
  - `[Detect] header_row=..., value_row=..., start_col=...`
  - `[Diagnóstico] Encabezados ejemplo ...`
- **`.xls`**: asegurar `xlrd==1.2.0`.

---
