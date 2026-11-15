import json
import os
from datetime import datetime, timedelta, timezone

import prompts
from comun import bq, ia
from comun.config import env
from comun.ddb import a_dynamo, a_json, tabla

recomendaciones = tabla("TABLA_RECOMENDACION_FLOTA")

CARPETA_SQL = os.path.join(os.path.dirname(__file__), "sql")
LIMA = timezone(timedelta(hours=-5))
MAX_MAQUINAS_PROMPT = 30


def calcular_kpis(event, context):
    sql_kpi = _leer("kpi_diario.sql")
    for nombre, valor in {
        "dias": int(env("DIAS_KPI", "60")),
        "horas_turno": float(env("HORAS_TURNO", "10")),
        "precio_litro": float(env("PRECIO_LITRO", "4.5")),
        "costo_hora": float(env("COSTO_HORA", "0")),
        "rpm_ralenti": float(env("RPM_RALENTI", "900")),
    }.items():
        sql_kpi = sql_kpi.replace("{" + nombre + "}", str(valor))
    bq.consultar(sql_kpi)

    filas = bq.consultar(_leer("hallazgos.sql"), {
        "dias_analisis": int(env("DIAS_ANALISIS", "7")),
        "horas_max": float(env("HORAS_MAX_DIA", "12")),
        "dias_excesivos_min": int(env("DIAS_EXCESIVOS_MIN", "2")),
        "util_min": float(env("UTILIZACION_MIN_PCT", "40")),
        "pct_costo": float(env("PCT_COSTO", "30")),
        "pct_carga": float(env("PCT_CARGA", "20")),
    })
    maquinas = json.loads(json.dumps(filas, default=str))
    print(f"Maquinas con hallazgos de productividad: {len(maquinas)}")
    return {"cantidad": len(maquinas), "maquinas": maquinas}


def recomendar(event, context):
    maquinas = event["maquinas"]
    acciones = _acciones(maquinas)

    respuesta = ia.generar_json(
        prompts.construir(maquinas[:MAX_MAQUINAS_PROMPT], acciones), prompts.SISTEMA, max_tokens=1500
    )
    if isinstance(respuesta, dict) and isinstance(respuesta.get("resumen"), str) and respuesta["resumen"].strip():
        lista = respuesta.get("recomendaciones")
        lista = [str(r).strip()[:300] for r in lista if str(r).strip()][:5] if isinstance(lista, list) else []
        resumen, redactado_por = respuesta["resumen"].strip()[:1500], "gemini"
    else:
        lista = [a["detalle"] for a in acciones][:5]
        resumen, redactado_por = prompts.respaldo(maquinas, acciones), "reglas"

    ahora = datetime.now(LIMA)
    item = {
        "fecha": ahora.date().isoformat(),
        "ts": ahora.isoformat(),
        "maquinas": maquinas,
        "acciones": acciones,
        "resumen": resumen,
        "recomendaciones": lista,
        "redactado_por": redactado_por,
    }
    recomendaciones.put_item(Item=a_dynamo(item))
    print(f"Recomendacion {item['fecha']}: {len(acciones)} acciones, redactada por {redactado_por}")
    return {"fecha": item["fecha"], "acciones": len(acciones), "redactado_por": redactado_por}


def ultima(event, context):
    params = event.get("queryStringParameters") or {}
    hoy = datetime.now(LIMA).date()
    fechas = [params["fecha"]] if params.get("fecha") else [hoy.isoformat(), (hoy - timedelta(days=1)).isoformat()]
    for fecha in fechas:
        item = recomendaciones.get_item(Key={"fecha": fecha}).get("Item")
        if item:
            return _http(200, item)
    return _http(404, {"error": "No hay recomendaciones para esa fecha"})


def _acciones(maquinas):
    def con(hallazgo):
        return [m for m in maquinas if hallazgo in m.get("hallazgos", [])]

    libres = con("baja_utilizacion")
    acciones = []

    for excedida in con("jornada_excesiva"):
        apoyo = next(
            (m for m in libres
             if m.get("modelo_id") == excedida.get("modelo_id") and m["maquina_id"] != excedida["maquina_id"]),
            None,
        )
        if apoyo:
            libres.remove(apoyo)
            acciones.append({
                "tipo": "reasignar",
                "maquina_id": apoyo["maquina_id"],
                "apoya_a": excedida["maquina_id"],
                "desde_zona": apoyo.get("zona_id"),
                "hacia_zona": excedida.get("zona_id"),
                "detalle": (
                    f"Reasignar {apoyo['maquina_id']} ({apoyo.get('utilizacion_pct')}% de uso, zona {apoyo.get('zona_id')}) "
                    f"para apoyar a {excedida['maquina_id']} ({excedida.get('dias_excesivos')} dias con jornada excesiva, "
                    f"zona {excedida.get('zona_id')})."
                ),
            })
        else:
            acciones.append({
                "tipo": "repartir_jornada",
                "maquina_id": excedida["maquina_id"],
                "detalle": (
                    f"{excedida['maquina_id']} tuvo {excedida.get('dias_excesivos')} dias sobre la jornada maxima y no hay "
                    "otra maquina libre de su modelo: evaluar un segundo turno o limitar sus horas."
                ),
            })

    for libre in libres:
        acciones.append({
            "tipo": "revisar_asignacion",
            "maquina_id": libre["maquina_id"],
            "detalle": (
                f"{libre['maquina_id']} uso solo {libre.get('utilizacion_pct')}% de su turno en la zona {libre.get('zona_id')}: "
                "evaluar moverla a otra zona o retirarla temporalmente."
            ),
        })

    for cara in con("baja_productividad_alto_costo"):
        acciones.append({
            "tipo": "revisar_operacion",
            "maquina_id": cara["maquina_id"],
            "detalle": (
                f"{cara['maquina_id']} cuesta {cara.get('costo_hora_por_t')} por hora y tonelada frente a "
                f"{cara.get('costo_mediana_modelo')} de su modelo, con {cara.get('ralenti_pct')}% de ralenti: "
                "revisar forma de operacion, carga por ciclo y mantenimiento."
            ),
        })
    return acciones


def _leer(nombre):
    with open(os.path.join(CARPETA_SQL, nombre), encoding="utf-8") as archivo:
        return archivo.read()


def _http(codigo, cuerpo):
    return {
        "statusCode": codigo,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": a_json(cuerpo),
    }