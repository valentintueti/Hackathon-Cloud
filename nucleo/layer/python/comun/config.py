import json
import os

import boto3

_secreto_cache = None


def env(nombre, defecto=None):
    valor = os.environ.get(nombre, defecto)
    if valor is None:
        raise RuntimeError(f"Falta la variable de entorno {nombre}")
    return valor


def secreto():
    global _secreto_cache
    if _secreto_cache is None:
        cliente = boto3.client("secretsmanager")
        respuesta = cliente.get_secret_value(SecretId=env("SECRET_NAME"))
        _secreto_cache = json.loads(respuesta["SecretString"])
    return _secreto_cache