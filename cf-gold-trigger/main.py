import base64, json, os
from google.cloud import bigquery

PROJECT_ID = os.environ.get("PROJECT_ID")
PROC_FQN = os.environ.get("PROC_FQN", "tgs-sandbox.ds_datos_tableros.sp_merge_lkp_indices_ajuste")

bq = bigquery.Client()

def pubsub_handler(event, context=None):
    data_b64 = event["data"] if isinstance(event, dict) else event.data["message"]["data"]
    payload = json.loads(base64.b64decode(data_b64).decode("utf-8"))
    archivo = payload.get("archivo")
    if not archivo:
        raise ValueError("No se recibió 'archivo' en curated.done")

    query = f"CALL `{PROC_FQN}`(@p_archivo);"
    job = bq.query(query, job_config=bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("p_archivo", "STRING", archivo)]
    ))
    job.result()
