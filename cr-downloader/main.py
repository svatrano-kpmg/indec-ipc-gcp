
import os
import io
import json
import logging
from datetime import datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import requests
from google.cloud import storage
from functions_framework import http

logging.basicConfig(level=logging.INFO)
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
    Handler HTTP para Cloud Run via functions_framework.

    Espera JSON:
    {
      "url_descarga": "https://www.indec.gob.ar/ftp/cuadros/economia/serie_ipc_divisiones.csv",
      "GCS_BUCKET": "raw-zone-lakehouse/indec/ipc/"
    }

    Respuesta JSON con metadata del objeto subido.
    """
    try:
        data = request.get_json(silent=True) or {}
    except Exception:
        # fallback para payload como texto
        try:
            data = json.loads(request.data.decode("utf-8"))
        except Exception:
            data = {}

    url = data.get("url_descarga")
    gcs_bucket_val = data.get("GCS_BUCKET")

    if not url:
        return (json.dumps({"error": "Falta 'url_descarga' en el payload"}), 400, {"Content-Type": "application/json"})
    if not gcs_bucket_val:
        return (json.dumps({"error": "Falta 'GCS_BUCKET' en el payload"}), 400, {"Content-Type": "application/json"})

    try:
        bucket_name, base_prefix = parse_bucket_and_prefix(gcs_bucket_val)
    except ValueError as e:
        return (json.dumps({"error": str(e)}), 400, {"Content-Type": "application/json"})

    # Carpeta por día: YYYYMMDD (timezone BA)
    today_str = datetime.now(BA_TZ).strftime("%Y%m%d")
    prefix = "/".join([p for p in [base_prefix, today_str] if p])

    file_name = filename_from_url(url)

    # Descarga
    try:
        logging.info(f"Descargando: {url}")
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        content = resp.content
        content_type = resp.headers.get("Content-Type", "application/octet-stream")
    except Exception as e:
        logging.exception("Error descargando archivo")
        return (json.dumps({"error": f"Fallo al descargar: {str(e)}"}), 502, {"Content-Type": "application/json"})

    # Subida a GCS
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        object_name = f"{prefix}/{file_name}" if prefix else file_name
        blob = bucket.blob(object_name)

        blob.upload_from_string(content, content_type=content_type)
        blob.reload()

        result = {
            "bucket": bucket_name,
            "object_name": object_name,
            "size_bytes": blob.size,
            "md5_hash_b64": blob.md5_hash,
            "content_type": content_type,
            "download_url": f"gs://{bucket_name}/{object_name}",
        }
        logging.info(f"Subido a: gs://{bucket_name}/{object_name} ({blob.size} bytes)")

        return (json.dumps(result), 200, {"Content-Type": "application/json"})
    except Exception as e:
        logging.exception("Error subiendo a GCS")
        return (json.dumps({"error": f"Fallo al subir a GCS: {str(e)}"}), 500, {"Content-Type": "application/json"})


@http
def healthz(request):
    return ("ok", 200, {"Content-Type": "text/plain"})
