import json
from datetime import datetime, timezone

import boto3

from comun.config import env
from comun.ddb import tabla, a_json

maquinas = tabla("TABLA_MAQUINA")

def _http(codigo, cuerpo):
    return {
        "statusCode": codigo,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": a_json(cuerpo),
    }

def _escanear_todo(tabla_ddb):
    items = []
    respuesta = tabla_ddb.scan()
    items.extend(respuesta.get("Items", []))
    while "LastEvaluatedKey" in respuesta:
        respuesta = tabla_ddb.scan(ExclusiveStartKey=respuesta["LastEvaluatedKey"])
        items.extend(respuesta.get("Items", []))
    return items

def listar(event, context):
    params = event.get("queryStringParameters") or {}
    zona = params.get("zona")
    estado = params.get("estado")

    todas = _escanear_todo(maquinas)

    resultado = []
    for m in todas:
        if (zona is not None and m.get("zona_id")!=zona):
            continue
        if (estado is not None and m.get("estado")!=estado):
            continue
        resultado.append(m)
    return _http(200, {"cantidad": len(resultado), "maquinas": resultado})