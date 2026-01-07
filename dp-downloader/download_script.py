import os
import sys
import argparse
import requests
from google.cloud import pubsub_v1, storage
from datetime import datetime

def download_and_publish(args):
    """
    Función principal que ejecuta la lógica de descarga, subida a GCS y publicación en Pub/Sub.
    Recibe un objeto args con todos los parámetros necesarios.
    """
    # Desempaquetar argumentos de infraestructura y negocio
    project_id = args.project_id
    bucket_name = args.bucket
    topic_name = args.topic
    codigo = args.codigo
    url = args.url
    folder = args.folder
    sp_gold = args.sp_gold

    # Validación básica (aunque argparse required=True ya maneja la mayoría)
    if not all([project_id, bucket_name, topic_name]):
        print("Error: Faltan argumentos de infraestructura (project_id, bucket, o topic).")
        sys.exit(1)

    # Inicializar clientes de GCP
    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(project_id, topic_name)
    storage_client = storage.Client(project=project_id)

    try:
        # 1. Descarga del archivo
        print(f"[{codigo}] Iniciando descarga desde: {url}")
        r = requests.get(url, timeout=60)
        r.raise_for_status()

        # 2. Manejo de codificación (latin-1 a utf-8)
        raw = r.content
        try:
            text = raw.decode("latin-1")
        except UnicodeDecodeError:
            text = raw.decode(r.encoding or "utf-8", errors="replace")
        content = text.encode("utf-8")

        # 3. Preparar nombre y ruta en GCS
        filename_original = url.split("/")[-1]
        datestamp = datetime.now().strftime("%Y-%m-%d")
        
        print(f"[{codigo}] Guardando en GCS (bucket: {bucket_name}, carpeta: {folder})")
        bucket = storage_client.bucket(bucket_name)
        object_name = f"{folder}/{datestamp}_{filename_original}"
        blob = bucket.blob(object_name)
        
        # 4. Subir archivo a GCS
        blob.upload_from_string(content, content_type="text/csv; charset=utf-8")
        gcs_uri = f"gs://{bucket_name}/{object_name}"

        # 5. Publicar mensaje de finalización en Pub/Sub
        print(f"[{codigo}] Publicando en topic: {topic_name}")
        future = publisher.publish(
            topic_path,
            b"File downloaded successfully",
            codigo_descarga=str(codigo),
            nombre_procedure_gold=str(sp_gold),
            gcs_uri=gcs_uri,
            source_url=url
        )
        message_id = future.result(timeout=30)

        print(f"[{codigo}] Mensaje publicado exitosamente (ID: {message_id})")
        print(f"[{codigo}] Tarea completada. Archivo disponible en: {gcs_uri}")

    except requests.exceptions.RequestException as e:
        print(f"Error HTTP al descargar {url}: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error interno durante la ejecución: {e}")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Script Worker de Dataproc para descarga y publicación.")
    
    # --- Argumentos de Negocio (del Scheduler) ---
    parser.add_argument("--codigo", required=True, help="Código identificador de la descarga (ej: IPC, IPIM)")
    parser.add_argument("--url", required=True, help="URL pública del archivo a descargar")
    parser.add_argument("--folder", required=True, help="Carpeta destino dentro del bucket Raw")
    parser.add_argument("--sp_gold", required=True, help="Nombre del Stored Procedure a ejecutar en capa Gold")
    
    # --- Argumentos de Infraestructura (Pasados por el Launcher) ---
    parser.add_argument("--project_id", required=True, help="ID del proyecto de Google Cloud")
    parser.add_argument("--topic", required=True, help="Nombre del Tópico Pub/Sub para notificar (raw.done)")
    parser.add_argument("--bucket", required=True, help="Nombre del Bucket GCS para guardar los datos (Raw)")

    args = parser.parse_args()
    
    # Llamar a la función principal con los argumentos de línea de comandos
#    download_and_publish(args.codigo, args.url, args.folder, args.sp_gold, args.project_id, args.topic, args.bucket)
    download_and_publish(args)