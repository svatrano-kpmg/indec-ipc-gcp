# Contenido de cf-cuadro-tarifario/main.py
import os
import functions_framework
from google.cloud import bigquery, pubsub_v1

PROJECT_ID = os.environ.get("PROJECT_ID")
BQ_DATASET = os.environ.get("BQ_DATASET") # ej: ds_datos_tableros
BQ_LOCATION = os.environ.get("BQ_LOCATION")
PUB_SUB_TOPIC_OUT = os.environ.get("PUB_SUB_TOPIC_OUT") # ej: end.done

bq_client = bigquery.Client(project=PROJECT_ID, location=BQ_LOCATION)
publisher = pubsub_v1.PublisherClient()
topic_path_out = publisher.topic_path(PROJECT_ID, PUB_SUB_TOPIC_OUT)

# Configuración de validaciones
TABLES_TO_CHECK = {
    'lkp_indices_ajuste': 'indices_id_indice',
    'lkp_demanda': None,
    'lkp_escalones': None,
    'lkp_gas_retenido': None
}
# SPs a ejecutar en orden
SPS_TO_RUN = [
    'sp_merge_ft_ajustes',
    'sp_merge_ft_marcha_calculo',
    'sp_merge_ft_cuadro_tarifario'
]

@functions_framework.cloud_event
def check_and_run_cuadro_tarifario(cloud_event):
    try:
        attributes = cloud_event.data["message"]["attributes"]
        codigo = attributes.get("codigo_descarga")
        anio_str = attributes.get("anio")
        mes_str = attributes.get("mes")

        if not all([codigo, anio_str, mes_str]):
            raise ValueError(f"Mensaje incompleto. Faltan anio/mes/codigo. Recibido: {attributes}")

        anio = int(anio_str)
        mes = int(mes_str)
        print(f"Iniciando validación para Cuadro Tarifario (Índice: {codigo}, Período: {anio}-{mes})")

        all_data_ready = True
        for table_name, extra_filter_col in TABLES_TO_CHECK.items():
            if not check_data_exists(table_name, anio, mes, codigo, extra_filter_col):
                print(f"DATOS FALTANTES: No se encontraron datos en {table_name} para {anio}-{mes}")
                all_data_ready = False
                break
        
        if not all_data_ready:
            print(f"Validación fallida. No se ejecutarán los SPs. El pipe termina aquí para {anio}-{mes}.")
            return

        print(f"Validación exitosa: Todos los datos para {anio}-{mes} están presentes.")

        for sp in SPS_TO_RUN:
            sp_full_name = f"`{PROJECT_ID}.{BQ_DATASET}.{sp}`"
            print(f"Ejecutando SP: {sp_full_name}...")
            # Asumimos que los SPs no reciben parámetros.
            sql_call = f"CALL {sp_full_name}();" 
            job = bq_client.query(sql_call, location=BQ_LOCATION)
            job.result()
            print(f"SP {sp} completado. Job ID: {job.job_id}")

        future = publisher.publish(
            topic_path_out,
            b"Cuadro tarifario calculado",
            anio=str(anio),
            mes=str(mes)
        )
        print(f"Mensaje publicado en {PUB_SUB_TOPIC_OUT} (ID: {future.get()})")

    except Exception as e:
        print(f"Error en 'check_and_run_cuadro_tarifario' para {anio_str}-{mes_str}: {e}")
        raise

def check_data_exists(table_name, anio, mes, codigo, extra_filter_col=None):
    table_ref = f"`{PROJECT_ID}.{BQ_DATASET}.{table_name}`"
    
    params = [
            bigquery.ScalarQueryParameter("anio", "INT64", anio),
            bigquery.ScalarQueryParameter("mes", "INT64", mes),
        ]

    sql = f"SELECT EXISTS (SELECT 1 FROM {table_ref} WHERE anio = @anio AND mes = @mes"
    
    if extra_filter_col:
        if extra_filter_col == 'indices_id_indice':
            # Convertir 'IPC' a 1 y 'IPIM' a 2
            indice_id = 1 if codigo == 'IPC' else 2 if codigo == 'IPIM' else 0
            sql += f" AND {extra_filter_col} = @codigo_id"
            params.append(bigquery.ScalarQueryParameter("codigo_id", "INT64", indice_id))
        else:
            # Para otras tablas, el código es string
            sql += f" AND {extra_filter_col} = @codigo"
            params.append(bigquery.ScalarQueryParameter("codigo", "STRING", codigo))

    sql += ")"

    job_config = bigquery.QueryJobConfig(query_parameters=params)
    query_job = bq_client.query(sql, job_config=job_config, location=BQ_LOCATION)
    exists = [row[0] for row in query_job.result()][0]
    return exists