import json
import uuid
from collections import defaultdict
from datetime import datetime, timezone

import boto3

from comun.config import env
from comun.ddb import actualizar, tabla

s3 = boto3.client("s3")
events = boto3.client("events")
maquinas = tabla("TABLA_MAQUINA")

LECTURAS_POR_EVENTO = 20
EVENTOS_POR_LLAMADA = 10 

CAMPOS_DE_ESTADO = {
    "zona_id": "zona_id",
    "modelo_id": "modelo_id",
    "lat": "lat",
    "lon": "lon",
    "estado": "estado",
    "horas_funcionamiento": "horas_totales",
}


def handler(event, context):
    validas, fallidas = [], []
    for registro in event["Records"]:
        try:
            lectura = json.loads(registro["body"])
            actualizar_estado(lectura)
            validas.append(lectura)
        except Exception as error:
            print(f"Error en el mensaje {registro['messageId']}: {error}")
            fallidas.append({"itemIdentifier": registro["messageId"]})

    if validas:
        guardar_historico(validas)
        publicar_evento(validas)

    print(f"Procesadas: {len(validas)} | Fallidas: {len(fallidas)}")
    return {"batchItemFailures": fallidas}


def actualizar_estado(lectura):
    campos = {
        "ultima_lectura": lectura,
        "ultima_lectura_ts": lectura["ts"],
        "ultima_recepcion_ts": datetime.now(timezone.utc).isoformat(),
    }
    for origen, destino in CAMPOS_DE_ESTADO.items():
        if lectura.get(origen) is not None:
            campos[destino] = lectura[origen]
    try:
        actualizar(
            maquinas,
            clave={"maquina_id": str(lectura["maquina_id"])},
            campos=campos,
            condicion="attribute_not_exists(#ultima_lectura_ts) OR #ultima_lectura_ts < :ts_nuevo",
            valores_extra={":ts_nuevo": lectura["ts"]},
        )
    except maquinas.meta.client.exceptions.ConditionalCheckFailedException:
        pass


def guardar_historico(lecturas):
    bucket = env("BUCKET_TELEMETRIA")
    por_fecha = defaultdict(list)
    for lectura in lecturas:
        por_fecha[str(lectura["ts"])[:10]].append(lectura)  # "AAAA-MM-DD"
    for fecha, grupo in por_fecha.items():
        s3.put_object(
            Bucket=bucket,
            Key=f"telemetria/fecha={fecha}/{uuid.uuid4()}.jsonl",
            Body="\n".join(json.dumps(l) for l in grupo).encode("utf-8"),
            ContentType="application/x-ndjson",
        )


def publicar_evento(lecturas):
    bus = env("BUS")
    entradas = [
        {
            "EventBusName": bus,
            "Source": "arquifusion.nucleo",
            "DetailType": "LecturasProcesadas",
            "Detail": json.dumps({"lecturas": lecturas[i:i + LECTURAS_POR_EVENTO]}),
        }
        for i in range(0, len(lecturas), LECTURAS_POR_EVENTO)
    ]
    for i in range(0, len(entradas), EVENTOS_POR_LLAMADA):
        resultado = events.put_events(Entries=entradas[i:i + EVENTOS_POR_LLAMADA])
        if resultado.get("FailedEntryCount"):
            print(f"EventBridge rechazó {resultado['FailedEntryCount']} eventos: {resultado['Entries']}")