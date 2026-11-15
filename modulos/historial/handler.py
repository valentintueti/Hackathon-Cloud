import json
import uuid
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Key

import logica
from comun.config import env
from comun.ddb import a_dynamo, a_json, actualizar, tabla

sfn = boto3.client("stepfunctions")
events = boto3.client("events")
ordenes = tabla("TABLA_ORDEN_TRABAJO")




def crear(event, context):
    try:
        datos = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _http(400, {"error": "El cuerpo no es JSON válido"})
    if not datos.get("maquina_id") or not datos.get("descripcion"):
        return _http(400, {"error": "Faltan maquina_id o descripcion"})
    if datos.get("severidad", "media") not in logica.SEVERIDADES:
        return _http(400, {"error": f"severidad debe ser una de {logica.SEVERIDADES}"})

    orden = _registrar_incidente(datos, origen="manual")
    return _http(201, orden)


def avanzar(event, context):
    orden_id = (event.get("pathParameters") or {}).get("orden_id")
    try:
        datos = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _http(400, {"error": "El cuerpo no es JSON válido"})

    orden = ordenes.get_item(Key={"orden_id": orden_id}).get("Item")
    if not orden:
        return _http(404, {"error": "Incidente no encontrado"})

    nuevo = datos.get("estado")
    if orden.get("tipo") == "preventivo" and nuevo == "hecha":
        return _http(409, {"error": "Las órdenes preventivas se completan con POST /ordenes/{orden_id}/completar del módulo preventivo"})
    if not logica.transicion_valida(orden.get("estado"), nuevo):
        esperado = logica.TRANSICIONES.get(orden.get("estado"))
        return _http(409, {"error": f"De '{orden.get('estado')}' solo se puede pasar a '{esperado}'"})

    campos = {"estado": nuevo, logica.CAMPO_TS[nuevo]: _ahora()}
    for campo in ("tecnico_id", "trabajo_realizado", "causa_raiz", "componentes_reemplazados", "observaciones"):
        if datos.get(campo) is not None:
            campos[campo] = datos[campo]
    actualizar(ordenes, clave={"orden_id": orden_id}, campos=campos)

    if orden.get("token_pendiente") and orden.get("etapa_esperada") == nuevo:
        _reanudar(orden_id, orden["token_pendiente"], nuevo)

    return _http(200, {"orden_id": orden_id, "estado": nuevo})


def historial(event, context):
    maquina_id = (event.get("pathParameters") or {}).get("maquina_id")
    lista = _ordenes_de_maquina(maquina_id)
    for o in lista:
        o.update({k: v for k, v in logica.tiempos(o).items() if o.get(k) is None})
        o.pop("token_pendiente", None)
    return _http(200, {"maquina_id": maquina_id, "resumen": logica.resumen(lista), "incidentes": lista})



def guardar_token(event, context):
    actualizar(
        ordenes,
        clave={"orden_id": event["orden_id"]},
        campos={"token_pendiente": event["token"], "etapa_esperada": event["etapa"]},
    )
    orden = ordenes.get_item(Key={"orden_id": event["orden_id"]}).get("Item", {})
    estado = orden.get("estado")
    if estado in logica.ESTADOS and logica.ESTADOS.index(estado) >= logica.ESTADOS.index(event["etapa"]):
        _reanudar(event["orden_id"], event["token"], event["etapa"])
    return {"esperando": event["etapa"]}


def _reanudar(orden_id, token, etapa):
    try:
        actualizar(
            ordenes,
            clave={"orden_id": orden_id},
            campos={"token_pendiente": None, "etapa_esperada": None},
            condicion="#token_pendiente = :token_usado",
            valores_extra={":token_usado": token},
        )
    except ordenes.meta.client.exceptions.ConditionalCheckFailedException:
        return
    try:
        sfn.send_task_success(taskToken=token, output=json.dumps({"estado": etapa}))
    except (sfn.exceptions.TaskTimedOut, sfn.exceptions.InvalidToken, sfn.exceptions.TaskDoesNotExist) as error:
        print(f"No se pudo reanudar la orden {orden_id} ({etapa}): {error}")


def cerrar(event, context):
    orden = ordenes.get_item(Key={"orden_id": event["orden_id"]})["Item"]
    calculados = logica.tiempos(orden)
    actualizar(ordenes, clave={"orden_id": event["orden_id"]}, campos=calculados)
    _publicar("OrdenCerrada", {**orden, **calculados})
    return {"orden_id": event["orden_id"], **calculados}



def desde_alerta(event, context):
    alerta = event["detail"]
    if not alerta.get("maquina_id"):
        return {"omitida": "alerta sin maquina_id"}
    abierta = next(
        (o for o in _ordenes_de_maquina(str(alerta["maquina_id"]))
         if o.get("tipo", "correctivo") == "correctivo" and o.get("estado") != "hecha"),
        None,
    )
    if abierta:
        return {"omitida": f"la maquina ya tiene el incidente abierto {abierta['orden_id']}"}
    datos = {
        "maquina_id": alerta["maquina_id"],
        "descripcion": f"Alerta automática: {', '.join(alerta.get('variables_afectadas', [])) or alerta.get('tipo', 'anomalía')}",
        "severidad": alerta.get("severidad", "alta"),
        "categoria": alerta.get("categoria") or alerta.get("tipo"),
        "alerta_id": alerta.get("alerta_id"),
    }
    return _registrar_incidente(datos, origen="alerta")


def _registrar_incidente(datos, origen):
    orden = {
        "orden_id": str(uuid.uuid4()),
        "maquina_id": str(datos["maquina_id"]),
        "ts_creada": _ahora(),
        "tipo": "correctivo",
        "estado": "pendiente",
        "origen": origen,
        "descripcion": datos["descripcion"],
        "severidad": datos.get("severidad", "media"),
        "categoria": datos.get("categoria", "general"),
    }
    if datos.get("alerta_id"):
        orden["alerta_id"] = datos["alerta_id"]

    previa = logica.buscar_reincidencia(orden, _ordenes_de_maquina(orden["maquina_id"]), int(env("DIAS_REINCIDENCIA", "30")))
    if previa:
        orden["reincidente_de"] = previa

    ordenes.put_item(Item=a_dynamo(orden))
    sfn.start_execution(
        stateMachineArn=env("STATE_MACHINE_ARN"),
        name=orden["orden_id"],  # una ejecución por incidente, con el mismo id
        input=json.dumps({"orden_id": orden["orden_id"]}),
    )
    _publicar("OrdenCreada", orden)
    return orden


def _ordenes_de_maquina(maquina_id):
    items, parametros = [], {
        "IndexName": "por_maquina",
        "KeyConditionExpression": Key("maquina_id").eq(maquina_id),
        "ScanIndexForward": False,  # más recientes primero
    }
    while True:
        respuesta = ordenes.query(**parametros)
        items.extend(respuesta.get("Items", []))
        if "LastEvaluatedKey" not in respuesta:
            return items
        parametros["ExclusiveStartKey"] = respuesta["LastEvaluatedKey"]


def _publicar(tipo, detalle):
    events.put_events(Entries=[{
        "EventBusName": env("BUS"),
        "Source": "arquifusion.historial",
        "DetailType": tipo,
        "Detail": a_json({k: v for k, v in detalle.items() if k != "token_pendiente"}),
    }])


def _ahora():
    return datetime.now(timezone.utc).isoformat()


def _http(codigo, cuerpo):
    return {
        "statusCode": codigo,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": a_json(cuerpo),
    }