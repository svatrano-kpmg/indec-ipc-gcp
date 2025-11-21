import os
import functions_framework
import requests
import gcsfs
import mimetypes
from google.cloud import pubsub_v1
from datetime import datetime

PROJECT_ID = os.environ.get("PROJECT_ID")
GCS_BUCKET = os.environ.get("GCS_BUCKET")
PUB_SUB_TOPIC = os.environ.get("PUB_SUB_TOPIC") # ej: raw.done

# publisher = pubsub_v1.PublisherClient()
# topic_path = publisher.topic_path(PROJECT_ID, PUB_SUB_TOPIC)
# fs = gcsfs.GCSFileSystem(project=PROJECT_ID)

@functions_framework.http
def download_and_publish(request):
    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(PROJECT_ID, PUB_SUB_TOPIC)
    fs = gcsfs.GCSFileSystem(project=PROJECT_ID)
    try:
        data = request.get_json(silent=True)
        if not data:
            return ("No JSON payload received.", 400)

        # Parámetros recibidos del Scheduler
        codigo = data["codigo_descarga"]
        url = data["url_descarga"]
        folder = data["nombre_carpeta_gcs"]
        sp_gold = data["nombre_procedure_gold"]

        print(f"[{codigo}] Iniciando descarga desde: {url}")
        r = requests.get(url)
        r.raise_for_status()
        
        # IMPORTANTE: INDEC usa latin-1. Decodificar y re-codificar a UTF-8
        content = r.content.decode('latin-1').encode('utf-8')
        
        filename_original = url.split('/')[-1]
        datestamp = datetime.now().strftime("%Y-%m-%d")
        gcs_path = f"{GCS_BUCKET}/{folder}/{datestamp}_{filename_original}"
        
        print(f"[{codigo}] Guardando en GCS: {gcs_path}")
        with fs.open(gcs_path, 'wb') as f:
            f.write(content)

        print(f"[{codigo}] Publicando en topic: {PUB_SUB_TOPIC}")
        future = publisher.publish(
            topic_path,
            b"File downloaded successfully",
            # Atributos: la clave del workflow
            codigo_descarga=codigo,
            nombre_procedure_gold=sp_gold,
            gcs_uri=f"gs://{gcs_path}",
            source_url=url
        )
        message_id = future.get()
        print(f"[{codigo}] Mensaje publicado (ID: {message_id})")
        
        return (f"Workflow iniciado para {codigo}. GCS: {gcs_path}", 200)

    except requests.exceptions.RequestException as e:
        print(f"Error HTTP: {e}")
        return (f"Error al descargar {url}: {e}", 500)
    except Exception as e:
        print(f"Error: {e}")
        return (f"Error interno: {e}", 500)