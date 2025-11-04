# Contenido de cf-gold-trigger/main.py
import os
import functions_framework
from google.cloud import bigquery, pubsub_v1

PROJECT_ID = os.environ.get("PROJECT_ID")
BQ_LOCATION = os.environ.get("BQ_LOCATION")
PUB_SUB_TOPIC_OUT = os.environ.get("PUB SUB_TOPIC_OUT") # ej: gold.done

bq_client = bigquery.Client(project=PROJECT_ID, location=BQ_LOCATION)
publisher = pubsub_v1.PublisherClient()
topic_path_out = publisher.topic_path(PROJECT_ID, PUB_SUB_TOPIC_OUT)

@functions_framework.cloud_event
def call_gold_sp(cloud_event):
    codigo = "UNKNOWN"
    max_anio_str = "UNKNOWN"
    max_mes_str = "UNKNOWN"
    
    try:
        attributes = cloud_event.data["message"]["attributes"]
        codigo = attributes.get("codigo_descarga")
        sp_name = attributes.get("nombre_procedure_gold")
        max_anio_str = attributes.get("max_anio")
        max_mes_str = attributes.get("max_mes")

        if not all([codigo, sp_name, max_anio_str, max_mes_str]):
            raise ValueError(f"Mensaje incompleto (faltan max_anio/mes). Recibido: {attributes}")

        print(f"[{codigo}] Invocando SP: {sp_name} con parámetro: {codigo}")
        
        if len(sp_name.split('.')) != 2:
             raise ValueError(f"Nombre de SP inválido: {sp_name}")
        
        sql_call = f"CALL `{PROJECT_ID}.{sp_name}`('{codigo}');"
        job = bq_client.query(sql_call)
        job.result() 

        print(f"[{codigo}] SP ejecutado. Job ID: {job.job_id}. Filas afectadas: {job.num_dml_affected_rows}")

        # Publicar en gold.done
        future = publisher.publish(
            topic_path_out,
            b"Gold SP executed successfully",
            codigo_descarga=codigo,
            anio=max_anio_str,
            mes=max_mes_str
        )
        print(f"[{codigo}] Mensaje publicado en {PUB_SUB_TOPIC_OUT} (ID: {future.get()})")

    except Exception as e:
        print(f"Error en 'call_gold_sp' para {codigo} (Período: {max_anio_str}-{max_mes_str}): {e}")
        raise