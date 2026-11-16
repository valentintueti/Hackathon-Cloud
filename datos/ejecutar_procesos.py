import argparse
import json
import time

import boto3
from botocore.config import Config

PROCESOS = ["lineas-base", "preventivo", "combustible", "productividad", "planificacion", "repuestos"]


def exportar(region, stage, espera):
    if espera:
        print(f"Esperando {espera} s para que la exportacion tome los archivos recien subidos...")
        time.sleep(espera)
    cliente = boto3.client("lambda", region_name=region,
                           config=Config(read_timeout=400, retries={"max_attempts": 0}))
    print("Exportando telemetria de S3 a BigQuery (una sola Lambda)...")
    respuesta = cliente.invoke(FunctionName=f"arquifusion-nucleo-{stage}-exportarBigquery",
                               InvocationType="RequestResponse")
    cuerpo = json.loads(respuesta["Payload"].read() or "null")
    if respuesta.get("FunctionError"):
        raise SystemExit(f"La exportacion fallo: {cuerpo}")
    print(f"  {cuerpo}")


def ejecutar(sfn, arn, limite_s):
    try:
        ejecucion = sfn.start_execution(stateMachineArn=arn, input="{}")["executionArn"]
    except sfn.exceptions.StateMachineDoesNotExist:
        return "NO_DESPLEGADO", None
    inicio = time.time()
    while True:
        detalle = sfn.describe_execution(executionArn=ejecucion)
        if detalle["status"] != "RUNNING":
            return detalle["status"], detalle
        if time.time() - inicio > limite_s:
            return "SIGUE_CORRIENDO", detalle
        time.sleep(5)


def main():
    parser = argparse.ArgumentParser(description="Exporta a BigQuery y ejecuta los procesos diarios uno por uno")
    parser.add_argument("--stage", default="dev")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--esperar", type=int, default=150)
    parser.add_argument("--sin-exportar", action="store_true")
    parser.add_argument("--solo", nargs="*", choices=PROCESOS)
    parser.add_argument("--pausa", type=int, default=20)
    args = parser.parse_args()

    if not args.sin_exportar:
        exportar(args.region, args.stage, args.esperar)

    cuenta = boto3.client("sts", region_name=args.region).get_caller_identity()["Account"]
    sfn = boto3.client("stepfunctions", region_name=args.region)
    for proceso in args.solo or PROCESOS:
        arn = f"arn:aws:states:{args.region}:{cuenta}:stateMachine:{proceso}-{args.stage}"
        print(f"{proceso}: ejecutando...")
        estado, detalle = ejecutar(sfn, arn, 900)
        if estado == "SUCCEEDED":
            print(f"  OK -> {(detalle.get('output') or '')[:300]}")
        elif estado == "NO_DESPLEGADO":
            print("  se omite: la Step Function no existe (modulo no desplegado)")
            continue
        else:
            print(f"  {estado}: {detalle.get('error', '')} {(detalle.get('cause') or '')[:500]}")
        time.sleep(args.pausa)
    print("Listo.")


if __name__ == "__main__":
    main()
