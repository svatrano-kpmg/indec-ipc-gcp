from flask import Flask, request, jsonify
from google.cloud import storage, pubsub_v1
import os, requests, json
from datetime import datetime, timedelta

app = Flask(__name__)

PROJECT_ID = os.environ.get("PROJECT_ID")
RAW_BUCKET = os.environ.get("RAW_BUCKET")            # tgs-sandbox-raw
TOPIC_RAW_DONE = os.environ.get("TOPIC_RAW_DONE")    # raw.done
BASE_URL = "https://www.indec.gob.ar/ftp/cuadros/economia"

publisher = pubsub_v1.PublisherClient()
storage_client = storage.Client()

def compute_period(target: str | None):
    """
    target opcional: 'YYYY-MM' o 'YY-MM'. Si no viene, usa mes anterior.
    """
    if target:
        parts = target.split("-")
        if len(parts[0]) == 4:
            yyyy, mm = int(parts[0]), int(parts[1])
        else:
            yyyy, mm = 2000 + int(parts[0]), int(parts[1])
    else:
        today = datetime.utcnow()
        first = today.replace(day=1)
        prev = first - timedelta(days=1)
        yyyy, mm = prev.year, prev.month
    MM = f"{mm:02d}"
    YY = f"{yyyy % 100:02d}"
    return yyyy, mm, MM, YY

@app.route("/run", methods=["GET"])
def run():
    period = request.args.get("period")
    yyyy, mm, MM, YY = compute_period(period)

    filename = f"sh_ipc_{MM}_{YY}.xls"
    url = f"{BASE_URL}/{filename}"

    resp = requests.get(url, timeout=60)
    if resp.status_code != 200:
        return jsonify({"status": "error", "message": f"No se pudo descargar {url}", "code": resp.status_code}), 404

    bucket = storage_client.bucket(RAW_BUCKET)
    gcs_path = f"indec/ipc/{yyyy}/{MM}/{filename}"
    blob = bucket.blob(gcs_path)
    blob.upload_from_string(resp.content, content_type="application/vnd.ms-excel")
    gcs_uri = f"gs://{RAW_BUCKET}/{gcs_path}"

    message = {
        "project_id": PROJECT_ID,
        "gcs_uri": gcs_uri,
        "archivo": filename,
        "anio": yyyy,
        "mes": mm,
        "source_url": url
    }
    topic_path = publisher.topic_path(PROJECT_ID, TOPIC_RAW_DONE)
    publisher.publish(topic_path, data=json.dumps(message).encode("utf-8")).result(30)

    return jsonify({"status": "ok", "gcs_uri": gcs_uri, "published_to": TOPIC_RAW_DONE, "source_url": url}), 200

@app.route("/healthz", methods=["GET"])
def healthz():
    return "ok", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
