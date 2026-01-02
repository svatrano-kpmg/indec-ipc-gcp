import functions_framework
from google.cloud import dataproc_v1 as dataproc
import os
from datetime import datetime

# --- Variables de Entorno de la Cloud Function (Configuración propia) ---
PROJECT_ID = os.environ.get("PROJECT_ID")
REGION = os.environ.get("REGION")
SCRIPT_URI = os.environ.get("SCRIPT_URI")
REQS_URI = os.environ.get("REQS_URI")
# Estas variables las pasaremos como argumentos al script de Dataproc
PUB_SUB_TOPIC = os.environ.get("PUB_SUB_TOPIC") 
GCS_BUCKET = os.environ.get("GCS_BUCKET")
DATAPROC_PROJECT_ID = os.environ.get("DATAPROC_PROJECT_ID")

@functions_framework.http
def launch_dataproc_job(request):
    try:
        data = request.get_json(silent=True)
        if not data:
            return ("No JSON payload received.", 400)

        # 1. Extracción de Parámetros (Ahora incluye cluster_name)
        required = ["codigo_descarga", "url_descarga", "nombre_carpeta_gcs", "nombre_procedure_gold", "cluster_name"]
        missing = [k for k in required if k not in data]
        if missing:
            return (f"Faltan parámetros en el payload: {', '.join(missing)}", 400)

        codigo = data["codigo_descarga"]
        url = data["url_descarga"]
        folder = data["nombre_carpeta_gcs"]
        sp_gold = data["nombre_procedure_gold"]
        cluster_name = data["cluster_name"]  # <--- Nuevo: Viene del Scheduler

        print(f"[{codigo}] Preparando Job para cluster: {cluster_name}")

        job_client = dataproc.JobControllerClient(
            client_options={"api_endpoint": f"{REGION}-dataproc.googleapis.com:443"}
        )

        # 2. Argumentos explícitos para el script (Solución al punto C)
        # Se agregan --project_id, --topic y --bucket tomando los valores de la CF
        job_args = [
            f"--codigo={codigo}",
            f"--url={url}",
            f"--folder={folder}",
            f"--sp_gold={sp_gold}",
            f"--project_id={PROJECT_ID}",      # <--- Agregado
            f"--topic={PUB_SUB_TOPIC}",        # <--- Agregado
            f"--bucket={GCS_BUCKET}"           # <--- Agregado
        ]

        job = {
            "placement": {"cluster_name": cluster_name}, # <--- Usamos la variable
            "pyspark_job": {
                "main_python_file_uri": SCRIPT_URI,
                "args": job_args,
                "file_uris": [REQS_URI],
                "properties": {
                    "spark.submit.deployMode": "client"
                    # Ya no necesitamos pasar propiedades extra aquí
                }
            },
            "job_id": f"downloader-{codigo}-{datetime.now().strftime('%Y%m%d%H%M%S')}".lower()
        }

        operation = job_client.submit_job(
         project_id=DATAPROC_PROJECT_ID, # <--- CAMBIO: Usar el ID de INTAKE, no el local
         region=REGION, 
         job=job
        )        

        return ({
            "status": "Job submitted",
            "job_id": operation.job_id,
            "cluster": cluster_name
        }, 200)

    except Exception as e:
        print(f"Error: {e}")
        return (f"Error interno: {e}", 500)