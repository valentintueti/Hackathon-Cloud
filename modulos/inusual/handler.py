import os
import uuid
from datetime import datetime, timezone

import boto3

import estadistica
from comun import bq
from comun.config import env
from comun.ddb import a_dynamo, a_json, actualizar, tabla

events = boto3.client("events")
lineas_base = tabla("TABLA_LINEA_BASE")
maquinas = tabla("TABLA_MAQUINA")
alertas = tabla("TABLA_ALERTA")

RUTA_SQL = os.path.join(os.path.dirname(__file__), "sql", "lineas_base.sql")


def calcular_lineas_base(event, context):
    with open(RUTA_SQL, encoding="utf-8") as archivo:
        bq.consultar(archivo.read(), {"dias": int(env("DIAS_HISTORIA", "14"))})
    filas = bq.consultar("SELECT COUNT(*) AS filas FROM `{dataset}.linea_base`")[0]["filas"]
    print(f"Líneas base calculadas en BigQuery: {filas}")
    return {"filas": filas}


def copiar_a_dynamo(event, context):
    filas = bq.consultar("SELECT * FROM `{dataset}.linea_base`")
    with lineas_base.batch_writer() as escritor:
        for fila in filas:
            escritor.put_item(Item=a_dynamo({
                "clave": f"{fila['ambito']}#{fila['id']}",
                "ambito": fila["ambito"],
                "id": fila["id"],
                "n": fila["n"],
                "calculado_en": str(fila["calculado_en"]),
                "variables": {
                    v: {"media": fila[f"{v}_media"], "desv": fila[f"{v}_desv"]}
                    for v in estadistica.VARIABLES
                    if fila.get(f"{v}_media") is not None
                },
            }))
    print(f"Líneas base copiadas a DynamoDB: {len(filas)}")
    return {"guardadas": len(filas)}



def comparar(event, context):
    ahora = datetime.now(timezone.utc)
    z_umbral = float(env("Z_UMBRAL", "3"))
    min_muestras = int(env("MIN_MUESTRAS", "30"))
    minutos = int(env("MINUTOS_ENTRE_ALERTAS", "60"))
    cache = {}
    creadas = 0

    for lectura in event["detail"]["lecturas"]:
        if lectura.get("estado") == "detenida" or (lectura.get("rpm") is not None and lectura["rpm"] <= 0):
            continue

        maquina_id = str(lectura["maquina_id"])
        base_maquina = _base(f"maquina#{maquina_id}", cache)
        base_modelo = _base(f"modelo#{lectura.get('modelo_id')}", cache) if lectura.get("modelo_id") else None

        desvios = estadistica.comparar(lectura, base_maquina, base_modelo, z_umbral, min_muestras)
        severidad = estadistica.severidad(desvios)
        if severidad == "normal":
            continue

        maquina = maquinas.get_item(Key={"maquina_id": maquina_id}).get("Item", {})
        if not estadistica.debe_alertar(
            severidad, maquina.get("inusual_ultima_severidad"), maquina.get("inusual_ultima_alerta_ts"), ahora, minutos
        ):
            continue

        alerta = {
            "alerta_id": str(uuid.uuid4()),
            "ts": ahora.isoformat(),
            "origen": "inusual",
            "tipo": "inusual",
            "estado": "abierta",
            "maquina_id": maquina_id,
            "zona_id": lectura.get("zona_id") or maquina.get("zona_id"),
            "modelo_id": lectura.get("modelo_id") or maquina.get("modelo_id"),
            "ts_lectura": lectura["ts"],
            "severidad": severidad,
            "variables_afectadas": sorted({d["variable"] for d in desvios}),
            "comparado_con": sorted({d["referencia"] for d in desvios}),
            "desvios": desvios,
            "descripcion": estadistica.descripcion(desvios),
        }
        alertas.put_item(Item=a_dynamo({k: v for k, v in alerta.items() if v is not None}))
        actualizar(maquinas, clave={"maquina_id": maquina_id},
                   campos={"inusual_ultima_alerta_ts": ahora.isoformat(), "inusual_ultima_severidad": severidad})
        events.put_events(Entries=[{
            "EventBusName": env("BUS"),
            "Source": "arquifusion.inusual",
            "DetailType": "AlertaCreada",
            "Detail": a_json(alerta),
        }])
        creadas += 1

    print(f"Lecturas: {len(event['detail']['lecturas'])} | alertas inusuales: {creadas}")
    return {"alertas": creadas}


def _base(clave, cache):
    if clave not in cache:
        cache[clave] = lineas_base.get_item(Key={"clave": clave}).get("Item")
    return cache[clave]