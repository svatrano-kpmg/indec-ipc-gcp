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

```
Cloud Scheduler (OIDC, mensual)
  ┌─ Job: "job-indec-ipc"
  └─ Job: "job-indec-ipim"
           │
           │ HTTP (OIDC) con payload JSON (código, url, carpeta, sp_name)
           ▼
  Cloud Run: cr-indec-downloader (privado)
      ├─ Recibe JSON (ej: "IPC" o "IPIM")
      ├─ Descarga CSV (maneja encoding latin-1 → utf-8)
      ├─ Guarda en GCS RAW: gs://tgs-sandbox-raw/[carpeta]/... (ej: /ipc/ o /ipim/)
      └─ Pub/Sub topic: raw.done {codigo_descarga, gcs_uri, nombre_procedure_gold}
           │
           ▼ (Trigger Eventarc)
  Cloud Function: cf-indec-silver-transformer (trigger: raw.done)
      ├─ Lee atributos (ej: "IPC")
      ├─ **Router Lógico**:
      │   ├─ Si "IPC": Parsea CSV de IPC (Filtra "NIVEL GENERAL", "Nacional")
      │   └─ Si "IPIM": Parsea CSV de IPIM (Filtra "ng_nivel_general")
      ├─ Extrae (anio, mes, valor)
      ├─ Busca (max_anio, max_mes) del lote
      ├─ Inserta en BQ Silver (Unificado): tgs_sandbox_curated.indec_ipc
      └─ Pub/Sub topic: curated.done {codigo_descarga, nombre_procedure_gold, max_anio, max_mes}
           │
           ▼ (Trigger Eventarc)
  Cloud Function: cf-indec-gold-trigger (trigger: curated.done)
      ├─ Lee atributos (ej: "IPC", "2024", "10")
      └─ CALL BQ SP: ds_datos_tableros.sp_merge_lkp_indices_ajuste(codigo_descarga)
           │
           ▼
  BigQuery: MERGE → ds_datos_tableros.lkp_indices_ajuste
      ├─ Fuente: tgs_sandbox_curated.indec_ipc (filtrada por `archivo = codigo_descarga`)
      ├─ Clave Lógica: (indices_id_indice, anio, mes)
      └─ Resultado: indices_id_indice = "IPC" o "IPIM" (desde el SP)
           │
           └─ (Al éxito) CF Gold publica en Pub/Sub topic: gold.done {codigo_descarga, anio, mes}
                │
                ▼ (Trigger Eventarc)
  Cloud Function: cf-indec-cuadro-tarifario (trigger: gold.done)
      ├─ Lee atributos (ej: "IPC", "2024", "10")
      ├─ **1. Validación (SELECT EXISTS)**:
      │   ├─ lkp_indices_ajuste (para anio/mes/codigo)
      │   ├─ lkp_demanda (para anio/mes)
      │   ├─ lkp_escalones (para anio/mes)
      │   └─ lkp_gas_retenido (para anio/mes)
      │
      ├─ **2. Ejecución (Solo si 1. es OK)**:
      │   ├─ CALL ds_datos_tableros.sp_merge_ft_ajustes()
      │   ├─ CALL ds_datos_tableros.sp_merge_ft_marcha_calculo()
      │   └─ CALL ds_datos_tableros.sp_merge_ft_cuadro_tarifario()
      │
      └─ **3. Notificación Final**:
           └─ Pub/Sub topic: end.done {anio, mes}
```

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
