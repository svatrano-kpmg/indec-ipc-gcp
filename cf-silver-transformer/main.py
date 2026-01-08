# Contenido de cf-silver-transformer/main.py
import os
import functions_framework
import pandas as pd
from google.cloud import bigquery, pubsub_v1
import gcsfs

PROJECT_ID = os.environ.get("PROJECT_ID")
BQ_DATASET = os.environ.get("BQ_DATASET") # ej: tgs_sandbox_curated
BQ_TABLE = os.environ.get("BQ_TABLE") # ej: indec_ipc
PUB_SUB_TOPIC_OUT = os.environ.get("PUB_SUB_TOPIC_OUT") # ej: curated.done
BQ_PROJECT_ID = os.environ.get("BQ_PROJECT_ID")

# Filtros (leídos desde variables de entorno)
FILTER_IPC_DESC = os.environ.get("FILTER_IPC_DESC", "NIVEL GENERAL")
FILTER_IPC_REGION = os.environ.get("FILTER_IPC_REGION", "Nacional")
FILTER_IPIM_APERTURA = os.environ.get("FILTER_IPIM_APERTURA", "ng_nivel_general")

# bq_client = bigquery.Client(project=PROJECT_ID)
# publisher = pubsub_v1.PublisherClient()
# topic_path_out = publisher.topic_path(PROJECT_ID, PUB_SUB_TOPIC_OUT)
# fs = gcsfs.GCSFileSystem(project=PROJECT_ID)

@functions_framework.cloud_event
def process_raw_to_silver(cloud_event):
    bq_client = bigquery.Client(project=BQ_PROJECT_ID)
    publisher = pubsub_v1.PublisherClient()
    topic_path_out = publisher.topic_path(PROJECT_ID, PUB_SUB_TOPIC_OUT)
    fs = gcsfs.GCSFileSystem(project=PROJECT_ID)
    try:
        attributes = cloud_event.data["message"]["attributes"]
        codigo = attributes.get("codigo_descarga")
        gcs_uri = attributes.get("gcs_uri")
        source_url = attributes.get("source_url")
        sp_gold = attributes.get("nombre_procedure_gold")

        if not all([codigo, gcs_uri, sp_gold]):
            raise ValueError(f"Mensaje incompleto. Faltan atributos. Recibido: {attributes}")

        print(f"[{codigo}] Procesando GCS: {gcs_uri}")

        with fs.open(gcs_uri, 'rb') as f:
            # Leemos como utf-8 (Cloud Run ya lo normalizó)
            df = pd.read_csv(f, encoding='utf-8', delimiter=';', decimal=',')
        
        print(f"[{codigo}] CSV leído. {len(df)} filas iniciales.")

        if codigo == "IPC":
            df_silver = transform_ipc(df)
        elif codigo == "IPIM":
            df_silver = transform_ipim(df)
        else:
            raise ValueError(f"Codigo de descarga no reconocido: {codigo}")

        df_silver["archivo"] = codigo
        df_silver["gcs_uri"] = gcs_uri
        df_silver["source_url"] = source_url
        df_silver["load_ts"] = pd.Timestamp.now(tz='UTC')
        
        n_rows = len(df_silver)
        if n_rows == 0:
            print(f"[{codigo}] No se encontraron filas que cumplan el filtro. Finalizando.")
            return

        print(f"[{codigo}] Transformación completa. {n_rows} filas para BQ.")
        
        # Encontrar período máximo del lote
        max_period_index = (df_silver['anio'] * 100 + df_silver['mes']).idxmax()
        max_anio = df_silver.loc[max_period_index, 'anio'].item()
        max_mes = df_silver.loc[max_period_index, 'mes'].item()
        print(f"[{codigo}] Período máximo detectado en el archivo: {max_anio}-{max_mes}")

        table_ref = f"{BQ_PROJECT_ID}.{BQ_DATASET}.{BQ_TABLE}"
        job_config = bigquery.LoadJobConfig(
            schema=[
                bigquery.SchemaField("periodo", "STRING"),
                bigquery.SchemaField("anio", "INTEGER"),
                bigquery.SchemaField("mes", "INTEGER"),
                bigquery.SchemaField("valor", "FLOAT"),
                bigquery.SchemaField("archivo", "STRING"),
                bigquery.SchemaField("gcs_uri", "STRING"),
                bigquery.SchemaField("source_url", "STRING"),
                bigquery.SchemaField("load_ts", "TIMESTAMP"),
            ],
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        )
        job = bq_client.load_table_from_dataframe(df_silver, table_ref, job_config=job_config)
        job.result()
        print(f"[{codigo}] Carga a BQ Silver completada. Job ID: {job.job_id}")

        future = publisher.publish(
            topic_path_out,
            b"Silver load complete",
            codigo_descarga=codigo,
            nombre_procedure_gold=sp_gold,
            gcs_uri=gcs_uri,
            n_rows=str(n_rows),
            max_anio=str(max_anio),
            max_mes=str(max_mes)
        )
        message_id = future.result()  # bloquea hasta que se publique
        print(f"[{codigo}] Mensaje publicado en {PUB_SUB_TOPIC_OUT} (ID: {message_id})")
        # print(f"[{codigo}] Mensaje publicado en {PUB_SUB_TOPIC_OUT} (ID: {future.get()})")

    except Exception as e:
        print(f"Error en 'process_raw_to_silver' para {gcs_uri}: {e}")
        return

def transform_ipc(df):
    # 1. Limpieza de nombres de columnas (ya lo tenía)
    df.columns = df.columns.str.strip().str.replace('í', 'i')
    # 2. *** Limpiar los valores de las celdas ***
    df["Descripcion"] = df["Descripcion"].str.strip()
    df["Region"] = df["Region"].str.strip()
    
    df_filtered = df[
        (df["Descripcion"] == FILTER_IPC_DESC) &
        (df["Region"] == FILTER_IPC_REGION)
    ].copy()
    df_filtered["periodo_str"] = df_filtered["Periodo"].astype(str)
    df_filtered["anio"] = df_filtered["periodo_str"].str[:4].astype(int)
    df_filtered["mes"] = df_filtered["periodo_str"].str[4:6].astype(int)
    df_final = df_filtered.rename(columns={"Indice_IPC": "valor", "periodo_str": "periodo"})
    return df_final[["periodo", "anio", "mes", "valor"]]

def transform_ipim(df):
    df.columns = df.columns.str.strip()
    df_filtered = df[(df["nivel_general_aperturas"] == FILTER_IPIM_APERTURA)].copy()
    df_filtered["dt"] = pd.to_datetime(df_filtered["periodo"])
    df_filtered["anio"] = df_filtered["dt"].dt.year
    df_filtered["mes"] = df_filtered["dt"].dt.month
    df_final = df_filtered.rename(columns={"indice_ipim": "valor"})
    return df_final[["periodo", "anio", "mes", "valor"]]