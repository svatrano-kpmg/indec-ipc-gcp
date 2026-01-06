
import functions_framework
from google.cloud import dataproc_v1 as dataproc
import os
import logging
import traceback
from datetime import datetime

# -----------------------------
# Configuración de logging
# -----------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -----------------------------
# Variables de entorno
# -----------------------------
PROJECT_ID_LOC = os.environ.get("PROJECT_ID", "No definido")
DATAPROC_PROJECT_ID = os.environ.get("DATAPROC_PROJECT_ID", PROJECT_ID_LOC)
REGION = os.environ.get("REGION", "us-central1")
SCRIPT_URI = os.environ.get("SCRIPT_URI", "No definido")
REQS_URI = os.environ.get("REQS_URI", "")
PUB_SUB_TOPIC_PROJECT = os.environ.get("PUB_SUB_TOPIC_PROJECT", DATAPROC_PROJECT_ID)
GCS_BUCKET = os.environ.get("GCS_BUCKET", "No definido")
PUB_SUB_TOPIC = os.environ.get("PUB_SUB_TOPIC", "raw.done")

# Fijo: runtime Dataproc Serverless
RUNTIME_VERSION = "2.2"

# Service Account (igual que la CF)
BATCH_SERVICE_ACCOUNT = os.environ.get("BATCH_SERVICE_ACCOUNT", "")


def _batch_client():
    return dataproc.BatchControllerClient(
        client_options={"api_endpoint": f"{REGION}-dataproc.googleapis.com:443"}
    )


@functions_framework.http
def launch_dataproc_batch(request):
    """Launcher HTTP que envía un Dataproc Serverless Batch (PySpark)."""
    batch_id_ref = "unknown"
    try:
        logger.info("--- INICIO EJECUCIÓN LAUNCHER (SERVERLESS) ---")
        logger.info(f"Function Project: {PROJECT_ID_LOC}")
        logger.info(f"Target Project: {DATAPROC_PROJECT_ID}")
        logger.info(f"Región: {REGION}")

        # Leer payload
        data = request.get_json(silent=True)
        if not data:
            return ("No JSON payload received.", 400)

        logger.info(f"Payload recibido: {data}")

        required = [
            "codigo_descarga",
            "url_descarga",
            "nombre_carpeta_gcs",
            "nombre_procedure_gold",
        ]
        missing = [k for k in required if k not in data]
        if missing:
            return (f"Faltan parámetros: {', '.join(missing)}", 400)

        codigo = data["codigo_descarga"]

        # ID único para el batch
        batch_id_ref = f"downloader-{codigo}-{datetime.now().strftime('%Y%m%d%H%M%S')}".lower()

        # Argumentos para el script PySpark
        job_args = [
            f"--codigo={codigo}",
            f"--url={data['url_descarga']}",
            f"--folder={data['nombre_carpeta_gcs']}",
            f"--sp_gold={data['nombre_procedure_gold']}",
            f"--project_id={PUB_SUB_TOPIC_PROJECT}",
            f"--topic={PUB_SUB_TOPIC}",
            f"--bucket={GCS_BUCKET}",
        ]
        logger.info(f"Argumentos para el PySpark Batch: {job_args}")

        # Definición del batch
        batch = {
            "labels": {
                "codigo": "CT",
                "origen": "indec-launcher",
            },
            "pyspark_batch": {
                "main_python_file_uri": SCRIPT_URI,
                "args": job_args,
            },
            "runtime_config": {"version": RUNTIME_VERSION},
            "environment_config": {
                "execution_config": {
                    "service_account": BATCH_SERVICE_ACCOUNT
                }
            }
        }

        if REQS_URI:
            batch["pyspark_batch"]["python_file_uris"] = [REQS_URI]

        parent = f"projects/{DATAPROC_PROJECT_ID}/locations/{REGION}"
        batch_name = f"{parent}/batches/{batch_id_ref}"

        # Crear batch
        client = _batch_client()
        logger.info(f"Enviando create_batch. batch_id={batch_id_ref}")
        client.create_batch(parent=parent, batch=batch, batch_id=batch_id_ref)

        logger.info(f"Batch enviado exitosamente. Resource: {batch_name}")

        return (
            {
                "status": "Batch submitted",
                "batch_id": batch_id_ref,
                "batch_name": batch_name,
                "target_project": DATAPROC_PROJECT_ID,
                "region": REGION,
                "labels": batch["labels"],
            },
            200,
        )

    except Exception as e:
        error_msg = f"ERROR FATAL en Batch {batch_id_ref}: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        return (f"Error interno: {e}", 500)

----------------------


import functions_framework
from google.cloud import dataproc_v1 as dataproc
import os
import logging
import traceback
from datetime import datetime

# Configuración básica de logging
logging.basicConfig(level=logging.INFO)

PROJECT_ID_LOC = os.environ.get("PROJECT_ID", "No definido")
DATAPROC_PROJECT_ID = os.environ.get("DATAPROC_PROJECT_ID", "No definido")
REGION = os.environ.get("REGION", "us-central1")
SCRIPT_URI = os.environ.get("SCRIPT_URI", "No definido")
REQS_URI = os.environ.get("REQS_URI", "No definido")
PUB_SUB_TOPIC_PROJECT = os.environ.get("PUB_SUB_TOPIC_PROJECT", "No definido")
GCS_BUCKET = os.environ.get("GCS_BUCKET", "No definido")
PUB_SUB_TOPIC = os.environ.get("PUB_SUB_TOPIC", "raw.done")

@functions_framework.http
def launch_dataproc_job(request):
    """Launcher HTTP (Gen2) que envía un PySpark Job al cluster de Dataproc."""
    job_id_ref = "unknown"
    try:
        # 1) Log inicial de contexto
        logger.info("--- INICIO EJECUCIÓN LAUNCHER ---")
        logger.info(f"Contexto de Ejecución (Function Project): {PROJECT_ID_LOC}")
        logger.info(f"Objetivo Dataproc (Target Project): {DATAPROC_PROJECT_ID}")
        logger.info(f"Región: {REGION}")

        # 2) Leer y validar payload JSON
        data = request.get_json(silent=True)
        if not data:
            logger.error("No se recibió JSON payload")
            return ("No JSON payload received.", 400)

        logger.info(f"Payload recibido: {data}")

        required = [
            "codigo_descarga",
            "url_descarga",
            "nombre_carpeta_gcs",
            "nombre_procedure_gold",
            "cluster_name",
        ]
        missing = [k for k in required if k not in data]
        if missing:
            msg = f"Faltan parámetros: {', '.join(missing)}"
            logger.error(msg)
            return (msg, 400)

        codigo = data["codigo_descarga"]
        cluster_name = data["cluster_name"]

        # 3) Generar ID amigable para trazabilidad local (solo logging)
        job_id_ref = f"downloader-{codigo}-{datetime.now().strftime('%Y%m%d%H%M%S')}".lower()
        logger.info(f"Preparando Job ID local (referencia): {job_id_ref}")
        logger.info(
            f"Intentando conectar al cluster: '{cluster_name}' en proyecto '{DATAPROC_PROJECT_ID}'"
        )

        # 4) Crear cliente de Dataproc apuntando a la región
        try:
            job_client = dataproc.JobControllerClient(
                client_options={"api_endpoint": f"{REGION}-dataproc.googleapis.com:443"}
            )
        except Exception as e:
            logger.critical(f"Error al crear cliente Dataproc: {e}")
            raise

        # 5) Construir argumentos para el script del worker
        job_args = [
            f"--codigo={codigo}",
            f"--url={data['url_descarga']}",
            f"--folder={data['nombre_carpeta_gcs']}",
            f"--sp_gold={data['nombre_procedure_gold']}",
            f"--project_id={PUB_SUB_TOPIC_PROJECT}",
            f"--topic={PUB_SUB_TOPIC}",
            f"--bucket={GCS_BUCKET}",
        ]
        logger.info(f"Argumentos para el script: {job_args}")

        # 6) Definir el Job de Dataproc (sin job_id en el payload)
        job = {
            "placement": {"cluster_name": cluster_name},
            "pyspark_job": {
                "main_python_file_uri": SCRIPT_URI,
                "args": job_args,
                # Dependencias Python (si aplican). Puede ser .py, .zip, .egg, .whl
                # Si REQS_URI no está configurado, evitamos pasar una ruta "No definido".
                **(
                    {"python_file_uris": [REQS_URI]}
                    if REQS_URI and REQS_URI != "No definido"
                    else {}
                ),
                "properties": {
                    # Si necesitás modo cluster, podés ajustar esto en el script y configuración del cluster
                    "spark.submit.deployMode": "client"
                },
            },
            # Labels solicitados
            "labels": {
                "codigo": "indec-launcher",
                "origen": "ctrl-tarifario",
            },
        }

        # 7) Submit simple del Job (retorna un Job)
        logger.info("Enviando solicitud submit_job a la API de GCP...")
        response = job_client.submit_job(
            project_id=DATAPROC_PROJECT_ID,
            region=REGION,
            job=job,
        )

        # 8) Log y respuesta
        job_id = getattr(getattr(response, "reference", None), "job_id", None)
        logger.info(f"Job enviado exitosamente. Job ID: {job_id}")

        return (
            {
                "status": "Job submitted",
                "job_id": job_id,
                "cluster": cluster_name,
                "target_project": DATAPROC_PROJECT_ID,
                "labels": job.get("labels"),
            },
            200,
        )

    except Exception as e:
        # 9) Manejo de errores con stack trace
        error_msg = f"ERROR FATAL en Job {job_id_ref}: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        return (f"Error interno: {e}", 500)
logger = logging.getLogger(__name__)
