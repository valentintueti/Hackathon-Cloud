import json
import os
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import boto3
from boto3.dynamodb.conditions import Key

import correlacion
from comun import bq
from comun.config import env
from comun.ddb import a_dynamo, a_json, actualizar, tabla

events = boto3.client("events")
maquinas = tabla("TABLA_MAQUINA")
zonas = tabla("TABLA_ZONA")
alertas = tabla("TABLA_ALERTA")
ordenes = tabla("TABLA_ORDEN_TRABAJO")
eventos = tabla("TABLA_EVENTO_MASIVO")

RUTA_SQL = os.path.join(os.path.dirname(__file__), "sql", "factores_comunes.sql")

def detectar_grupos(event, context):
    ahora = datetime.now(timezone.utc)
    desde = (ahora - timedelta(minutes=int(env("VENTANA_MINUTOS", "30")))).isoformat()

    todas = _escanear_todo(maquinas)
    zonas_ids = {z["zona_id"] for z in _escanear_todo(zonas)}
    zonas_ids |= {m["zona_id"] for m in todas if m.get("zona_id")}

    recientes = []
    for zona_id in zonas_ids:
        recientes.extend(_alertas_de_zona(zona_id, desde))

    por_zona = correlacion.afectadas_por_zona(recientes, todas, desde)
    grupos = correlacion.armar_grupos(por_zona, int(env("MIN_MAQUINAS", "3")))

    zonas_con_grupo = {g["zona_id"] for g in grupos}
    cerrados = _cerrar_eventos_resueltos(zonas_ids - zonas_con_grupo)

    print(f"Zonas: {len(zonas_ids)} | alertas recientes: {len(recientes)} | grupos: {len(grupos)} | eventos cerrados: {cerrados}")
    return _plano({"cantidad": len(grupos), "grupos": grupos})

def analizar_factores(event, context):
    grupo = event
    ids = grupo["maquinas"]
    fichas = {mid: maquinas.get_item(Key={"maquina_id": mid}).get("Item", {}) for mid in ids}

    factores = []
    factores += correlacion.factores_compartidos("modelo", {mid: f.get("modelo_id") for mid, f in fichas.items()})
    factores += correlacion.factores_compartidos(
        "lote_combustible",
        {mid: (f.get("ultima_lectura") or {}).get("lote_combustible") for mid, f in fichas.items()},
    )
    factores += _factores_componentes(ids)
    factores += _factores_bigquery(ids)
    factores = correlacion.ordenar(factores)

    zona = zonas.get_item(Key={"zona_id": grupo["zona_id"]}).get("Item", {})
    condiciones = {"tipo_terreno": zona.get("tipo_terreno"), "clima_actual": zona.get("clima_actual")}

    texto = correlacion.descripcion(grupo["zona_id"], ids, factores)
    if condiciones["tipo_terreno"] or condiciones["clima_actual"]:
        texto += f" Condiciones de la zona: terreno {condiciones['tipo_terreno'] or '-'}, clima {condiciones['clima_actual'] or '-'}."

    return _plano({**grupo, "factores": factores, "condiciones_zona": condiciones, "descripcion": texto})

def registrar_evento(event, context):
    ahora = datetime.now(timezone.utc).isoformat()
    zona_id = event["zona_id"]

    abierto = _evento_abierto(zona_id)
    if abierto:
        previas = set(abierto.get("maquinas", []))
        nuevas = sorted(set(event["maquinas"]) - previas)
        actualizar(eventos, clave={"evento_id": abierto["evento_id"]}, campos={
            "maquinas": sorted(previas | set(event["maquinas"])),
            "factores": event["factores"],
            "descripcion": event["descripcion"],
            "ts_actualizado": ahora,
        })
        print(f"Evento {abierto['evento_id']} actualizado en {zona_id}; maquinas nuevas: {nuevas}")
        return {"evento_id": abierto["evento_id"], "accion": "actualizado", "maquinas_nuevas": nuevas}

    evento = {
        "evento_id": str(uuid.uuid4()),
        "zona_id": zona_id,
        "estado": "abierto",
        "maquinas": event["maquinas"],
        "inicio": event.get("inicio") or ahora,
        "ts_creado": ahora,
        "ts_actualizado": ahora,
        "factores": event["factores"],
        "condiciones_zona": event.get("condiciones_zona", {}),
        "descripcion": event["descripcion"],
    }
    eventos.put_item(Item=a_dynamo(evento))

    alerta = {
        "alerta_id": str(uuid.uuid4()),
        "ts": ahora,
        "origen": "masivos",
        "tipo": "masiva",
        "estado": "abierta",
        "zona_id": zona_id,
        "severidad": "alta",
        "evento_id": evento["evento_id"],
        "maquinas_afectadas": event["maquinas"],
        "factores_comunes": [f["valor"] for f in event["factores"]],
        "descripcion": event["descripcion"],
    }
    alertas.put_item(Item=a_dynamo(alerta))
    events.put_events(Entries=[{
        "EventBusName": env("BUS"),
        "Source": "arquifusion.masivos",
        "DetailType": "AlertaCreada",
        "Detail": a_json(alerta),
    }])
    print(f"Evento masivo creado en {zona_id}: {evento['evento_id']}")
    return {"evento_id": evento["evento_id"], "accion": "creado", "alerta_id": alerta["alerta_id"]}

def _escanear_todo(tabla_ddb):
    items = []
    respuesta = tabla_ddb.scan()
    items.extend(respuesta.get("Items", []))
    while "LastEvaluatedKey" in respuesta:
        respuesta = tabla_ddb.scan(ExclusiveStartKey=respuesta["LastEvaluatedKey"])
        items.extend(respuesta.get("Items", []))
    return items


def _consultar_todo(tabla_ddb, **parametros):
    items = []
    while True:
        respuesta = tabla_ddb.query(**parametros)
        items.extend(respuesta.get("Items", []))
        if "LastEvaluatedKey" not in respuesta:
            return items
        parametros["ExclusiveStartKey"] = respuesta["LastEvaluatedKey"]


def _alertas_de_zona(zona_id, desde):
    return _consultar_todo(
        alertas,
        IndexName="por_zona",
        KeyConditionExpression=Key("zona_id").eq(zona_id) & Key("ts").gte(desde),
    )


def _evento_abierto(zona_id):
    items = _consultar_todo(
        eventos,
        IndexName="por_zona_estado",
        KeyConditionExpression=Key("zona_id").eq(zona_id) & Key("estado").eq("abierto"),
    )
    return items[0] if items else None


def _cerrar_eventos_resueltos(zonas_sin_grupo):
    ahora = datetime.now(timezone.utc).isoformat()
    cerrados = 0
    for zona_id in zonas_sin_grupo:
        abierto = _evento_abierto(zona_id)
        if abierto:
            actualizar(eventos, clave={"evento_id": abierto["evento_id"]},
                       campos={"estado": "cerrado", "ts_cierre": ahora})
            cerrados += 1
    return cerrados


def _factores_componentes(ids):
    desde = (datetime.now(timezone.utc) - timedelta(days=int(env("DIAS_COMPONENTES", "30")))).isoformat()
    maquinas_por_componente = defaultdict(set)
    for mid in ids:
        lista = _consultar_todo(
            ordenes,
            IndexName="por_maquina",
            KeyConditionExpression=Key("maquina_id").eq(mid) & Key("ts_creada").gte(desde),
        )
        for orden in lista:
            for c in orden.get("componentes_reemplazados", []) or []:
                if c.get("componente"):
                    maquinas_por_componente[c["componente"]].add(mid)
    return [
        {"tipo": "componente", "valor": comp, "maquinas": sorted(ms), "cantidad": len(ms)}
        for comp, ms in maquinas_por_componente.items()
        if len(ms) >= 2
    ]


def _factores_bigquery(ids):
    try:
        with open(RUTA_SQL, encoding="utf-8") as archivo:
            filas = bq.consultar(archivo.read(), {
                "maquinas": ",".join(ids),
                "dias": int(env("DIAS_HISTORIA", "14")),
                "minutos": int(env("MINUTOS_BIGQUERY", "180")),
                "z": float(env("Z_UMBRAL", "3")),
            })
        return correlacion.factores_variables(filas)
    except Exception as error:
        print(f"No se pudo analizar en BigQuery: {error}")
        return []


def _plano(valor):
    return json.loads(a_json(valor))