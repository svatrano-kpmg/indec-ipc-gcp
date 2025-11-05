# Pipeline de Ingesta de Índices (INDEC) y Cálculo Tarifario en GCP

Este proyecto implementa un pipeline de datos serverless en Google Cloud para automatizar la ingesta, transformación y carga de múltiples índices económicos (IPC, IPIM) desde el INDEC.

El pipeline sigue una arquitectura Medallion (Raw, Silver, Gold) y culmina con la orquestación de un proceso de cálculo de cuadro tarifario, todo disparado por eventos.

## 🎯 Arquitectura del Pipeline

El flujo es 100% event-driven y se compone de 5 microservicios principales:

1.  **Scheduler (OIDC) → Cloud Run (Downloader)**
    * `Cloud Scheduler` (con OIDC) invoca de forma segura a un `Cloud Run` privado.
    * Existen *múltiples* jobs, uno por cada índice (IPC, IPIM), cada uno con su URL y configuración.
    * El Cloud Run descarga el archivo, lo normaliza (ej. `latin-1` a `utf-8`) y lo guarda en GCS (Capa **Raw**).
    * Al finalizar, publica un mensaje en `raw.done`.

2.  **Pub/Sub (raw.done) → CF (Silver Transformer)**
    * Un mensaje en `raw.done` (con atributos `codigo_descarga`, `gcs_uri`, etc.) dispara `cf-indec-silver-transformer`.
    * Esta Cloud Function actúa como un *router*: lee el `codigo_descarga` y aplica la lógica de parsing (Pandas) específica para IPC o IPIM.
    * Transforma los datos y los carga en la tabla **Silver** de BigQuery (`tgs_sandbox_curated.indec_ipc`).
    * Detecta el mes/año (`max_anio`, `max_mes`) más reciente del lote y lo publica en `curated.done`.

3.  **Pub/Sub (curated.done) → CF (Gold SP Trigger)**
    * Un mensaje en `curated.done` dispara `cf-indec-gold-trigger`.
    * Esta función lee los atributos (incluyendo `max_anio`, `max_mes`) y ejecuta el Stored Procedure de carga **Gold**.
    * Invoca `CALL ds_datos_tableros.sp_merge_lkp_indices_ajuste(@codigo_descarga)`.
    * Al finalizar, publica un mensaje en `gold.done` (pasando `anio` y `mes`).

4.  **Pub/Sub (gold.done) → CF (Cuadro Tarifario)**
    * Un mensaje en `gold.done` dispara `cf-indec-cuadro-tarifario`.
    * Esta función *valida* si todos los datos necesarios para el `anio`/`mes` recibido existen en las tablas `lkp_*` (demanda, escalones, etc.).
    * Si la validación es exitosa, ejecuta en orden los 3 SPs del cálculo tarifario (`sp_merge_ft_ajustes`, `sp_merge_ft_marcha_calculo`, `sp_merge_ft_cuadro_tarifario`).
    * Al finalizar, publica un mensaje en `end.done`.

5.  **Pub/Sub (end.done)**
    * Topic final que notifica que el cuadro tarifario para un `anio`/`mes` específico está disponible.

## 🎯 Arquitectura del Pipeline

El flujo es 100% event-driven y se compone de 5 microservicios principales que interactúan a través de Pub/Sub.
```mermaid
graph TD
    subgraph "1. Disparador (Scheduler)"
        Job_IPC[Scheduler Job (IPC)]
        Job_IPIM[Scheduler Job (IPIM)]
    end

    subgraph "2. Ingesta (RAW)"
        CR_Downloader(<b>Cloud Run</b><br/>cr-indec-downloader)
        GCS_Raw[<b>GCS (Raw)</b><br/>gs://...-raw]
        Topic_Raw(<b>Pub/Sub</b><br/>raw.done)
        DLQ_Raw(<b>DLQ</b><br/>raw.done-dlq)
    end

    subgraph "3. Transformación (SILVER)"
        CF_Silver(<b>Cloud Function</b><br/>cf-indec-silver-transformer)
        BQ_Silver[<b>BigQuery (Silver)</b><br/>tgs_..._curated.indec_ipc]
        Topic_Curated(<b>Pub/Sub</b><br/>curated.done)
        DLQ_Curated(<b>DLQ</b><br/>curated.done-dlq)
    end
    
    subgraph "4. Carga (GOLD - Índices)"
        CF_Gold(<b>Cloud Function</b><br/>cf-indec-gold-trigger)
        SP_Merge_Indices[<b>Stored Procedure</b><br/>sp_merge_lkp_indices...]
        BQ_Gold_Indices[<b>BigQuery (Gold)</b><br/>...lkp_indices_ajuste]
        Topic_Gold(<b>Pub/Sub</b><br/>gold.done)
        DLQ_Gold(<b>DLQ</b><br/>gold.done-dlq)
    end

    subgraph "5. Orquestación (Cálculo Tarifario)"
        CF_Cuadro(<b>Cloud Function</b><br/>cf-indec-cuadro-tarifario)
        BQ_Validate[<b>Validación BQ</b><br/>(lkp_demanda, lkp_escalones...)]
        SP_Calculo[<b>Stored Procedures (3)</b><br/>sp_merge_ft_ajustes<br/>sp_merge_ft_marcha...<br/>sp_merge_ft_cuadro...]
        Topic_End(<b>Pub/Sub</b><br/>end.done)
    end

    %% --- Flujo Principal ---
    Job_IPC -- OIDC Invoke --> CR_Downloader
    Job_IPIM -- OIDC Invoke --> CR_Downloader
    
    CR_Downloader -- 1. Guarda CSV --> GCS_Raw
    CR_Downloader -- 2. Publica msg --> Topic_Raw

    Topic_Raw -- Trigger --> CF_Silver
    CF_Silver -- Lee CSV --> GCS_Raw
    CF_Silver -- Carga Datos --> BQ_Silver
    CF_Silver -- Publica msg<br/>(con max_anio/mes) --> Topic_Curated

    Topic_Curated -- Trigger --> CF_Gold
    CF_Gold -- Llama a SP<br/>(con codigo_descarga) --> SP_Merge_Indices
    SP_Merge_Indices -- Lee --> BQ_Silver
    SP_Merge_Indices -- MERGE --> BQ_Gold_Indices
    CF_Gold -- Publica msg<br/>(con anio/mes) --> Topic_Gold

    Topic_Gold -- Trigger --> CF_Cuadro
    CF_Cuadro -- 1. Valida datos --> BQ_Validate
    CF_Cuadro -- 2. Llama SPs --> SP_Calculo
    CF_Cuadro -- 3. Publica msg --> Topic_End

    %% --- Flujo de Errores (DLQs) ---
    CF_Silver -- on error --> DLQ_Raw
    CF_Gold -- on error --> DLQ_Curated
    CF_Cuadro -- on error --> DLQ_Gold
``

## 🗂️ Estructura del Repositorio
```
. 
├── bq/ 
│ ├── ddl_silver.sql # DDL Tabla Silver (unificada) 
│ ├── ddl_gold_indices.sql # DDL Tabla Gold (lkp_indices_ajuste) 
│ ├── ddl_gold_tarifario.sql # DDLs (demanda, escalones, gas_retenido) 
│ ├── sp_merge_gold_indices.sql # SP (MERGE para lkp_indices_ajuste) 
│ └── sp_cuadro_tarifario.sql # (Stubs) SPs para ft_ajustes, ft_marcha, etc. 
├── cr-downloader/ # Cloud Run (Downloader) 
│ ├── main.py 
│ └── requirements.txt 
├── cf-silver-transformer/ # CF (Raw -> Silver) 
│ ├── main.py 
│ └── requirements.txt 
├── cf-gold-trigger/ # CF (Silver -> Gold) 
│ ├── main.py 
│ └── requirements.txt 
├── cf-cuadro-tarifario/ # CF (Gold -> Cálculo Tarifario) 
│ ├── main.py 
│ └── requirements.txt 
├── scripts/ 
│ ├── _env.sh # Variables de entorno 
│ ├── 00_bootstrap.sh # Crea SAs, Topics, DLQs 
│ ├── 01_bq_init.sh # Ejecuta todos los SQL de /bq 
│ ├── 02_deploy_cr_downloader.sh 
│ ├── 03_deploy_cf_silver.sh 
│ ├── 04_deploy_cf_gold.sh 
│ ├── 05_deploy_cf_cuadro.sh 
│ ├── 06_deploy_scheduler.sh # Crea los 2 jobs (IPC, IPIM) 
│ └── 07_cleanup.sh # Limpia todos los recursos 
└── README.md
```
## 🚀 Despliegue (End-to-End)

El despliegue está 100% automatizado usando los scripts en el directorio `/scripts`.

**Proyecto:** `tgs-sandbox`
**Región:** `us-central1`

### Pasos

1.  **Configurar Variables:**
    Revisar y ajustar el archivo `scripts/_env.sh` con los IDs de proyecto y nombres de recursos correctos.

2.  **Autenticación:**
    ```bash
    gcloud auth login
    gcloud config set project tgs-sandbox
    ```

3.  **Ejecutar Scripts de Despliegue (en orden):**
    ```bash
    # 0. Habilitar APIs y crear SAs, Topics, DLQs
    ./scripts/00_bootstrap.sh

    # 1. Crear Datasets, Tablas y Stored Procedures en BigQuery
    ./scripts/01_bq_init.sh

    # 2. Desplegar el Cloud Run (Downloader)
    ./scripts/02_deploy_cr_downloader.sh

    # 3. Desplegar CF Silver (con trigger raw.done)
    ./scripts/03_deploy_cf_silver.sh

    # 4. Desplegar CF Gold (con trigger curated.done)
    ./scripts/04_deploy_cf_gold.sh

    # 5. Desplegar CF Cuadro Tarifario (con trigger gold.done)
    ./scripts/05_deploy_cf_cuadro.sh

    # 6. Crear los Cloud Scheduler Jobs (IPC y IPIM)
    ./scripts/06_deploy_scheduler.sh
    ```

4.  **Probar el Pipeline:**
    Se puede forzar la ejecución de los jobs desde la consola de Cloud Scheduler.
    ```bash
    gcloud scheduler jobs run job-indec-ipc
    gcloud scheduler jobs run job-indec-ipim
    ```

### 🧹 Limpieza

Para eliminar todos los recursos creados por este despliegue, ejecuta:

```bash
./scripts/07_cleanup.sh
```
