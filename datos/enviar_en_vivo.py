import argparse
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

import boto3

from generar_datos import MAQUINAS, lectura_base, redondear


def url_nucleo(region, stage):
    cf = boto3.client("cloudformation", region_name=region)
    salidas = cf.describe_stacks(StackName=f"arquifusion-nucleo-{stage}")["Stacks"][0]["Outputs"]
    return next(o["OutputValue"] for o in salidas if o["OutputKey"] == "ServiceEndpoint").rstrip("/")


def horometros(region, stage):
    tabla = boto3.resource("dynamodb", region_name=region).Table(f"arquifusion-{stage}-maquina")
    items = tabla.scan(ProjectionExpression="maquina_id, horas_totales").get("Items", [])
    return {i["maquina_id"]: float(i.get("horas_totales", 0)) for i in items}


def lectura(m, horas, anomala=False):
    datos = lectura_base(m, datetime.now(timezone.utc), horas)
    if anomala:
        datos.update({"temperatura": 115, "vibracion": 8.6, "presion": 18.5, "consumo_combustible": 44, "rpm": 1900})
    return redondear(datos)


def enviar(url, lecturas):
    peticion = urllib.request.Request(
        f"{url}/telemetria",
        data=json.dumps(lecturas).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(peticion, timeout=30) as respuesta:
            return respuesta.status, respuesta.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8")


def main():
    parser = argparse.ArgumentParser(description="Envia telemetria en vivo en UNA peticion por ciclo (para la demo)")
    parser.add_argument("--stage", default="dev")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--intervalo", type=int, default=300)
    parser.add_argument("--ciclos", type=int, default=0)
    parser.add_argument("--anomalia", help="maquina_id que recibe una lectura anomala en el primer ciclo")
    parser.add_argument("--masivo", help="zona_id: 3 maquinas de la zona reciben lecturas anomalas, una cada 90 s")
    args = parser.parse_args()

    url = url_nucleo(args.region, args.stage)
    horas = horometros(args.region, args.stage)
    print(f"Enviando a {url}/telemetria cada {args.intervalo} s")

    if args.masivo:
        afectadas = [m for m in MAQUINAS if m["zona"] == args.masivo][:3]
        for i, m in enumerate(afectadas):
            if i:
                time.sleep(90)
            codigo, cuerpo = enviar(url, [lectura(m, horas.get(m["id"], 0), anomala=True)])
            print(f"Anomalia en {m['id']} ({args.masivo}): {codigo} {cuerpo}")

    ciclo = 0
    while True:
        ciclo += 1
        lote = [lectura(m, horas.get(m["id"], 0), anomala=(ciclo == 1 and m["id"] == args.anomalia)) for m in MAQUINAS]
        codigo, cuerpo = enviar(url, lote)
        print(f"Ciclo {ciclo}: {len(lote)} lecturas -> {codigo} {cuerpo}")
        for m in MAQUINAS:
            horas[m["id"]] = horas.get(m["id"], 0) + args.intervalo / 3600
        if args.ciclos and ciclo >= args.ciclos:
            break
        time.sleep(args.intervalo)


if __name__ == "__main__":
    main()
