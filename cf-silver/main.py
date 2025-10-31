import base64, json, os, re, unicodedata, logging
from google.cloud import storage, bigquery, pubsub_v1
import xlrd  # v1.2.0 para .xls
from xlrd.xldate import xldate_as_datetime
from xlrd import XL_CELL_TEXT, XL_CELL_NUMBER, XL_CELL_DATE

logging.getLogger().setLevel(logging.INFO)

PROJECT_ID = os.environ.get("PROJECT_ID")
SILVER_DATASET = os.environ.get("SILVER_DATASET", "tgs_sandbox_curated")
SILVER_TABLE = os.environ.get("SILVER_TABLE", "indec_ipc")
TOPIC_CURATED_DONE = os.environ.get("TOPIC_CURATED_DONE", "curated.done")

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
    t = normalize(text).replace(" ", "")
    m = re.match(r"^([a-z]{3})-(\d{2}|\d{4})$", t)
    if m:
        mmm, yy = m.group(1), m.group(2)
        if mmm in MONTHS:
            mes = MONTHS[mmm]
            anio = int(yy) if len(yy)==4 else 2000+int(yy)
            return anio, mes
    m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{2}|\d{4})$", t)
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
    m = re.match(r"^(\d{1,2})[/-](\d{2}|\d{4})$", t)
    if m:
        mes = int(m.group(1))
        ytxt = m.group(2)
        if 1 <= mes <= 12:
            anio = int(ytxt) if len(ytxt)==4 else 2000+int(ytxt)
            return anio, mes
    raise ValueError(f"Texto de periodo no reconocido: {text}")

def parse_period_cell(book, cell) -> tuple[int, int, str]:
    if cell.ctype in (XL_CELL_DATE, XL_CELL_NUMBER):
        try:
            dt = xldate_as_datetime(float(cell.value), book.datemode)
            anio, mes = dt.year, dt.month
            return anio, mes, periodo_str(anio, mes)
        except Exception:
            pass
    if cell.ctype == XL_CELL_TEXT:
        anio, mes = parse_period_from_text(str(cell.value))
        return anio, mes, periodo_str(anio, mes)
    raise ValueError(f"Formato de periodo no reconocido: {cell.value} (ctype={cell.ctype})")

def find_target_sheet(book: xlrd.book.Book):
    target = normalize("Índices IPC Cobertura Nacional")
    for name in book.sheet_names():
        if normalize(name) == target or target in normalize(name):
            return book.sheet_by_name(name)
    for name in book.sheet_names():
        n = normalize(name)
        if "indices" in n and "cobertura" in n and "nacional" in n:
            return book.sheet_by_name(name)
    raise RuntimeError("No se encontró la hoja 'Índices IPC Cobertura Nacional'.")

def find_header_and_value_rows(sheet: xlrd.sheet.Sheet, book: xlrd.book.Book) -> tuple[int, int, int]:
    header_row, start_col = None, None
    max_scan_rows = min(sheet.nrows, 60)
    for r in range(0, max_scan_rows):
        consecutive = 0
        first_col = None
        for c in range(1, sheet.ncols):
            cell = sheet.cell(r, c)
            try:
                anio, mes, _ = parse_period_cell(book, cell)
                if 2000 <= anio <= 2100 and 1 <= mes <= 12:
                    consecutive += 1
                    if first_col is None:
                        first_col = c
                else:
                    break
            except:
                if consecutive >= 5:
                    break
        if consecutive >= 5:
            header_row, start_col = r, first_col
            break
    if header_row is None:
        raise RuntimeError("No se detectó fila de períodos (encabezados).")

    value_row = None
    search_from, search_to = header_row, min(sheet.nrows, header_row + 40)
    for r in range(search_from, search_to):
        cell = sheet.cell(r, 0)
        if cell.ctype == XL_CELL_TEXT and "nivel general" in normalize(str(cell.value)):
            value_row = r
            break
    if value_row is None:
        candidate = header_row + 4
        if candidate < sheet.nrows:
            value_row = candidate
        else:
            raise RuntimeError("No se encontró la fila 'Nivel general'.")

    logging.info(f"[Detect] header_row={header_row}, start_col={start_col}, value_row={value_row}")
    return header_row, value_row, start_col

def read_sheet_from_gcs(gcs_uri: str) -> list[dict]:
    assert gcs_uri.startswith("gs://")
    bucket_name, path = gcs_uri[5:].split("/", 1)

    contents = storage_client.bucket(bucket_name).blob(path).download_as_bytes()
    tmp = "/tmp/input.xls"
    with open(tmp, "wb") as f:
        f.write(contents)

    book = xlrd.open_workbook(tmp)
    sheet = find_target_sheet(book)

    header_row, value_row, start_col = find_header_and_value_rows(sheet, book)

    samples = []
    for c in range(start_col, min(sheet.ncols, start_col+6)):
        try:
            _, _, p = parse_period_cell(book, sheet.cell(header_row, c))
        except Exception as e:
            p = f"err:{e}"
        samples.append(p)
    logging.info(f"[Diagnóstico] Encabezados ejemplo desde col={start_col}: {samples}")

    rows = []
    empty_streak, empty_streak_limit = 0, 6

    for c in range(start_col, sheet.ncols):
        hcell = sheet.cell(header_row, c)
        if (hcell.ctype == 0) or (str(hcell.value).strip() == ""):
            empty_streak += 1
            if empty_streak >= empty_streak_limit:
                break
            else:
                continue
        empty_streak = 0

        try:
            anio, mes, periodo_std = parse_period_cell(book, hcell)
        except Exception as e:
            logging.warning(f"Header no interpretable en col={c}: {hcell.value} ({e})")
            continue

        if not (2016 <= anio <= 2100 and 1 <= mes <= 12):
            continue

        vcell = sheet.cell(value_row, c)
        valor = None
        if vcell.ctype in (XL_CELL_NUMBER, XL_CELL_DATE):
            try:
                valor = float(vcell.value)
            except:
                valor = None
        else:
            txt = str(vcell.value).strip()
            if txt:
                txt = txt.replace(".", "").replace(",", ".")
                try:
                    valor = float(txt)
                except:
                    valor = None

        if valor is None:
            logging.warning(f"Valor vacío/no numérico en col={c} (periodo={periodo_std}). Se omite.")
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
    data_b64 = event["data"] if isinstance(event, dict) else event.data["message"]["data"]
    msg = json.loads(base64.b64decode(data_b64).decode("utf-8"))

    gcs_uri = msg["gcs_uri"]; archivo = msg["archivo"]; source_url = msg.get("source_url")
    rows = read_sheet_from_gcs(gcs_uri)
    insert_silver(rows, archivo, gcs_uri, source_url)
    publish_curated_done({"archivo": archivo, "gcs_uri": gcs_uri, "n_rows": len(rows), "source_url": source_url})
