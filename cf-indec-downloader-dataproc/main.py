import functions_framework
from google.cloud import dataproc_v1 as dataproc
import os

# --- Variables de Entorno de la Cloud Function ---
PROJECT_ID = os.environ.get("PROJECT_ID")
REGION = os.environ.get("REGION") # Ej: us-central1
CLUSTER_NAME = "sqlserver-cluster"
SCRIPT_URI = os.environ.get("SCRIPT_URI") # Ej: gs://TU_BUCKET_DATAPROC/scripts/download_script.py
REQS_URI = os.environ.get("REQS_URI") # Ej: gs://TU_BUCKET_DATAPROC/scripts/requirements.txt
# --- Variables de Entorno para el Script de Dataproc ---
PUB_SUB_TOPIC = os.environ.get("PUB_SUB_TOPIC") 
GCS_BUCKET = os.environ.get("GCS_BUCKET")


@functions_framework.http
def launch_dataproc_job(request):
    """
    Recibe el payload del Cloud Scheduler y lanza un Job de PySpark en Dataproc.
    """
    try:
        data = request.get_json(silent=True)
        if not data:
            return ("No JSON payload received.", 400)

        # 1. Validación y Extracción de Parámetros del Payload
        required = ["codigo_descarga", "url_descarga", "nombre_carpeta_gcs", "nombre_procedure_gold"]
        missing = [k for k in required if k not in data]
        if missing:
            return (f"Faltan parámetros en el payload: {', '.join(missing)}", 400)

        codigo = data["codigo_descarga"]
        url = data["url_descarga"]
        folder = data["nombre_carpeta_gcs"]
        sp_gold = data["nombre_procedure_gold"]

        print(f"[{codigo}] Payload recibido. Preparando Job de Dataproc...")

        # 2. Configuración del Job
        job_client = dataproc.JobControllerClient(client_options={"api_endpoint": f"{REGION}-dataproc.googleapis.com:443"})

        # Los argumentos se pasan a download_script.py
        job_args = [
            f"--codigo={codigo}",
            f"--url={url}",
            f"--folder={folder}",
            f"--sp_gold={sp_gold}"
        ]

        # Configuración del Job de PySpark
        job = {
            "placement": {"cluster_name": CLUSTER_NAME},
            "pyspark_job": {
                "main_python_file_uri": SCRIPT_URI,
                "args": job_args,
                "file_uris": [REQS_URI],
                # Variables de entorno para el script dentro de Dataproc
                "properties": {
                    "spark.submit.deployMode": "client",
                    "PUB_SUB_TOPIC": PUB_SUB_TOPIC,
                    "GCS_BUCKET": GCS_BUCKET,
                    "PROJECT_ID": PROJECT_ID
                }
            },
            # Opcional: Nombre del job de Dataproc para fácil seguimiento
            "job_id": f"downloader-{codigo}-{datetime.now().strftime('%Y%m%d%H%M%S')}".lower()
        }

        # 3. Envío del Job a Dataproc
        operation = job_client.submit_job(
            project_id=PROJECT_ID, region=REGION, job=job
        )
        job_id = operation.job_id
        
        print(f"[{codigo}] Job de Dataproc enviado con ID: {job_id}")

        return ({
            "status": "Job submitted to Dataproc",
            "dataproc_job_id": job_id,
            "cluster": CLUSTER_NAME,
            "codigo_descarga": codigo
        }, 200)

    except Exception as e:
        print(f"Error al lanzar el Job de Dataproc: {e}")
        return (f"Error interno: {e}", 500)