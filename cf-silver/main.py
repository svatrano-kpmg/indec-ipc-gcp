import base64, json, os, re, unicodedata, logging
from google.cloud import storage, bigquery, pubsub_v1
import xlrd  # v1.2.0 para .xls
from xlrd.xldate import xldate_as_datetime
from xlrd import XL_CELL_TEXT, XL_CELL_NUMBER, XL_CELL_DATE, XL_CELL_EMPTY

logging.getLogger().setLevel(logging.INFO)

# ---- Config env (human-friendly 1-based for rows/cols) ----
PROJECT_ID = os.environ.get("PROJECT_ID")

SILVER_DATASET = os.environ.get("SILVER_DATASET", "tgs_sandbox_curated")
SILVER_TABLE = os.environ.get("SILVER_TABLE", "indec_ipc")
TOPIC_CURATED_DONE = os.environ.get("TOPIC_CURATED_DONE", "curated.done")

HEADER_ROW_1B = int(os.environ.get("HEADER_ROW", "6"))     # fila períodos (Excel)
VALUE_ROW_1B  = int(os.environ.get("VALUE_ROW", "10"))     # fila "Nivel general" (Excel)
START_COL_1B  = int(os.environ.get("START_COL", "2"))      # 2 = columna B (Excel)
EMPTY_STREAK_LIMIT = int(os.environ.get("EMPTY_STREAK_LIMIT", "6"))

# Convertimos a índices 0-based para xlrd
HEADER_ROW = HEADER_ROW_1B - 1
VALUE_ROW  = VALUE_ROW_1B  - 1
START_COL  = START_COL_1B  - 1

storage_client = storage.Client()
bq_client = bigquery.Client()
publisher = pubsub_v1.PublisherClient()

MONTHS = {"ene":1,"feb":2,"mar":3,"abr":4,"may":5,"jun":6,"jul":7,"ago":8,"sep":9,"oct":10,"nov":11,"dic":12}
INV_MONTHS = {v:k for k,v in MONTHS.items()}

def normalize(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")

def periodo_str(anio:int, mes:int) -> str:
    return f"{INV_MONTHS[mes]}-{anio % 100:02d}"

def parse_period_from_text(text: str) -> tuple[int, int]:
    """
    Acepta:
      - mmm-yy / mmm-yyyy  (ej. dic-16 / dic-2016)
      - dd/mm/yyyy o mm/dd/yyyy (heurística: el día suele ser 01)
      - mm/yyyy, mm-yy, mm-yyyy
    Regla YY -> 2000+YY
    """
    t = normalize(text).replace(" ", "")
    # mmm-yy
    m = re.match(r"^([a-z]{3})-(\d{2}|\d{4})$", t)
    if m:
        mmm, yy = m.group(1), m.group(2)
        if mmm in MONTHS:
            mes = MONTHS[mmm]
            anio = int(yy) if len(yy)==4 else 2000+int(yy)
            return anio, mes

    # dd/mm/yyyy o mm/dd/yyyy
    m = re.match(r"^(\d{1,2})/-/-$", t)
    if m:
        a, b, ytxt = int(m.group(1)), int(m.group(2)), m.group(3)
        if 1 <= a <= 12 and b == 1:
            mes = a
        elif 1 <= b <= 12 and a == 1:
            mes = b
        else:
            mes = a if 1 <= a <= 12 else b
        anio = int(ytxt) if len(ytxt)==4 else 2000+int(ytxt)
        return anio, mes

    # mm/yyyy o mm-yy o mm-yyyy
    m = re.match(r"^(\d{1,2})/-$", t)
    if m:
        mes = int(m.group(1))
        ytxt = m.group(2)
        if 1 <= mes <= 12:
            anio = int(ytxt) if len(ytxt)==4 else 2000+int(ytxt)
            return anio, mes

    raise ValueError(f"Texto de periodo no reconocido: {text}")

def parse_period_cell(book, cell) -> tuple[int, int, str]:
    """
    Interpreta el encabezado de período desde una celda:
    - DATE o NUMBER (serial Excel): usa xldate_as_datetime
    - TEXT: intenta parsear con formatos conocidos
    Retorna (anio, mes, 'mmm-yy')
    """
    if cell.ctype in (XL_CELL_DATE, XL_CELL_NUMBER):
        try:
            dt = xldate_as_datetime(float(cell.value), book.datemode)
            anio, mes = dt.year, dt.month
            return anio, mes, periodo_str(anio, mes)
        except Exception:
            # Si NO era convertible a fecha (raro), probamos como texto
            pass

    if cell.ctype == XL_CELL_TEXT:
        anio, mes = parse_period_from_text(str(cell.value))
        return anio, mes, periodo_str(anio, mes)

    raise ValueError(f"Formato de periodo no reconocido: {cell.value} (ctype={cell.ctype})")

def read_sheet_from_gcs(gcs_uri: str) -> list[dict]:
    """
    Lee XLS desde GCS, toma la hoja que contenga 'Índices IPC Cobertura Nacional' (normalizada)
    y extrae (anio, mes, valor) usando posiciones fijas:
      - HEADER_ROW (1-based env, convertido a 0-based)
      - VALUE_ROW  (1-based env, convertido a 0-based)
      - START_COL  (1-based env, convertido a 0-based) = B por default
    Avanza columnas hasta encontrar EMPTY_STREAK_LIMIT encabezados vacíos seguidos.
    """
    assert gcs_uri.startswith("gs://")
    bucket_name, path = gcs_uri[5:].split("/", 1)

    contents = storage_client.bucket(bucket_name).blob(path).download_as_bytes()
    tmp = "/tmp/input.xls"
    with open(tmp, "wb") as f:
        f.write(contents)

    book = xlrd.open_workbook(tmp)

    # Buscar la hoja por nombre (con tolerancia a tildes)
    target = normalize("Índices IPC Cobertura Nacional")
    sheet = None
    for name in book.sheet_names():
        if target in normalize(name):
            sheet = book.sheet_by_name(name)
            break
    if sheet is None:
        raise RuntimeError("No se encontró la hoja 'Índices IPC Cobertura Nacional'.")

    if HEADER_ROW >= sheet.nrows or VALUE_ROW >= sheet.nrows:
        raise RuntimeError(f"HEADER_ROW ({HEADER_ROW_1B}) o VALUE_ROW ({VALUE_ROW_1B}) fuera de rango (nrows={sheet.nrows}).")

    rows = []
    empty_streak = 0

    # Diagnóstico: muestra 6 valores de encabezado desde START_COL
    diag = []
    for c in range(START_COL, min(sheet.ncols, START_COL + 6)):
        diag.append(str(sheet.cell(HEADER_ROW, c).value))
    logging.info(f"[Diagnóstico] Header row={HEADER_ROW_1B}, value row={VALUE_ROW_1B}, start col={START_COL_1B} | sample headers: {diag}")

    for c in range(START_COL, sheet.ncols):
        hcell = sheet.cell(HEADER_ROW, c)

        # corte por encabezados vacíos consecutivos
        if hcell.ctype == XL_CELL_EMPTY or str(hcell.value).strip() == "":
            empty_streak += 1
            if empty_streak >= EMPTY_STREAK_LIMIT:
                logging.info(f"Corte por {EMPTY_STREAK_LIMIT} encabezados vacíos consecutivos a partir de col={c+1}.")
                break
            continue
        else:
            empty_streak = 0

        # Parse período (con soporte DATE/NUMBER/TEXT)
        try:
            anio, mes, periodo_std = parse_period_cell(book, hcell)
        except Exception as e:
            logging.warning(f"No se pudo interpretar periodo en col={c+1}: val={hcell.value} ctype={hcell.ctype}. Error: {e}")
            continue

        # Filtro de rango razonable
        if not (2016 <= anio <= 2100 and 1 <= mes <= 12):
            continue

        vcell = sheet.cell(VALUE_ROW, c)
        valor = None
        if vcell.ctype in (XL_CELL_NUMBER, XL_CELL_DATE):
            try:
                valor = float(vcell.value)
            except Exception:
                valor = None
        else:
            txt = str(vcell.value).strip()
            if txt:
                txt = txt.replace(".", "").replace(",", ".")
                try:
                    valor = float(txt)
                except Exception:
                    valor = None

        if valor is None:
            logging.warning(f"Valor vacío/no numérico en col={c+1} (periodo={periodo_std}). Se omite.")
            continue

        rows.append({"periodo": periodo_std, "anio": anio, "mes": mes, "valor": valor})

    return rows

def insert_silver(rows: list[dict], archivo: str, gcs_uri: str, source_url: str):
    table_id = f"{PROJECT_ID}.{SILVER_DATASET}.{SILVER_TABLE}"
    payload = [{
        "periodo": r["periodo"], "anio": r["anio"], "mes": r["mes"], "valor": r["valor"],
        "archivo": archivo, "gcs_uri": gcs_uri, "source_url": source_url
    } for r in rows]
    if not payload:
        raise RuntimeError("No se extrajeron filas desde el XLS (0).")
    errors = bq_client.insert_rows_json(table_id, payload)
    if errors:
        raise RuntimeError(f"Errores insertando en Silver: {errors}")
    logging.info(f"Insertadas {len(payload)} filas en {table_id} para archivo {archivo}")

def publish_curated_done(info: dict):
    topic_path = publisher.topic_path(PROJECT_ID, TOPIC_CURATED_DONE)
    publisher.publish(topic_path, data=json.dumps(info).encode("utf-8")).result(30)
    logging.info(f"Publicado curated.done: {info}")

def pubsub_handler(event, context=None):
    # Trigger Pub/Sub (Gen2 compatible)
    data_b64 = event["data"] if isinstance(event, dict) else event.data["message"]["data"]
    msg = json.loads(base64.b64decode(data_b64).decode("utf-8"))

    gcs_uri = msg["gcs_uri"]; archivo = msg["archivo"]; source_url = msg.get("source_url")
    rows = read_sheet_from_gcs(gcs_uri)
    insert_silver(rows, archivo, gcs_uri, source_url)
    publish_curated_done({"archivo": archivo, "gcs_uri": gcs_uri, "n_rows": len(rows), "source_url": source_url})