import json

import boto3

from comun.config import env

sqs = boto3.client("sqs")


CAMPOS_OBLIGATORIOS = ("maquina_id", "ts")
MAX_LECTURAS_POR_PETICION = 1000


def _respuesta(codigo, cuerpo):
    return {
        "statusCode": codigo,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(cuerpo, ensure_ascii=False),
    }


def _errores_de_validacion(lecturas):
    errores = []
    for i, lectura in enumerate(lecturas):
        if not isinstance(lectura, dict):
            errores.append({"indice": i, "error": "la lectura debe ser un objeto JSON"})
            continue
        faltan = [c for c in CAMPOS_OBLIGATORIOS if lectura.get(c) in (None, "")]
        if faltan:
            errores.append({"indice": i, "faltan": faltan})
    return errores


def handler(event, context):
    try:
        datos = json.loads(event.get("body") or "null")
    except json.JSONDecodeError:
        return _respuesta(400, {"error": "El cuerpo no es JSON válido"})

    lecturas = datos if isinstance(datos, list) else [datos]
    if not lecturas or lecturas == [None]:
        return _respuesta(400, {"error": "No se enviaron lecturas"})
    if len(lecturas) > MAX_LECTURAS_POR_PETICION:
        return _respuesta(413, {"error": f"Máximo {MAX_LECTURAS_POR_PETICION} lecturas por petición"})

    errores = _errores_de_validacion(lecturas)
    if errores:
        return _respuesta(400, {"error": "Lecturas inválidas", "detalle": errores[:20]})

    cola = env("COLA_TELEMETRIA")
    fallidas = 0
    for inicio in range(0, len(lecturas), 10):
        lote = lecturas[inicio:inicio + 10]
        resultado = sqs.send_message_batch(
            QueueUrl=cola,
            Entries=[{"Id": str(j), "MessageBody": json.dumps(l)} for j, l in enumerate(lote)],
        )
        fallidas += len(resultado.get("Failed", []))

    if fallidas:
        print(f"No se pudieron encolar {fallidas} lecturas")
        return _respuesta(500, {"recibidas": len(lecturas) - fallidas, "fallidas": fallidas})
    return _respuesta(202, {"recibidas": len(lecturas)})