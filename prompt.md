**ROL:** Actúa como un arquitecto de datos experto y desarrollador DevOps senior especializado en Google Cloud Platform (GCP).

**OBJETIVO:** Generar todo el código fuente (Python), los scripts SQL (DDL y Stored Procedures) y los comandos de despliegue (`gcloud`) para un pipeline de datos *serverless* y basado en eventos en GCP.

El pipeline ingiere dos archivos CSV (IPC e IPIM) desde el INDEC, los procesa siguiendo una arquitectura Medallion (Raw, Silver, Gold) y, finalmente, orquesta una serie de cálculos de cuadros tarifarios.

---

### 1. Arquitectura General

* **Proyecto GCP:** `tgs-sandbox`
* **Región:** `us-central1`
* **Arquitectura:** Medallion (GCS para Raw, BigQuery para Silver y Gold).
* **Orquestación:** 100% *event-driven* usando Cloud Scheduler, Cloud Run, Cloud Functions Gen2 y Pub/Sub.

---

### 2. Flujo del Pipeline (Componentes a Generar)

Genera el código para cada uno de los siguientes pasos:

#### PASO 1: Cloud Run (Downloader)
* **Nombre:** `cr-indec-downloader`
* **Trigger:** Cloud Scheduler (HTTP POST con OIDC).
* **Lógica (Python):**
    1.  Recibe un payload JSON del Scheduler. Ejemplo para IPC:
        ```json
        {
          "codigo_descarga": "IPC",
          "url_descarga": "[https://www.indec.gob.ar/ftp/cuadros/economia/serie_ipc_divisiones.csv](https://www.indec.gob.ar/ftp/cuadros/economia/serie_ipc_divisiones.csv)",
          "nombre_carpeta_gcs": "ipc",
          "nombre_procedure_gold": "ds_datos_tableros.sp_merge_lkp_indices_ajuste"
        }
        ```
    2.  Descarga el archivo desde la `url_descarga` (usando `requests`).
    3.  **IMPORTANTE:** Maneja la codificación. Los archivos del INDEC vienen en `latin-1`. Debe leerlos y guardarlos en GCS (Raw) como `utf-8`.
    4.  Guarda el archivo en el bucket `gs://tgs-sandbox-raw` dentro de la carpeta especificada (`nombre_carpeta_gcs`).
    5.  Publica un mensaje en el topic Pub/Sub `raw.done`.
    6.  El mensaje debe contener los siguientes **atributos**: `codigo_descarga`, `gcs_uri` (la ruta al archivo guardado), `nombre_procedure_gold`.

#### PASO 2: Cloud Function (Silver Transformer)
* **Nombre:** `cf-indec-silver-transformer`
* **Trigger:** Pub/Sub (Topic: `raw.done`).
* **Lógica (Python/Pandas):**
    1.  Lee los atributos del mensaje Pub/Sub (`codigo_descarga`, `gcs_uri`, `nombre_procedure_gold`).
    2.  Actúa como un **router** basado en el `codigo_descarga`:
    3.  **Si `codigo_descarga == "IPC"`:**
        * Lee el CSV desde `gcs_uri` (delimitador `;`, decimal `,`, encoding `utf-8`).
        * Filtra filas donde `Descripcion == "NIVEL GENERAL"` Y `Region == "Nacional"`.
        * Parsea el campo `Periodo` (ej. `201612`) para extraer `anio` (2016) y `mes` (12).
        * Selecciona las columnas `Periodo`, `anio`, `mes` y `Indice_IPC` (renombrada a `valor`).
    4.  **Si `codigo_descarga == "IPIM"`:**
        * Lee el CSV desde `gcs_uri` (delimitador `;`, decimal `,`, encoding `utf-8`).
        * Filtra filas donde `nivel_general_aperturas == "ng_nivel_general"`.
        * Parsea el campo `periodo` (ej. `2015-12-01`) para extraer `anio` (2015) y `mes` (12).
        * Selecciona las columnas `periodo`, `anio`, `mes` y `indice_ipim` (renombrada a `valor`).
    5.  Añade columnas de metadatos al DataFrame resultante: `archivo` (valor de `codigo_descarga`), `gcs_uri`, `load_ts` (timestamp actual).
    6.  Encuentra el `max_anio` y `max_mes` del lote procesado.
    7.  Carga el DataFrame en la tabla Silver de BigQuery: `tgs-sandbox.tgs_sandbox_curated.indec_ipc` (usando `WRITE_APPEND`).
    8.  Publica un mensaje en el topic `curated.done` con los atributos: `codigo_descarga`, `nombre_procedure_gold`, `max_anio` (string), `max_mes` (string).

#### PASO 3: Cloud Function (Gold SP Trigger)
* **Nombre:** `cf-indec-gold-trigger`
* **Trigger:** Pub/Sub (Topic: `curated.done`).
* **Lógica (Python):**
    1.  Lee los atributos del mensaje (`codigo_descarga`, `nombre_procedure_gold`, `max_anio`, `max_mes`).
    2.  Ejecuta el Stored Procedure en BigQuery pasándole el `codigo_descarga` como parámetro.
    3.  Query: `CALL tgs-sandbox.ds_datos_tableros.sp_merge_lkp_indices_ajuste('{codigo_descarga}');`
    4.  Si la llamada al SP es exitosa, publica un mensaje en el topic `gold.done` con los atributos: `codigo_descarga`, `anio` (el `max_anio` recibido), `mes` (el `max_mes` recibido).

#### PASO 4: Cloud Function (Orquestador Cuadro Tarifario)
* **Nombre:** `cf-indec-cuadro-tarifario`
* **Trigger:** Pub/Sub (Topic: `gold.done`).
* **Lógica (Python):**
    1.  Lee los atributos del mensaje (`codigo_descarga`, `anio`, `mes`).
    2.  **Validación de Datos:** Antes de ejecutar nada, debe chequear que existan datos para ese `anio` y `mes` en 4 tablas de BigQuery (usando `SELECT EXISTS` para eficiencia):
        * `tgs-sandbox.ds_datos_tableros.lkp_indices_ajuste` (WHERE `anio`, `mes` y `indices_id_indice` = `codigo_descarga`)
        * `tgs-sandbox.ds_datos_tableros.lkp_demanda` (WHERE `anio`, `mes`)
        * `tgs-sandbox.ds_datos_tableros.lkp_escalones` (WHERE `anio`, `mes`)
        * `tgs-sandbox.ds_datos_tableros.lkp_gas_retenido` (WHERE `anio`, `mes`)
    3.  **Si la validación de las 4 tablas es EXITOSA:**
        * Ejecuta los siguientes 3 Stored Procedures en orden:
            1.  `CALL tgs-sandbox.ds_datos_tableros.sp_merge_ft_ajustes();`
            2.  `CALL tgs-sandbox.ds_datos_tableros.sp_merge_ft_marcha_calculo();`
            3.  `CALL tgs-sandbox.ds_datos_tableros.sp_merge_ft_cuadro_tarifario();`
        * Tras la ejecución exitosa de los 3 SPs, publica un mensaje final en el topic `end.done` con los atributos: `anio`, `mes`.
    4.  **Si la validación FALLA:** Simplemente escribe un log indicando qué tabla faltaba y finaliza la función (no es un error, es lógica de negocio).

---

### 3. Scripts SQL (BigQuery)

Genera todos los archivos SQL necesarios.

#### A. DDLs (Creación de Tablas)
1.  **Tabla Silver (`ddl_silver.sql`):**
    * `tgs-sandbox.tgs_sandbox_curated.indec_ipc`
    * Columnas: `periodo` (STRING), `anio` (INT64), `mes` (INT64), `valor` (FLOAT64), `archivo` (STRING), `gcs_uri` (STRING), `load_ts` (TIMESTAMP).
    * Particionada por `DATE(load_ts)` y clusterizada por `(archivo, anio, mes)`.
2.  **Tablas Gold (`ddl_gold_tarifario.sql`):**
    * `tgs-sandbox.ds_datos_tableros.lkp_indices_ajuste` (Columnas: `indices_id_indice` STRING, `anio` INT64, `mes` INT64, `valor` FLOAT64, `gold_load_ts` TIMESTAMP).
    * `tgs-sandbox.ds_datos_tableros.lkp_demanda` (Columnas: `anio` INT64, `mes` INT64, `valor_demanda` FLOAT64, ...otras columnas...).
    * `tgs-sandbox.ds_datos_tableros.lkp_escalones` (Columnas: `anio` INT64, `mes` INT64, `tarifa` FLOAT64, ...otras columnas...).
    * `tgs-sandbox.ds_datos_tableros.lkp_gas_retenido` (Columnas: `anio` INT64, `mes` INT64, `valor` FLOAT64, ...otras columnas...).

#### B. Stored Procedures (Lógica de Negocio)
1.  **SP Merge Índices (`sp_merge_gold_indices.sql`):**
    * `tgs-sandbox.ds_datos_tableros.sp_merge_lkp_indices_ajuste(p_codigo_descarga STRING)`
    * Debe hacer un `MERGE` en `lkp_indices_ajuste`.
    * La fuente (`USING`) debe ser un `SELECT` de la tabla Silver (`indec_ipc`) filtrando por `archivo = p_codigo_descarga`.
    * El `MERGE` debe ser idempotente usando la clave `(indices_id_indice, anio, mes)`.
    * `WHEN MATCHED THEN UPDATE SET valor = S.valor, gold_load_ts = CURRENT_TIMESTAMP()`
    * `WHEN NOT MATCHED THEN INSERT (indices_id_indice, anio, mes, valor, gold_load_ts) VALUES (S.indices_id_indice, S.anio, S.mes, S.valor, CURRENT_TIMESTAMP())`
2.  **SPs Cálculo Tarifario (`sp_cuadro_tarifario.sql`):**
    * Genera *stubs* (esqueletos) para los 3 SPs de cálculo, ya que no tenemos su lógica interna:
        * `sp_merge_ft_ajustes()`
        * `sp_merge_ft_marcha_calculo()`
        * `sp_merge_ft_cuadro_tarifario()`

---

### 4. Scripts de Despliegue (`gcloud`)

Genera una serie de scripts `.sh` (bash) para desplegar toda la infraestructura.

1.  **`00_bootstrap.sh`:**
    * Habilita todas las APIs necesarias (Run, Pub/Sub, BQ, Scheduler, Eventarc, IAM).
    * Crea la Service Account para el Scheduler: `sa-scheduler-indec`.
    * Crea el GCS Bucket: `tgs-sandbox-raw`.
    * Crea todos los Topics de Pub/Sub: `raw.done`, `curated.done`, `gold.done`, `end.done`.
    * Crea los Topics DLQ (Dead Letter Queues): `raw.done-dlq`, `curated.done-dlq`, `gold.done-dlq`.
    * Asigna los roles IAM mínimos a la SA de Compute por defecto (que usarán las CF/Run) para publicar en Pub/Sub, escribir en GCS y ser Editor/JobUser de BigQuery.
2.  **`01_bq_init.sh`:**
    * Crea los datasets `tgs_sandbox_curated` y `ds_datos_tableros`.
    * Ejecuta todos los archivos SQL (DDL y SP) generados en el paso anterior.
3.  **`02_deploy_cr_downloader.sh`:**
    * Despliega `cr-indec-downloader` (usando `--source` y `--no-allow-unauthenticated`).
    * Asigna el rol `roles/run.invoker` a la SA `sa-scheduler-indec` sobre este servicio.
4.  **`03_deploy_cf_silver.sh`:**
    * Despliega `cf-indec-silver-transformer` (usando `--source`).
    * Configura el trigger de Eventarc para el topic `raw.done`.
    * Configura la política de reintentos (`--trigger-retry`) y el DLQ (`--trigger-dead-letter-topic=raw.done-dlq`).
    * Pasa las variables de entorno necesarias (filtros IPC/IPIM).
5.  **`04_deploy_cf_gold.sh`:**
    * Despliega `cf-indec-gold-trigger`.
    * Configura el trigger de Eventarc para el topic `curated.done`.
    * Configura reintentos y DLQ (`curated.done-dlq`).
6.  **`05_deploy_cf_cuadro.sh`:**
    * Despliega `cf-indec-cuadro-tarifario`.
    * Configura el trigger de Eventarc para el topic `gold.done`.
    * Configura reintentos y DLQ (`gold.done-dlq`).
7.  **`06_deploy_scheduler.sh`:**
    * Obtiene la URL del `cr-indec-downloader` desplegado.
    * Crea los dos `gcloud scheduler jobs create http` (uno para "IPC" y otro para "IPIM").
    * Ambos deben usar el método `POST`, apuntar a la URL del Cloud Run, pasar el JSON `message-body` correspondiente, y usar OIDC (`--oidc-service-account-email=sa-scheduler-indec@...`).
    * Programación: `5 10 1 * *` (día 1 de cada mes a las 10:05).

---

**ENTREGABLE:**
Proporciona todo el código y los scripts organizados por directorios, listos para ser guardados en un repositorio.
/ 
├── bq/ 
│   ├── ddl_silver.sql 
│   ├── ddl_gold_indices.sql 
│   ├── ddl_gold_tarifario.sql 
│   ├── sp_merge_gold_indices.sql 
│   └── sp_cuadro_tarifario.sql 
|
├── cr-downloader/ 
│   ├── main.py 
│   └── requirements.txt 
|
├── cf-silver-transformer/ 
│   ├── main.py 
│   └── requirements.txt 
|
├── cf-gold-trigger/ 
│   ├── main.py 
│   └── requirements.txt 
|
├── cf-cuadro-tarifario/ 
│   ├── main.py 
│   └── requirements.txt 
|
└── scripts/ 
    ├── 00_bootstrap.sh 
    ├── 01_bq_init.sh 
    ├── 02_deploy_cr_downloader.sh 
    ├── 03_deploy_cf_silver.sh 
    ├── 04_deploy_cf_gold.sh 
    ├── 05_deploy_cf_cuadro.sh 
    └── 06_deploy_scheduler.sh