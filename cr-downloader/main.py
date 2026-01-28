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
      "nombre_procedure_gold": "xxxx",
      "pubsub_project_id" : "prj-data-process-dev",      
      "pubsub_topic_raw" : "raw.done"
      }

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
    pubsub_project_id = data.get("pubsub_project_id")
    pubsub_topic_raw = data.get("pubsub_topic_raw")

    # Validaciones
    missing = [k for k in ["url_descarga", "GCS_BUCKET", "project_lake", "codigo_descarga", "nombre_procedure_gold","pubsub_project_id","pubsub_topic_raw" ] if not data.get(k)]
    if missing:
        return (json.dumps({"error": f"Faltan campos en el payload: {', '.join(missing)}"}), 400, {"Content-Type": "application/json"})

    try:
        bucket_name, base_prefix = parse_bucket_and_prefix(gcs_bucket_val)
    except ValueError as e:
        return (json.dumps({"error": str(e)}), 400, {"Content-Type": "application/json"})

    run_project = os.getenv("GOOGLE_CLOUD_PROJECT", "desconocido")
#    pubsub_project_id = os.getenv("PUBSUB_PROJECT_ID")
#    pubsub_topic_raw = os.getenv("PUBSUB_TOPIC_RAW", "raw.done")

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
        
        resp = requests.get(url, verify=false, timeout=60) 
        resp.raise_for_status()
        raw_bytes = resp.content
        src_content_type = resp.headers.get("Content-Type", "application/octet-stream")
        logging.info(f"Descarga exitosa. Bytes: {len(raw_bytes)}. Content-Type origen: {src_content_type}")
    except Exception as e:
        logging.exception("Error descargando archivo")
        return (json.dumps({"error": f"Fallo al descargar: {str(e)}"}), 502, {"Content-Type": "application/json"})

    # Determinar si es JSON (no normalizar como CSV)
    is_json = "application/json" in (src_content_type or "").lower() or (url.lower().endswith(".json"))

    if is_json:
        # Normalizar JSON a UTF-8 sin tocar contenido (solo aseguramos bytes UTF-8)
        try:
            # Si son bytes UTF-8 válidos, esto no cambia nada; si vinieran en latin-1 (no usual para JSON),
            # intentamos decode->encode con fallback básico.
            try:
                text = raw_bytes.decode("utf-8")
                used_encoding = "utf-8"
            except UnicodeDecodeError:
                text = raw_bytes.decode("latin-1")
                used_encoding = "latin-1"
            normalized_bytes = text.encode("utf-8")
            applied_encoding = f"{used_encoding}→utf-8"
        except Exception as e:
            logging.exception("Error normalizando JSON a UTF-8")
            return (json.dumps({"error": f"Fallo al normalizar JSON: {str(e)}"}), 500, {"Content-Type": "application/json"})
        content_type = "application/json; charset=utf-8"

        # Si el nombre no tiene extensión, forzamos .json
        if not file_name.lower().endswith(".json"):
            # Si la URL del BCRA termina en /Cotizaciones, dame un nombre lógico
            base = os.path.splitext(file_name)[0] or "Cotizaciones"
            file_name = f"{base}.json"

    else:
        # Normalización de encoding a UTF-8 (simplificado)
        try:
            normalized_bytes = raw_bytes.decode("utf-8").encode("utf-8")
            applied_encoding = "utf-8"
            logging.info("Archivo decodificado como UTF-8 correctamente.")
        except UnicodeDecodeError:
            logging.info("Contenido no es UTF-8. Intentando Latin-1 → UTF-8...")
            normalized_bytes = raw_bytes.decode("latin-1").encode("utf-8")
            applied_encoding = "latin-1→utf-8"
            logging.info("Conversión exitosa (Latin-1 → UTF-8).")
    
    # Forzar content-type final como UTF-8
    content_type = "text/csv; charset=utf-8"

    # Subida a GCS
    try:
        logging.info("Preparando subida a GCS...")
        storage_client = storage.Client(project=project_lake)  # proyecto del bucket
        bucket = storage_client.bucket(bucket_name)
        object_name = f"{prefix}/{file_name}" if prefix else file_name
        gcs_uri = f"gs://{bucket_name}/{object_name}"

        logging.info(f"Subiendo a {gcs_uri} (proyecto {project_lake})...")
        blob = bucket.blob(object_name)
        blob.upload_from_string(normalized_bytes, content_type=content_type)
        blob.reload()
        logging.info("Subida exitosa.")
        logging.info(f"Objeto final: {gcs_uri} | Tamaño: {blob.size} bytes | MD5: {blob.md5_hash} | Encoding aplicado: {applied_encoding}")
    except Exception as e:
        logging.exception("Error subiendo a GCS")
        return (json.dumps({"error": f"Fallo al subir a GCS: {str(e)}"}), 500, {"Content-Type": "application/json"})

    # Publicar mensaje en Pub/Sub raw.done (proyecto de proceso)
    try:
        logging.info(f"Publicando mensaje en Pub/Sub: {pubsub_project_id}/{pubsub_topic_raw} ...")
        publisher = pubsub_v1.PublisherClient()
        topic_path = publisher.topic_path(pubsub_project_id, pubsub_topic_raw)

        # Atributos: incluir todo lo recibido + derivados (cf-silver-transformer consume estos claves)
        attributes = {
            "status": "success",
            "codigo_descarga": str(codigo_descarga),
            "nombre_procedure_gold": str(nombre_procedure_gold),
            "source_url": str(url),
            "gcs_uri": str(gcs_uri),

            # Payload original y metadatos útiles
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
            "encoding_applied": applied_encoding,
        }

        future = publisher.publish(
            topic_path,
            data=b"Raw download complete (UTF-8 normalized)",
            **attributes
        )
        message_id = future.result()
        logging.info(f"Mensaje publicado en {pubsub_topic_raw} (ID: {message_id})")
    except Exception as e:
        logging.exception("Error publicando en Pub/Sub raw.done")
        return (json.dumps({"error": f"Subida OK pero fallo Pub/Sub: {str(e)}", "gcs_uri": gcs_uri}), 500, {"Content-Type": "application/json"})

    # Respuesta
    result = {
        "bucket": bucket_name,
        "object_name": object_name,
        "size_bytes": blob.size,
        "md5_hash_b64": blob.md5_hash,
        "content_type": content_type,
        "download_url": gcs_uri,
        "encoding_applied": applied_encoding,
        "pubsub_topic": f"projects/{pubsub_project_id}/topics/{pubsub_topic_raw}",
        "message_id": message_id
    }

    logging.info("=== FIN: PROCESO COMPLETADO ===")
    return (json.dumps(result), 200, {"Content-Type": "application/json"})

@http
def healthz(request):
    return ("ok", 200, {"Content-Type": "text/plain"})
