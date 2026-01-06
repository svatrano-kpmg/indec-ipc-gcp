import functions_framework
from google.cloud import dataproc_v1 as dataproc
import os
import logging
import traceback
from datetime import datetime

# Configuración básica de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Variables de Entorno ---
PROJECT_ID_LOC = os.environ.get("PROJECT_ID", "No definido")
DATAPROC_PROJECT_ID = os.environ.get("DATAPROC_PROJECT_ID", "No definido")
REGION = os.environ.get("REGION", "us-central1")
SCRIPT_URI = os.environ.get("SCRIPT_URI", "No definido")
REQS_URI = os.environ.get("REQS_URI", "No definido")
PUB_SUB_TOPIC_PROJECT = os.environ.get("PUB_SUB_TOPIC_PROJECT", "No definido")
GCS_BUCKET = os.environ.get("GCS_BUCKET", "No definido")
PUB_SUB_TOPIC = os.environ.get("PUB_SUB_TOPIC","No definido") 

@functions_framework.http
def launch_dataproc_job(request):
    job_id_ref = "unknown"
    try:
        # 1. Log inicial de contexto
        logger.info(f"--- INICIO EJECUCIÓN LAUNCHER ---")
        logger.info(f"Contexto de Ejecución (Function Project): {PROJECT_ID_LOC}")
        logger.info(f"Objetivo Dataproc (Target Project): {DATAPROC_PROJECT_ID}")
        logger.info(f"Región: {REGION}")
        
        data = request.get_json(silent=True)
        if not data:
            logger.error("No se recibió JSON payload")
            return ("No JSON payload received.", 400)

        # 2. Log del Payload recibido
        logger.info(f"Payload recibido: {data}")

        required = ["codigo_descarga", "url_descarga", "nombre_carpeta_gcs", "nombre_procedure_gold", "cluster_name"]
        missing = [k for k in required if k not in data]
        if missing:
            msg = f"Faltan parámetros: {', '.join(missing)}"
            logger.error(msg)
            return (msg, 400)

        codigo = data["codigo_descarga"]
        cluster_name = data["cluster_name"]
        
        # Generar ID único para trazar
        job_id_ref = f"downloader-{codigo}-{datetime.now().strftime('%Y%m%d%H%M%S')}".lower()
        
        logger.info(f"Preparando Job ID: {job_id_ref}")
        logger.info(f"Intentando conectar al cluster: '{cluster_name}' en proyecto '{DATAPROC_PROJECT_ID}'")

        # 3. Creación del Cliente Dataproc
        try:
            job_client = dataproc.JobControllerClient(
                client_options={"api_endpoint": f"{REGION}-dataproc.googleapis.com:443"}
            )
        except Exception as e:
            logger.critical(f"Error al crear cliente Dataproc: {e}")
            raise

        job_args = [
            f"--codigo={codigo}",
            f"--url={data['url_descarga']}",
            f"--folder={data['nombre_carpeta_gcs']}",
            f"--sp_gold={data['nombre_procedure_gold']}",
            f"--project_id={PUB_SUB_TOPIC_PROJECT}", 
            f"--topic=raw.done",
            f"--bucket={GCS_BUCKET}"
        ]

        logger.info(f"Argumentos para el script: {job_args}")

        job = {
            "placement": {"cluster_name": cluster_name},
            "pyspark_job": {
                "main_python_file_uri": SCRIPT_URI,
                "args": job_args,
                "file_uris": [REQS_URI],
                "properties": {
                    "spark.submit.deployMode": "client"
                }
            },
            "job_id": job_id_ref
        }

        # 4. Envío del Job (Aquí es donde suele fallar)
        logger.info("Enviando solicitud submit_job a la API de GCP...")
        
        operation = job_client.submit_job(
            project_id=DATAPROC_PROJECT_ID, 
            region=REGION, 
            job=job
        )
        
        logger.info(f"Job enviado exitosamente. Operation ID: {operation.job_id}")
        
        return ({
            "status": "Job submitted",
            "job_id": operation.job_id,
            "cluster": cluster_name,
            "target_project": DATAPROC_PROJECT_ID
        }, 200)

    except Exception as e:
        # 5. Captura exhaustiva del error
        error_msg = f"ERROR FATAL en Job {job_id_ref}: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc()) # Imprime el stack trace completo en el log
        return (f"Error interno: {e}", 500)