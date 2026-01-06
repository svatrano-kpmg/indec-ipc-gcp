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