from datetime import date, datetime

from google.cloud import bigquery
from google.oauth2 import service_account

from comun.config import secreto

_cliente = None


def cliente():
    global _cliente
    if _cliente is None:
        s = secreto()
        credenciales = service_account.Credentials.from_service_account_info(s["gcp_credenciales"])
        _cliente = bigquery.Client(project=s["gcp_project"], credentials=credenciales)
    return _cliente


def dataset():
    s = secreto()
    return f"{s['gcp_project']}.{s['gcp_dataset']}"


def cargar_ndjson(nombre_tabla, archivo):
    configuracion = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        ignore_unknown_values=True,
    )
    trabajo = cliente().load_table_from_file(archivo, f"{dataset()}.{nombre_tabla}", job_config=configuracion)
    trabajo.result()
    return trabajo.output_rows


def _tipo(valor):
    if isinstance(valor, bool):
        return "BOOL"
    if isinstance(valor, int):
        return "INT64"
    if isinstance(valor, float):
        return "FLOAT64"
    if isinstance(valor, datetime):
        return "TIMESTAMP"
    if isinstance(valor, date):
        return "DATE"
    return "STRING"


def consultar(sql, parametros=None):
    configuracion = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter(nombre, _tipo(valor), valor)
            for nombre, valor in (parametros or {}).items()
        ]
    )
    resultado = cliente().query(sql.replace("{dataset}", dataset()), job_config=configuracion).result()
    return [dict(fila) for fila in resultado]