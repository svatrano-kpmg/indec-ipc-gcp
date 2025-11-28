import os
import sys
import argparse
import requests
from google.cloud import pubsub_v1, storage
from datetime import datetime

# Asume que las variables de entorno ya están configuradas en el entorno del Job de Dataproc
PROJECT_ID = os.environ.get("PROJECT_ID")
GCS_BUCKET = os.environ.get("GCS_BUCKET")
PUB_SUB_TOPIC = os.environ.get("PUB_SUB_TOPIC")

def download_and_publish(codigo, url, folder, sp_gold):
    """
    Función principal que ejecuta la lógica de descarga, subida a GCS y publicación en Pub/Sub.
    """
    if not all([PROJECT_ID, GCS_BUCKET, PUB_SUB_TOPIC]):
        print("Error: Las variables de entorno PROJECT_ID, GCS_BUCKET, o PUB_SUB_TOPIC no están configuradas.")
        sys.exit(1)

    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(PROJECT_ID, PUB_SUB_TOPIC)
    storage_client = storage.Client(project=PROJECT_ID)

    try:
        print(f"[{codigo}] Iniciando descarga desde: {url}")
        r = requests.get(url, timeout=60)
        r.raise_for_status()

        # Conversión de encoding
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
        message_id = future.result(timeout=30)

        print(f"[{codigo}] Mensaje publicado (ID: {message_id})")
        print(f"[{codigo}] Tarea completada con GCS URI: {gcs_uri}")

    except requests.exceptions.RequestException as e:
        print(f"Error HTTP al descargar {url}: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error interno: {e}")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Script para descargar, subir a GCS y publicar en Pub/Sub.")
    parser.add_argument("--codigo", required=True, help="Código de la descarga (ej: 123)")
    parser.add_argument("--url", required=True, help="URL del archivo a descargar")
    parser.add_argument("--folder", required=True, help="Nombre de la carpeta de destino en GCS")
    parser.add_argument("--sp_gold", required=True, help="Nombre del stored procedure gold")

    args = parser.parse_args()
    
    # Llamar a la función principal con los argumentos de línea de comandos
    download_and_publish(args.codigo, args.url, args.folder, args.sp_gold)