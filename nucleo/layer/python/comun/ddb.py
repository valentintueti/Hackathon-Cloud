import json
from decimal import Decimal

import boto3

from comun.config import env

_dynamo = boto3.resource("dynamodb")


def tabla(variable_entorno):
    return _dynamo.Table(env(variable_entorno))


def a_dynamo(valor):
    return json.loads(json.dumps(valor), parse_float=Decimal)


def _decimal_a_numero(obj):
    if isinstance(obj, Decimal):
        return int(obj) if obj == obj.to_integral_value() else float(obj)
    raise TypeError(f"Tipo no serializable: {type(obj).__name__}")


def a_json(valor):
    return json.dumps(valor, default=_decimal_a_numero)


def actualizar(tabla_ddb, clave, campos, condicion=None, valores_extra=None):
    nombres = {f"#{c}": c for c in campos}
    valores = {f":{c}": a_dynamo(v) for c, v in campos.items()}
    if valores_extra:
        valores.update({k: a_dynamo(v) for k, v in valores_extra.items()})
    parametros = {
        "Key": clave,
        "UpdateExpression": "SET " + ", ".join(f"#{c} = :{c}" for c in campos),
        "ExpressionAttributeNames": nombres,
        "ExpressionAttributeValues": valores,
    }
    if condicion:
        parametros["ConditionExpression"] = condicion
    return tabla_ddb.update_item(**parametros)