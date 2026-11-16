import io
import json
import os
from datetime import datetime, timedelta, timezone

from boto3.dynamodb.conditions import Attr, Key

import prompts
import riesgo
from comun import bq, ia
from comun.config import env
from comun.ddb import a_dynamo, a_json, actualizar, tabla

maquinas = tabla("TABLA_MAQUINA")
alertas = tabla("TABLA_ALERTA")
ordenes = tabla("TABLA_ORDEN_TRABAJO")
riesgos = tabla("TABLA_RIESGO")

RUTA_SQL = os.path.join(os.path.dirname(__file__), "sql", "patrones.sql")
MAQUINAS_POR_LLAMADA = 10
TABLA_FALLA = "CREATE OR REPLACE TABLE `{dataset}.falla` (maquina_id STRING, ts TIMESTAMP, origen STRING)"

def buscar_patrones(event, context):
    desde = (datetime.now(timezone.utc) - timedelta(days=int(env("DIAS_HISTORIA", "180")))).isoformat()

    fallas = _fallas_desde_ordenes(desde)
    origen = "ordenes_correctivas"
    if not fallas:
        fallas = _fallas_desde_alertas(desde)
        origen = "alertas_criticas"

    bq.consultar(TABLA_FALLA)
    if fallas:
        archivo = io.BytesIO("\n".join(json.dumps(f) for f in fallas).encode("utf-8"))
        bq.cargar_ndjson("falla", archivo)
    else:
        origen = "telemetria"

    with open(RUTA_SQL, encoding="utf-8") as sql:
        filas = bq.consultar(sql.read(), {
            "dias": int(env("DIAS_HISTORIA", "180")),
            "horas_desde": int(env("HORAS_ANTES_DESDE", "72")),
            "horas_hasta": int(env("HORAS_ANTES_HASTA", "24")),
            "dias_sin_falla": int(env("DIAS_SIN_FALLA", "3")),
            "horas_recientes": int(env("HORAS_RECIENTES", "24")),
            "z_nivel": float(env("Z_NIVEL", "1")),
            "min_soporte": int(env("MIN_SOPORTE", "3")),
            "min_lift": float(env("MIN_LIFT", "2")),
        })

    patrones, niveles = [], {}
    for f in filas:
        if f["tipo"] == "patron":
            patrones.append({
                "combinacion": f["combinacion"],
                "items": list(f["items"]),
                "soporte": int(f["soporte"]),
                "lift": float(f["lift"]),
            })
        else:
            niveles[str(f["maquina_id"])] = list(f["items"])

    print(f"Fallas: {len(fallas)} (origen: {origen}) | patrones: {len(patrones)} | maquinas con niveles hoy: {len(niveles)}")
    return {"fallas": len(fallas), "origen_fallas": origen, "patrones": patrones, "niveles": niveles}

def puntuar_riesgo(event, context):
    patrones = event.get("patrones", [])
    niveles = event.get("niveles", {})
    ahora = datetime.now(timezone.utc)
    umbral_medio = float(env("UMBRAL_MEDIO", "30"))
    umbral_alto = float(env("UMBRAL_ALTO", "60"))

    en_riesgo, total_maquinas = [], 0
    for m in _escanear_todo(maquinas):
        maquina_id = str(m["maquina_id"])
        items_hoy = niveles.get(maquina_id, [])
        presentes = riesgo.presentes(items_hoy, patrones)
        reincidencias, dias_desde_falla = _historial(maquina_id, ahora)

        total, factores = riesgo.puntaje(
            presentes,
            porcentaje_intervalo=m.get("porcentaje_intervalo"),
            health_score=m.get("health_score"),
            reincidencias=reincidencias,
            dias_desde_falla=dias_desde_falla,
        )
        nivel = riesgo.nivel(total, umbral_medio, umbral_alto)

        fila = {
            "maquina_id": maquina_id,
            "modelo_id": m.get("modelo_id"),
            "zona_id": m.get("zona_id"),
            "puntaje": total,
            "nivel": nivel,
            "patrones_presentes": presentes,
            "niveles_hoy": items_hoy,
            "factores": factores,
            "sin_patrones": not patrones,
            "ts": ahora.isoformat(),
        }
        riesgos.put_item(Item=a_dynamo({k: v for k, v in fila.items() if v is not None}))
        total_maquinas += 1
        if nivel in ("alto", "medio"):
            en_riesgo.append(fila)

    en_riesgo.sort(key=lambda f: f["puntaje"], reverse=True)
    print(f"Maquinas puntuadas: {total_maquinas} | en riesgo medio o alto: {len(en_riesgo)}")
    return _plano({"cantidad": len(en_riesgo), "en_riesgo": en_riesgo, "patrones": patrones})

def recomendar(event, context):
    en_riesgo = event["en_riesgo"]
    patrones = event.get("patrones", [])

    sugerencias, ajustes_modelo = {}, {}
    for i in range(0, len(en_riesgo), MAQUINAS_POR_LLAMADA):
        grupo = en_riesgo[i:i + MAQUINAS_POR_LLAMADA]
        respuesta = ia.generar_json(prompts.construir(patrones, grupo), prompts.SISTEMA, max_tokens=3000)
        if isinstance(respuesta, dict):
            if isinstance(respuesta.get("maquinas"), dict):
                sugerencias.update(respuesta["maquinas"])
            if isinstance(respuesta.get("modelos"), dict):
                ajustes_modelo.update(respuesta["modelos"])

    de_ia = 0
    for m in en_riesgo:
        sugerencia = sugerencias.get(m["maquina_id"])
        if isinstance(sugerencia, dict) and (sugerencia.get("programar") or sugerencia.get("revisar")):
            texto = " ".join(str(sugerencia[k]).strip() for k in ("programar", "revisar") if sugerencia.get(k))
            por = "gemini"
            de_ia += 1
        else:
            texto = riesgo.respaldo(m)
            por = "reglas"

        campos = {"recomendacion": texto[:1500], "recomendado_por": por}
        ajuste = ajustes_modelo.get(str(m.get("modelo_id")))
        if isinstance(ajuste, str) and ajuste.strip():
            campos["ajuste_modelo"] = ajuste.strip()[:500]
        actualizar(riesgos, clave={"maquina_id": m["maquina_id"]}, campos=campos)

    print(f"Recomendaciones: {len(en_riesgo)} ({de_ia} con Gemini) | ajustes por modelo: {len(ajustes_modelo)}")
    return {"recomendaciones": len(en_riesgo), "con_gemini": de_ia, "ajustes_modelo": len(ajustes_modelo)}


def listar_riesgo(event, context):
    params = event.get("queryStringParameters") or {}
    nivel = params.get("nivel")

    filas = _escanear_todo(riesgos)
    if nivel:
        filas = [f for f in filas if f.get("nivel") == nivel]
    filas.sort(key=lambda f: float(f.get("puntaje", 0)), reverse=True)

    return _http(200, {
        "cantidad": len(filas),
        "sin_patrones_suficientes": any(f.get("sin_patrones") for f in filas),
        "maquinas": filas,
    })


def _fallas_desde_ordenes(desde):
    items = _escanear_todo(ordenes, FilterExpression=Attr("tipo").eq("correctivo") & Attr("ts_creada").gte(desde))
    return [{"maquina_id": str(o["maquina_id"]), "ts": o["ts_creada"], "origen": "orden"} for o in items]


def _fallas_desde_alertas(desde):
    items = _escanear_todo(
        alertas,
        FilterExpression=Attr("severidad").eq("critica") & Attr("maquina_id").exists() & Attr("ts").gte(desde),
    )
    return [{"maquina_id": str(a["maquina_id"]), "ts": a["ts"], "origen": "alerta"} for a in items]


def _historial(maquina_id, ahora):
    desde = (ahora - timedelta(days=int(env("DIAS_REINCIDENCIA", "90")))).isoformat()
    lista = _consultar_todo(
        ordenes,
        IndexName="por_maquina",
        KeyConditionExpression=Key("maquina_id").eq(maquina_id) & Key("ts_creada").gte(desde),
    )
    correctivas = [o for o in lista if o.get("tipo", "correctivo") == "correctivo"]
    reincidencias = sum(1 for o in correctivas if o.get("reincidente_de"))
    if not correctivas:
        return reincidencias, None
    ultima = datetime.fromisoformat(str(max(o["ts_creada"] for o in correctivas)))
    if ultima.tzinfo is None:
        ultima = ultima.replace(tzinfo=timezone.utc)
    return reincidencias, max((ahora - ultima).total_seconds() / 86400, 0)


def _escanear_todo(tabla_ddb, **parametros):
    items = []
    while True:
        respuesta = tabla_ddb.scan(**parametros)
        items.extend(respuesta.get("Items", []))
        if "LastEvaluatedKey" not in respuesta:
            return items
        parametros["ExclusiveStartKey"] = respuesta["LastEvaluatedKey"]


def _consultar_todo(tabla_ddb, **parametros):
    items = []
    while True:
        respuesta = tabla_ddb.query(**parametros)
        items.extend(respuesta.get("Items", []))
        if "LastEvaluatedKey" not in respuesta:
            return items
        parametros["ExclusiveStartKey"] = respuesta["LastEvaluatedKey"]


def _plano(valor):
    return json.loads(a_json(valor))


def _http(codigo, cuerpo):
    return {
        "statusCode": codigo,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": a_json(cuerpo),
    }