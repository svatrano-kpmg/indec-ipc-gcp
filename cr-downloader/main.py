
# main.py
import os
import json
import logging
from datetime import datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import requests
from google.cloud import storage
from google.cloud import pubsub_v1
from functions_framework import http

# Logging detallado
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

BA_TZ = ZoneInfo("America/Argentina/Buenos_Aires")


def parse_bucket_and_prefix(value: str):
    """
    Acepta:
      - "raw-zone-lakehouse"
      - "raw-zone-lakehouse/indec/ipc/"
      - "gs://raw-zone-lakehouse/indec/ipc/"
    Devuelve (bucket, prefix_sin_slash_final).
    """
    v = (value or "").strip()
    if not v:
        raise ValueError("GCS_BUCKET vacío o no provisto.")

    if v.startswith("gs://"):
        v = v[5:]  # remove 'gs://'

    parts = v.split("/", 1)
    bucket = parts[0]
    prefix = ""
    if len(parts) > 1:
        prefix = parts[1].strip("/")
    return bucket, prefix


def filename_from_url(url: str, default_name: str = "downloaded_file.csv"):
    try:
        path = urlparse(url).path
        name = os.path.basename(path)
        return name if name else default_name
    except Exception:
        return default_name


@http
def run_indec_downloader(request):
    """
    Espera JSON:
    {
      "url_descarga": "https://www.indec.gob.ar/ftp/cuadros/economia/serie_ipc_divisiones.csv",
      "GCS_BUCKET": "raw-zone-lakehouse/indec/ipc/",
      "project_lake": "prj-data-lakehouse-dev",
      "codigo_descarga": "IPC",
      "nombre_procedure_gold": "xxxx"
    }
    Env vars requeridas en Cloud Run:
      - PUBSUB_PROJECT_ID: proyecto de Pub/Sub (ej: prj-data-process-dev)
      - PUBSUB_TOPIC_RAW: nombre del tópico raw (ej: raw.done)
    """
    # Parse del payload
    try:
        data = request.get_json(silent=True) or {}
    except Exception:
        try:
            data = json.loads(request.data.decode("utf-8"))
        except Exception:
            data = {}

    url = data.get("url_descarga")
    gcs_bucket_val = data.get("GCS_BUCKET")
    project_lake = data.get("project_lake")
    codigo_descarga = data.get("codigo_descarga")
    nombre_procedure_gold = data.get("nombre_procedure_gold")

    # Validaciones
    missing = [k for k in ["url_descarga", "GCS_BUCKET", "project_lake", "codigo_descarga", "nombre_procedure_gold"] if not data.get(k)]
    if missing:
        return (json.dumps({"error": f"Faltan campos en el payload: {', '.join(missing)}"}), 400, {"Content-Type": "application/json"})

    try:
        bucket_name, base_prefix = parse_bucket_and_prefix(gcs_bucket_val)
    except ValueError as e:
        return (json.dumps({"error": str(e)}), 400, {"Content-Type": "application/json"})

    run_project = os.getenv("GOOGLE_CLOUD_PROJECT", "desconocido")
    pubsub_project_id = os.getenv("PUBSUB_PROJECT_ID")
    pubsub_topic_raw = os.getenv("PUBSUB_TOPIC_RAW", "raw.done")

    if not pubsub_project_id:
        return (json.dumps({"error": "Falta env var 'PUBSUB_PROJECT_ID' en Cloud Run"}), 500, {"Content-Type": "application/json"})

    # Carpeta por día (BA): YYYYMMDD
    today_str = datetime.now(BA_TZ).strftime("%Y%m%d")
    prefix = "/".join([p for p in [base_prefix, today_str] if p])

    file_name = filename_from_url(url)

    # LOG: contexto y destino
    logging.info("=== INICIO ===")
    logging.info(f"Cloud Run (proyecto ejecución): {run_project}")
    logging.info(f"Proyecto destino (bucket): {project_lake}")
    logging.info(f"URL a descargar: {url}")
    logging.info(f"Archivo destino: {file_name}")
    logging.info(f"Bucket destino: {bucket_name}")
    logging.info(f"Prefijo destino: {prefix}")

    # Descarga
    try:
        logging.info("Iniciando descarga...")
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        content = resp.content
        content_type = resp.headers.get("Content-Type", "application/octet-stream")
        logging.info(f"Descarga exitosa. Tamaño: {len(content)} bytes. Content-Type: {content_type}")
    except Exception as e:
        logging.exception("Error descargando archivo")
        return (json.dumps({"error": f"Fallo al descargar: {str(e)}"}), 502, {"Content-Type": "application/json"})

    # Subida a GCS
    try:
        logging.info("Preparando subida a GCS...")
        storage_client = storage.Client(project=project_lake)  # proyecto del bucket
        bucket = storage_client.bucket(bucket_name)
        object_name = f"{prefix}/{file_name}" if prefix else file_name
        gcs_uri = f"gs://{bucket_name}/{object_name}"

        logging.info(f"Subiendo a {gcs_uri} (proyecto {project_lake})...")
        blob = bucket.blob(object_name)
        blob.upload_from_string(content, content_type=content_type)
        blob.reload()
        logging.info("Subida exitosa.")
        logging.info(f"Objeto final: {gcs_uri}")
        logging.info(f"Tamaño final: {blob.size} bytes | MD5: {blob.md5_hash}")

    except Exception as e:
        logging.exception("Error subiendo a GCS")
        return (json.dumps({"error": f"Fallo al subir a GCS: {str(e)}"}), 500, {"Content-Type": "application/json"})

    # Publicar mensaje en Pub/Sub raw.done (proyecto de proceso)
    try:
        logging.info(f"Publicando mensaje en Pub/Sub: {pubsub_project_id}/{pubsub_topic_raw} ...")
        publisher = pubsub_v1.PublisherClient()
        topic_path = publisher.topic_path(pubsub_project_id, pubsub_topic_raw)

        # Atributos: incluir TODO lo recibido + derivados necesarios para la silver
        # (cf-silver-transformer espera: codigo_descarga, gcs_uri, source_url, nombre_procedure_gold) [1](https://onedrive-global.kpmg.com/personal/sergiovatrano_kpmg_com_ar/Documents/Microsoft%20Copilot%20Chat%20Files/main.py)
        attributes = {
            "codigo_descarga": str(codigo_descarga),
            "nombre_procedure_gold": str(nombre_procedure_gold),
            "source_url": str(url),
            "gcs_uri": str(gcs_uri),
            # Extras útiles y que pediste incluir (todo el payload + contexto y metadata)
            "GCS_BUCKET": str(gcs_bucket_val),
            "bucket": str(bucket_name),
            "object_name": str(object_name),
            "prefix": str(base_prefix),
            "download_date": str(today_str),
            "content_type": str(content_type),
            "size_bytes": str(blob.size),
            "md5_hash_b64": str(blob.md5_hash),
            "project_lake": str(project_lake),
            "run_project": str(run_project),
            "pubsub_project": str(pubsub_project_id),
            "timestamp_ba": datetime.now(BA_TZ).isoformat(timespec="seconds"),
        }

        future = publisher.publish(
            topic_path,
            data=b"Raw download complete",
            **attributes
        )
        message_id = future.result()
        logging.info(f"Mensaje publicado en {pubsub_topic_raw} (ID: {message_id})")
    except Exception as e:
        logging.exception("Error publicando en Pub/Sub raw.done")
        # No cortar el flujo si la subida a GCS fue correcta; devolver 207 Multi-Status podría ser otra opción.
        return (json.dumps({"error": f"Subida OK pero fallo Pub/Sub: {str(e)}", "gcs_uri": gcs_uri}), 500, {"Content-Type": "application/json"})

    # Respuesta
    result = {
        "bucket": bucket_name,
        "object_name": object_name,
        "size_bytes": blob.size,
        "md5_hash_b64": blob.md5_hash,
        "content_type": content_type,
        "download_url": gcs_uri,
        "pubsub_topic": f"projects/{pubsub_project_id}/topics/{pubsub_topic_raw}",
        "message_id": message_id
    }

    logging.info("=== FIN: PROCESO COMPLETADO ===")
    return (json.dumps(result), 200, {"Content-Type": "application/json"})


@http
def healthz(request):
    return ("ok", 200, {"Content-Type": "text/plain"})
