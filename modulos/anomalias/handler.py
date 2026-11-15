import json
import uuid
from datetime import datetime, timezone

import boto3

import reglas
import prompts
from comun import ia
from comun.config import env
from comun.ddb import a_dynamo, actualizar, tabla

sfn = boto3.client("stepfunctions")
maquinas = tabla("TABLA_MAQUINA")
modelos = tabla("TABLA_MODELO")
alertas = tabla("TABLA_ALERTA")

def evaluar(event, context):
    ahora = datetime.now(timezone.utc)
    minutos_entre_alertas = int(env("MINUTOS_ENTRE_ALERTAS", "30"))
    tamano_ventana = int(env("TAMANO_VENTANA", "10"))
    cache_umbrales = {}
    iniciadas = 0

    for lectura in event["detail"]["lecturas"]:
        if not reglas.debe_evaluar(lectura):
            continue

        maquina_id = str(lectura["maquina_id"])
        maquina = maquinas.get_item(Key={"maquina_id": maquina_id}).get("Item", {})
        umbrales = _umbrales(maquina.get("modelo_id") or lectura.get("modelo_id"), cache_umbrales)

        puntaje, afectadas = reglas.puntaje(lectura, umbrales)
        ventana = [float(p) for p in maquina.get("ventana_puntajes", [])] + [puntaje]
        ventana = ventana[-tamano_ventana:]
        puntaje_final = min(100.0, puntaje + reglas.tendencia(ventana))
        severidad = reglas.severidad(puntaje_final)

        campos = {
            "health_score": round(100 - puntaje_final, 1),
            "ventana_puntajes": ventana,
            "ultima_evaluacion_ts": ahora.isoformat(),
        }
        alertar = reglas.debe_alertar(severidad, maquina, ahora, minutos_entre_alertas)
        if alertar:
            campos.update({"ultima_alerta_ts": ahora.isoformat(), "ultima_alerta_severidad": severidad})
        actualizar(maquinas, clave={"maquina_id": maquina_id}, campos=campos)

        if alertar:
            sfn.start_execution(
                stateMachineArn=env("STATE_MACHINE_ARN"),
                name=f"{maquina_id}-{uuid.uuid4().hex[:12]}"[:80],
                input=json.dumps({
                    "maquina_id": maquina_id,
                    "zona_id": lectura.get("zona_id") or maquina.get("zona_id"),
                    "modelo_id": lectura.get("modelo_id") or maquina.get("modelo_id"),
                    "ts_lectura": lectura["ts"],
                    "puntaje": puntaje_final,
                    "severidad": severidad,
                    "variables_afectadas": afectadas,
                    "valores": {v: lectura.get(v) for v in reglas.PESOS},
                    "umbrales": {
                        v: {"normal": float(u["normal"]), "limite": float(u["limite"])}
                        for v, u in umbrales.items() if v in reglas.PESOS
                    },
                    "tendencia_creciente": puntaje_final > puntaje,
                }),
            )
            iniciadas += 1

    print(f"Lecturas evaluadas: {len(event['detail']['lecturas'])} | alertas iniciadas: {iniciadas}")
    return {"alertas": iniciadas}

def registrar_alerta(event, context):
    alerta = {
        "alerta_id": str(uuid.uuid4()),
        "ts": datetime.now(timezone.utc).isoformat(),
        "origen": "anomalias",
        "tipo": "anomalia",
        "estado": "abierta",
        **event,
    }
    analisis = _explicar(event)
    if analisis:
        alerta["explicacion_ia"] = analisis["explicacion"]
        alerta["revisar_primero_ia"] = analisis["revisar_primero"]
    alertas.put_item(Item=a_dynamo({k: v for k, v in alerta.items() if v is not None}))

    variables = ", ".join(event["variables_afectadas"]) or "variables en el límite"
    asunto = f"[{event['severidad'].upper()}] Anomalía en {event['maquina_id']}"
    mensaje = (
        f"Máquina: {event['maquina_id']} (zona {event.get('zona_id')}, modelo {event.get('modelo_id')})\n"
        f"Severidad: {event['severidad']} — puntaje {event['puntaje']}/100\n"
        f"Variables afectadas: {variables}\n"
        f"Valores: {json.dumps(event['valores'], ensure_ascii=False)}\n"
        f"Tendencia creciente: {'sí' if event['tendencia_creciente'] else 'no'}\n"
        f"Lectura: {event['ts_lectura']}"
    )
    if analisis:
        pasos = "\n".join(f"{i}. {p}" for i, p in enumerate(analisis["revisar_primero"], 1))
        mensaje += f"\n\nExplicación (IA): {analisis['explicacion']}"
        if pasos:
            mensaje += f"\nRevisar primero:\n{pasos}"
    return {
        "alerta": alerta,
        "critica": event["severidad"] == "critica",
        "asunto": asunto[:100],
        "mensaje": mensaje,
    }


def _explicar(event):
    respuesta = ia.generar_json(prompts.construir(event), prompts.SISTEMA)
    if not isinstance(respuesta, dict):
        return None
    explicacion = respuesta.get("explicacion")
    if not isinstance(explicacion, str) or not explicacion.strip():
        return None
    pasos = respuesta.get("revisar_primero")
    pasos = [str(p).strip()[:200] for p in pasos if str(p).strip()] if isinstance(pasos, list) else []
    return {"explicacion": explicacion.strip()[:800], "revisar_primero": pasos[:3]}

def _umbrales(modelo_id, cache):
    if modelo_id not in cache:
        modelo = modelos.get_item(Key={"modelo_id": modelo_id}).get("Item", {}) if modelo_id else {}
        cache[modelo_id] = modelo.get("umbrales") or reglas.UMBRALES_POR_DEFECTO
    return cache[modelo_id]