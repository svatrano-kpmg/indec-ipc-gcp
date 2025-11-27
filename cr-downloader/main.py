
import os
import functions_framework
import requests
from google.cloud import pubsub_v1, storage
from datetime import datetime

PROJECT_ID = os.environ.get("PROJECT_ID")
GCS_BUCKET = os.environ.get("GCS_BUCKET")
PUB_SUB_TOPIC = os.environ.get("PUB_SUB_TOPIC")  # ej: raw.done

@functions_framework.http
def download_and_publish(request):
    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(PROJECT_ID, PUB_SUB_TOPIC)
    storage_client = storage.Client(project=PROJECT_ID)

    try:
        data = request.get_json(silent=True)
        if not data:
            return ("No JSON payload received.", 400)

        # Validación de parámetros
        required = ["codigo_descarga", "url_descarga", "nombre_carpeta_gcs", "nombre_procedure_gold"]
        missing = [k for k in required if k not in data]
        if missing:
            return (f"Faltan parámetros en el payload: {', '.join(missing)}", 400)

        # Parámetros recibidos del Scheduler
        codigo = data["codigo_descarga"]
        url = data["url_descarga"]
        folder = data["nombre_carpeta_gcs"]
        sp_gold = data["nombre_procedure_gold"]

        print(f"[{codigo}] Iniciando descarga desde: {url}")
        r = requests.get(url, timeout=60)
        r.raise_for_status()

        # INDEC suele publicar latin-1; convertir a UTF-8 con fallback
        raw = r.content
        try:
            text = raw.decode("latin-1")
        except UnicodeDecodeError:
            text = raw.decode(r.encoding or "utf-8", errors="replace")
        content = text.encode("utf-8")

        filename_original = url.split("/")[-1]
        datestamp = datetime.now().strftime("%Y-%m-%d")

        # Subir a Cloud Storage
        print(f"[{codigo}] Guardando en GCS (bucket: {GCS_BUCKET}, carpeta: {folder})")
        bucket = storage_client.bucket(GCS_BUCKET)
        object_name = f"{folder}/{datestamp}_{filename_original}"
        blob = bucket.blob(object_name)
        blob.upload_from_string(content, content_type="text/csv; charset=utf-8")
        gcs_uri = f"gs://{GCS_BUCKET}/{object_name}"

        # Publicar en Pub/Sub
        print(f"[{codigo}] Publicando en topic: {PUB_SUB_TOPIC}")
        future = publisher.publish(
            topic_path,
            b"File downloaded successfully",
            codigo_descarga=str(codigo),
            nombre_procedure_gold=str(sp_gold),
            gcs_uri=gcs_uri,
            source_url=url
        )
        message_id = future.result(timeout=30)  # <-- corrección del error

        print(f"[{codigo}] Mensaje publicado (ID: {message_id})")
        return ({
            "status": "OK",
            "codigo_descarga": codigo,
            "gcs_uri": gcs_uri,
            "pubsub_topic": PUB_SUB_TOPIC,
            "message_id": message_id
        }, 200)

    except requests.exceptions.RequestException as e:
        print(f"Error HTTP: {e}")
        return (f"Error al descargar {url}: {e}", 500)
    except Exception as e:
        print(f"Error: {e}")
        return (f"Error interno: {e}", 500)
