import json
import os
import uuid
from datetime import datetime, timezone

import boto3

import prompts
from comun import bq, ia
from comun.config import env
from comun.ddb import a_dynamo, a_json, tabla

events = boto3.client("events")
alertas = tabla("TABLA_ALERTA")

RUTA_SQL = os.path.join(os.path.dirname(__file__), "sql", "combustible.sql")

METRICAS = (
    "unidad", "consumo_ayer", "media_propia", "z_propio", "pct_propio",
    "media_modelo", "pct_modelo", "maquinas_modelo", "pendiente_diaria", "r_tendencia",
)


def analizar(event, context):
    with open(RUTA_SQL, encoding="utf-8") as archivo:
        filas = bq.consultar(archivo.read(), {
            "dias": int(env("DIAS_HISTORIA", "14")),
            "dias_tendencia": int(env("DIAS_TENDENCIA", "7")),
            "z": float(env("Z_UMBRAL", "3")),
            "pct_propio": float(env("PCT_PROPIO", "30")),
            "pct_modelo": float(env("PCT_MODELO", "20")),
            "min_maquinas_modelo": int(env("MIN_MAQUINAS_MODELO", "3")),
            "r_tendencia": float(env("R_TENDENCIA", "0.8")),
        })
    sospechosas = json.loads(json.dumps(filas, default=str))
    print(f"Maquinas con consumo sospechoso: {len(sospechosas)}")
    return {"cantidad": len(sospechosas), "sospechosas": sospechosas}


def explicar_causas(event, context):
    sospechosas = event["sospechosas"]
    respuesta = ia.generar_json(prompts.construir(sospechosas), prompts.SISTEMA, max_tokens=2000)
    if not isinstance(respuesta, dict):
        respuesta = {}

    de_ia = 0
    for s in sospechosas:
        texto = respuesta.get(str(s["maquina_id"]))
        if isinstance(texto, str) and texto.strip():
            s["explicacion"] = texto.strip()[:1000]
            s["explicado_por"] = "gemini"
            de_ia += 1
        else:
            s["explicacion"] = prompts.respaldo(s)                                   # HUECO 1
            s["explicado_por"] = "reglas"

    print(f"Explicaciones: {de_ia} con Gemini, {len(sospechosas) - de_ia} por reglas")
    return {**event, "sospechosas": sospechosas}


def guardar_alertas(event, context):
    ahora = datetime.now(timezone.utc).isoformat()
    creadas = 0
    for s in event["sospechosas"]:
        alerta = {
            "alerta_id": str(uuid.uuid4()),
            "ts": ahora,
            "origen": "combustible",                                                    # HUECO 2
            "tipo": "combustible",
            "estado": "abierta",
            "maquina_id": str(s["maquina_id"]),
            "zona_id": s.get("zona_id"),
            "modelo_id": s.get("modelo_id"),
            "severidad": "alta" if len(s["casos"]) >= 2 else "media",          # HUECO 3
            "casos": s["casos"],
            "variables_afectadas": ["consumo_combustible"],
            "metricas": {k: s[k] for k in METRICAS if s.get(k) is not None},
            "descripcion": s["explicacion"],
            "explicado_por": s.get("explicado_por"),
        }
        alertas.put_item(Item=a_dynamo({k: v for k, v in alerta.items() if v is not None}))
        events.put_events(Entries=[{
            "EventBusName": env("BUS"),
            "Source": "arquifusion.combustible",
            "DetailType": "AlertaCreada",                                                # HUECO 4
            "Detail": a_json(alerta),
        }])
        creadas += 1

    print(f"Alertas de combustible creadas: {creadas}")
    return {"alertas": creadas}