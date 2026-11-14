import io
import json
from datetime import datetime, timedelta, timezone

import boto3

from comun import bq
from comun.config import env

s3 = boto3.client("s3")

PREFIJO = "telemetria/"
CLAVE_CONTROL = "control/ultima_exportacion.json"
MARGEN = timedelta(minutes=2)
MAX_BYTES_POR_CARGA = 50 * 1024 * 1024
TABLA = "lectura_telemetria"


def handler(event, context):
    bucket = env("BUCKET_TELEMETRIA")
    desde = leer_control(bucket)
    hasta = datetime.now(timezone.utc) - MARGEN

    claves = archivos_nuevos(bucket, desde, hasta)
    filas_cargadas = 0
    buffer = io.BytesIO()

    for clave in claves:
        contenido = s3.get_object(Bucket=bucket, Key=clave)["Body"].read()
        if not contenido.strip():
            continue
        if not contenido.endswith(b"\n"):
            contenido += b"\n"
        buffer.write(contenido)
        if buffer.tell() >= MAX_BYTES_POR_CARGA:
            filas_cargadas += cargar(buffer)
            buffer = io.BytesIO()

    if buffer.tell():
        filas_cargadas += cargar(buffer)

    guardar_control(bucket, hasta)
    resumen = {"archivos": len(claves), "filas": filas_cargadas, "hasta": hasta.isoformat()}
    print(f"Exportación a BigQuery: {resumen}")
    return resumen


def cargar(buffer):
    buffer.seek(0)
    return bq.cargar_ndjson(TABLA, buffer)


def archivos_nuevos(bucket, desde, hasta):
    nuevos = []
    for pagina in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=PREFIJO):
        for objeto in pagina.get("Contents", []):
            if desde < objeto["LastModified"] <= hasta and objeto["Key"].endswith(".jsonl"):
                nuevos.append((objeto["LastModified"], objeto["Key"]))
    return [clave for _, clave in sorted(nuevos)]


def leer_control(bucket):
    try:
        cuerpo = s3.get_object(Bucket=bucket, Key=CLAVE_CONTROL)["Body"].read()
        return datetime.fromisoformat(json.loads(cuerpo)["hasta"])
    except s3.exceptions.NoSuchKey:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)


def guardar_control(bucket, hasta):
    s3.put_object(
        Bucket=bucket,
        Key=CLAVE_CONTROL,
        Body=json.dumps({"hasta": hasta.isoformat()}).encode("utf-8"),
        ContentType="application/json",
    )