import json
import logging
import os
import uuid
from datetime import date, datetime, timedelta, timezone

import boto3

from comun.bq import consultar
from comun.config import env
from comun.ddb import a_dynamo, actualizar, tabla

logger = logging.getLogger()
logger.setLevel(logging.INFO)

sns = boto3.client("sns")
events = boto3.client("events")

EVENTOS_POR_LLAMADA = 10

UMBRAL_ORDEN_PCT = float(os.environ.get("UMBRAL_ORDEN_PCT", 90))
UMBRAL_PRIORIDAD_ALTA_PCT = float(os.environ.get("UMBRAL_PRIORIDAD_ALTA_PCT", 100))
INTERVALO_DEFECTO_HORAS = float(os.environ.get("INTERVALO_DEFECTO_HORAS", 250))
CAPACIDAD_DEFECTO = float(os.environ.get("CAPACIDAD_DEFECTO", 100))
RPM_NOMINAL = float(os.environ.get("RPM_NOMINAL", 1800))
TEMPERATURA_NOMINAL = float(os.environ.get("TEMPERATURA_NOMINAL", 80))
FACTOR_MIN = float(os.environ.get("FACTOR_MIN", 0.5))
FACTOR_MAX = float(os.environ.get("FACTOR_MAX", 1.5))
VENTANA_RESPALDO_DIAS = int(os.environ.get("VENTANA_RESPALDO_DIAS", 400))

PESO_CARGA = 0.5
PESO_RPM = 0.3
PESO_TEMPERATURA = 0.2

RUTA_SQL = os.path.join(os.path.dirname(__file__), "sql", "indice_uso.sql")


def calcular_indice(event, context):
    maquinas_tabla = tabla("TABLA_MAQUINA")
    modelos_tabla = tabla("TABLA_MODELO")

    maquinas = _escanear_todo(maquinas_tabla)
    if not maquinas:
        return {"maquinasPorAtender": 0, "detalle": []}

    fecha_desde_global = _fecha_mas_antigua(maquinas)
    resumen_por_maquina = _resumen_diario_bigquery(fecha_desde_global)

    cache_modelos = {}
    maquinas_por_atender = 0
    detalle = []

    for maquina in maquinas:
        maquina_id = maquina["maquina_id"]
        fecha_ult_mantenimiento = _parsear_fecha(maquina.get("fecha_ult_mantenimiento"))

        modelo_id = maquina.get("modelo_id")
        if modelo_id not in cache_modelos:
            cache_modelos[modelo_id] = modelos_tabla.get_item(
                Key={"modelo_id": modelo_id}
            ).get("Item", {}) if modelo_id else {}
        modelo = cache_modelos[modelo_id]
        modelo_cargado = bool(modelo.get("capacidad") and modelo.get("intervalo"))

        capacidad = float(modelo.get("capacidad", CAPACIDAD_DEFECTO))
        intervalo_base = float(modelo.get("intervalo", INTERVALO_DEFECTO_HORAS))

        dias = resumen_por_maquina.get(maquina_id, [])
        horas_efectivas = 0.0
        for dia in dias:
            if dia["dia"] < fecha_ult_mantenimiento:
                continue
            if dia["horas_trabajadas_dia"] is None:
                continue

            factor = _factor_de_uso(
                carga_promedio=dia.get("carga_promedio"),
                rpm_promedio=dia.get("rpm_promedio"),
                temperatura_promedio=dia.get("temperatura_promedio"),
                capacidad=capacidad,
            )
            horas_efectivas += max(dia["horas_trabajadas_dia"], 0.0) * factor

        porcentaje_intervalo = (horas_efectivas / intervalo_base * 100) if intervalo_base else 0.0

        actualizar(
            maquinas_tabla,
            clave={"maquina_id": maquina_id},
            campos={
                "horas_efectivas_ciclo": round(horas_efectivas, 2),
                "porcentaje_intervalo": round(porcentaje_intervalo, 2),
                "indice_calculado_en": datetime.now(timezone.utc).isoformat(),
            },
        )

        if porcentaje_intervalo >= UMBRAL_ORDEN_PCT:
            maquinas_por_atender += 1
            detalle.append(
                {
                    "maquinaId": maquina_id,
                    "porcentajeIntervalo": round(porcentaje_intervalo, 2),
                    "horasEfectivas": round(horas_efectivas, 2),
                    "modeloCargado": modelo_cargado,
                }
            )

    logger.info(
        "Calculadas %s maquinas; %s sobre el %.0f%% de su intervalo",
        len(maquinas),
        maquinas_por_atender,
        UMBRAL_ORDEN_PCT,
    )
    return {"maquinasPorAtender": maquinas_por_atender, "detalle": detalle}


def crear_ordenes(event, context):
    detalle = event.get("resultadoCalculo", {}).get("detalle", [])
    if not detalle:
        return {"ordenesCreadas": []}

    ordenes_tabla = tabla("TABLA_ORDEN_TRABAJO")
    ahora = datetime.now(timezone.utc).isoformat()
    ordenes_creadas = []
    omitidas_por_duplicado = []

    for item in detalle:
        if _tiene_orden_preventiva_abierta(ordenes_tabla, item["maquinaId"]):
            omitidas_por_duplicado.append(item["maquinaId"])
            continue

        prioridad = "alta" if item["porcentajeIntervalo"] >= UMBRAL_PRIORIDAD_ALTA_PCT else "media"
        orden_id = str(uuid.uuid4())

        ordenes_tabla.put_item(
            Item={
                "orden_id": orden_id,
                "maquina_id": item["maquinaId"],
                "ts_creada": ahora,
                "tipo": "preventivo",
                "prioridad": prioridad,
                "porcentaje_intervalo": a_dynamo(item["porcentajeIntervalo"]),
                "horas_efectivas": a_dynamo(item["horasEfectivas"]),
                "estado": "pendiente",
            }
        )
        ordenes_creadas.append({**item, "ordenId": orden_id, "prioridad": prioridad})

    if ordenes_creadas:
        sns.publish(
            TopicArn=env("SNS_TOPIC_ARN"),
            Subject="Nuevas ordenes de mantenimiento preventivo",
            Message=json.dumps(
                {
                    "tipo": "mantenimiento-preventivo",
                    "ordenes": ordenes_creadas,
                    "omitidasPorYaTenerOrdenAbierta": omitidas_por_duplicado,
                },
                ensure_ascii=False,
            ),
        )
        _publicar_eventos(
            "OrdenCreada",
            [
                {
                    "orden_id": orden["ordenId"],
                    "maquina_id": orden["maquinaId"],
                    "tipo": "preventivo",
                    "prioridad": orden["prioridad"],
                    "porcentaje_intervalo": orden["porcentajeIntervalo"],
                }
                for orden in ordenes_creadas
            ],
        )

    logger.info(
        "Ordenes creadas: %s | omitidas por duplicado: %s",
        len(ordenes_creadas),
        len(omitidas_por_duplicado),
    )
    return {"ordenesCreadas": ordenes_creadas, "omitidas": omitidas_por_duplicado}


def completar_orden(event, context):
    orden_id = event.get("pathParameters", {}).get("orden_id")
    if not orden_id:
        return _respuesta_http(400, {"error": "Falta orden_id en la ruta"})

    ordenes_tabla = tabla("TABLA_ORDEN_TRABAJO")
    orden = ordenes_tabla.get_item(Key={"orden_id": orden_id}).get("Item")
    if not orden:
        return _respuesta_http(404, {"error": "Orden no encontrada"})

    hoy = date.today().isoformat()
    ahora = datetime.now(timezone.utc).isoformat()

    actualizar(
        ordenes_tabla,
        clave={"orden_id": orden_id},
        campos={"estado": "hecha", "ts_completada": ahora},
    )

    if orden.get("tipo") == "preventivo":
        maquinas_tabla = tabla("TABLA_MAQUINA")
        actualizar(
            maquinas_tabla,
            clave={"maquina_id": orden["maquina_id"]},
            campos={
                "fecha_ult_mantenimiento": hoy,
                "horas_efectivas_ciclo": 0,
                "porcentaje_intervalo": 0,
            },
        )

    _publicar_eventos(
        "OrdenCerrada",
        [
            {
                "orden_id": orden_id,
                "maquina_id": orden["maquina_id"],
                "tipo": orden.get("tipo"),
                "ts_cerrado": ahora,
            }
        ],
    )

    return _respuesta_http(200, {"ordenId": orden_id, "estado": "hecha"})


def _resumen_diario_bigquery(fecha_desde_global):
    with open(RUTA_SQL, encoding="utf-8") as archivo:
        sql = archivo.read()

    fecha_param = date.fromisoformat(str(fecha_desde_global)[:10])

    filas = consultar(sql, {"fecha_desde_global": fecha_param})

    resumen = {}
    for fila in filas:
        resumen.setdefault(fila["maquina_id"], []).append(
            {
                "dia": _texto_fecha(fila["dia"]),
                "horas_trabajadas_dia": fila.get("horas_trabajadas_dia"),
                "carga_promedio": fila.get("carga_promedio"),
                "rpm_promedio": fila.get("rpm_promedio"),
                "temperatura_promedio": fila.get("temperatura_promedio"),
            }
        )
    return resumen


def _texto_fecha(valor):
    return valor.isoformat() if hasattr(valor, "isoformat") else str(valor)


def _factor_de_uso(carga_promedio, rpm_promedio, temperatura_promedio, capacidad):
    desvio_carga = (carga_promedio / capacidad - 1) if carga_promedio is not None and capacidad else 0.0
    desvio_rpm = (rpm_promedio / RPM_NOMINAL - 1) if rpm_promedio is not None else 0.0
    desvio_temp = (
        (temperatura_promedio / TEMPERATURA_NOMINAL - 1) if temperatura_promedio is not None else 0.0
    )

    factor = 1 + PESO_CARGA * desvio_carga + PESO_RPM * desvio_rpm + PESO_TEMPERATURA * desvio_temp
    return max(FACTOR_MIN, min(factor, FACTOR_MAX))


def _tiene_orden_preventiva_abierta(ordenes_tabla, maquina_id):
    respuesta = ordenes_tabla.query(
        IndexName="por_maquina",
        KeyConditionExpression="maquina_id = :id",
        FilterExpression="tipo = :tipo AND estado <> :hecha",
        ExpressionAttributeValues={
            ":id": maquina_id,
            ":tipo": "preventivo",
            ":hecha": "hecha",
        },
    )
    return respuesta.get("Count", 0) > 0


def _fecha_mas_antigua(maquinas):
    fechas = [
        _parsear_fecha(m.get("fecha_ult_mantenimiento"))
        for m in maquinas
        if m.get("fecha_ult_mantenimiento")
    ]
    if fechas:
        return min(fechas)
    return (date.today() - timedelta(days=VENTANA_RESPALDO_DIAS)).isoformat()


def _parsear_fecha(valor):
    if not valor:
        return (date.today() - timedelta(days=VENTANA_RESPALDO_DIAS)).isoformat()
    return valor


def _escanear_todo(tabla_ddb):
    items = []
    respuesta = tabla_ddb.scan()
    items.extend(respuesta.get("Items", []))
    while "LastEvaluatedKey" in respuesta:
        respuesta = tabla_ddb.scan(ExclusiveStartKey=respuesta["LastEvaluatedKey"])
        items.extend(respuesta.get("Items", []))
    return items


def _publicar_eventos(detail_type, detalles):
    bus = env("BUS")
    entradas = [
        {
            "EventBusName": bus,
            "Source": "arquifusion.preventivo",
            "DetailType": detail_type,
            "Detail": json.dumps(detalle, ensure_ascii=False),
        }
        for detalle in detalles
    ]
    for i in range(0, len(entradas), EVENTOS_POR_LLAMADA):
        resultado = events.put_events(Entries=entradas[i : i + EVENTOS_POR_LLAMADA])
        if resultado.get("FailedEntryCount"):
            logger.error(
                "EventBridge rechazo %s eventos: %s",
                resultado["FailedEntryCount"],
                resultado["Entries"],
            )


def _respuesta_http(codigo, cuerpo):
    return {
        "statusCode": codigo,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps(cuerpo, ensure_ascii=False),
    }