import json
import uuid
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Key

import puntaje
from comun.config import env
from comun.ddb import a_dynamo, a_json, actualizar, tabla

sfn = boto3.client("stepfunctions")
sns = boto3.client("sns")
events = boto3.client("events")
maquinas = tabla("TABLA_MAQUINA")
tecnicos = tabla("TABLA_TECNICO")
asignaciones = tabla("TABLA_ASIGNACION")

JEFE = "jefe-mantenimiento"


def solicitar(event, context):
    orden = event["detail"]
    entrada = {
        "orden_id": str(orden["orden_id"]),
        "maquina_id": str(orden.get("maquina_id") or ""),
        "gravedad": orden.get("severidad") or orden.get("prioridad") or "media",
        "categoria": orden.get("categoria") or "general",
        "rechazados": [],
        "intentos": 0,
    }
    try:
        sfn.start_execution(
            stateMachineArn=env("STATE_MACHINE_ARN"),
            name=entrada["orden_id"],
            input=json.dumps(entrada),
        )
    except sfn.exceptions.ExecutionAlreadyExists:
        print(f"La orden {entrada['orden_id']} ya tiene una asignacion en curso; se ignora el evento repetido")
        return {"omitida": entrada["orden_id"]}
    print(f"Asignacion iniciada para la orden {entrada['orden_id']} (gravedad {entrada['gravedad']})")
    return entrada


def buscar_candidatos(event, context):
    maquina = {}
    if event.get("maquina_id"):
        maquina = maquinas.get_item(Key={"maquina_id": event["maquina_id"]}).get("Item", {})

    tiempos = json.loads(env("TIEMPOS_REPARACION_MIN", "{}"))
    categoria = str(event.get("categoria") or "general")
    candidatos = puntaje.ranking(
        _escanear_todo(tecnicos),
        maquina,
        categoria,
        event.get("rechazados", []),
        float(env("VELOCIDAD_KMH", "40")),
        float(tiempos.get(categoria.lower(), 0)),
        int(env("MAX_CANDIDATOS", "5")),
    )
    intentos = event.get("intentos", 0) + (0 if candidatos else 1)
    print(f"Orden {event['orden_id']}: {len(candidatos)} candidatos (busqueda sin candidatos #{intentos})")
    return _plano({**event, "candidatos": candidatos, "cantidad": len(candidatos), "intentos": intentos})


def asignar(event, context):
    for c in event.get("candidatos", []):
        try:
            actualizar(
                tecnicos,
                clave={"tecnico_id": c["tecnico_id"]},
                campos={"estado": "reservado"},
                condicion="#estado = :disponible",
                valores_extra={":disponible": "disponible"},
            )
        except tecnicos.meta.client.exceptions.ConditionalCheckFailedException:
            print(f"{c['tecnico_id']} ya fue reservado por otra orden; se prueba el siguiente")
            continue

        asignacion = {
            "asignacion_id": str(uuid.uuid4()),
            "orden_id": event["orden_id"],
            "maquina_id": event.get("maquina_id"),
            "tecnico_id": c["tecnico_id"],
            "estado": "pendiente",
            "puntaje": c["puntaje"],
            "justificacion": c["justificacion"],
            "gravedad": event.get("gravedad"),
            "ts_creada": _ahora(),
        }
        asignaciones.put_item(Item=a_dynamo(asignacion))
        print(f"Orden {event['orden_id']}: reservado {c['tecnico_id']} ({c['justificacion']})")
        return {**event, "asignado": True, "asignacion_id": asignacion["asignacion_id"], "tecnico_id": c["tecnico_id"]}

    return {**event, "asignado": False}


def guardar_token(event, context):
    asignacion_id = event["asignacion_id"]
    actualizar(asignaciones, clave={"asignacion_id": asignacion_id},
               campos={"token": event["token"], "ts_aviso": _ahora()})
    a = asignaciones.get_item(Key={"asignacion_id": asignacion_id})["Item"]
    _avisar(
        a["tecnico_id"],
        "Nueva orden de trabajo para ti",
        f"Se te propone la orden {a['orden_id']} (maquina {a.get('maquina_id')}, gravedad {a.get('gravedad')}). "
        f"Motivo: {a.get('justificacion')}. Tienes 15 minutos para responder con el id de asignacion {asignacion_id}.",
    )
    return {"esperando": asignacion_id}


def confirmar(event, context):
    ahora = _ahora()
    actualizar(asignaciones, clave={"asignacion_id": event["asignacion_id"]},
               campos={"estado": "aceptada", "ts_aceptada": ahora})

    tecnico = tecnicos.get_item(Key={"tecnico_id": event["tecnico_id"]}).get("Item", {})
    actualizar(tecnicos, clave={"tecnico_id": event["tecnico_id"]}, campos={
        "estado": "ocupado",
        "asignaciones_activas": int(tecnico.get("asignaciones_activas", 0) or 0) + 1,
    })

    _publicar("OrdenAsignada", {
        "orden_id": event["orden_id"],
        "maquina_id": event.get("maquina_id"),
        "tecnico_id": event["tecnico_id"],
        "asignacion_id": event["asignacion_id"],
        "gravedad": event.get("gravedad"),
        "ts_asignada": ahora,
    })
    print(f"Orden {event['orden_id']} asignada a {event['tecnico_id']}")
    return {"orden_id": event["orden_id"], "tecnico_id": event["tecnico_id"], "estado": "aceptada"}


def liberar(event, context):
    resultado = event["resultado"]
    campos = {"estado": resultado, "token": None, "ts_cierre": _ahora()}
    motivo = (event.get("respuesta") or {}).get("motivo")
    if motivo:
        campos["motivo"] = motivo
    actualizar(asignaciones, clave={"asignacion_id": event["asignacion_id"]}, campos=campos)

    try:
        actualizar(
            tecnicos,
            clave={"tecnico_id": event["tecnico_id"]},
            campos={"estado": "disponible"},
            condicion="#estado = :reservado",
            valores_extra={":reservado": "reservado"},
        )
    except tecnicos.meta.client.exceptions.ConditionalCheckFailedException:
        pass

    rechazados = event.get("rechazados", []) + [event["tecnico_id"]]
    print(f"Orden {event['orden_id']}: {event['tecnico_id']} {resultado}; rechazados: {rechazados}")
    sobrantes = ("respuesta", "error", "resultado", "asignado", "asignacion_id", "tecnico_id", "candidatos")
    return {**{k: v for k, v in event.items() if k not in sobrantes}, "rechazados": rechazados}


def avisar_jefe(event, context):
    rechazados = ", ".join(event.get("rechazados", [])) or "ninguno"
    _avisar(
        JEFE,
        f"Orden {event['orden_id']} sin tecnico disponible",
        f"No se encontro tecnico para la orden {event['orden_id']} (maquina {event.get('maquina_id')}, "
        f"categoria {event.get('categoria')}, gravedad {event.get('gravedad')}) tras {event.get('intentos')} busquedas. "
        f"Tecnicos que rechazaron o no respondieron: {rechazados}. Requiere asignacion manual.",
    )
    print(f"Aviso al jefe: orden {event['orden_id']} sin tecnico")
    return {"orden_id": event["orden_id"], "estado": "sin_tecnico"}


def responder(event, context):
    asignacion_id = (event.get("pathParameters") or {}).get("asignacion_id")
    try:
        datos = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _http(400, {"error": "El cuerpo no es JSON valido"})
    if not isinstance(datos.get("acepta"), bool):
        return _http(400, {"error": "Falta 'acepta' (true o false)"})

    a = asignaciones.get_item(Key={"asignacion_id": asignacion_id}).get("Item")
    if not a:
        return _http(404, {"error": "Asignacion no encontrada"})
    if a.get("estado") != "pendiente" or not a.get("token"):
        return _http(409, {"error": f"La asignacion ya no espera respuesta (estado: {a.get('estado')})"})

    token = a["token"]
    try:
        actualizar(
            asignaciones,
            clave={"asignacion_id": asignacion_id},
            campos={"token": None, "ts_respuesta": _ahora(), "motivo": datos.get("motivo")},
            condicion="#token = :token_usado",
            valores_extra={":token_usado": token},
        )
    except asignaciones.meta.client.exceptions.ConditionalCheckFailedException:
        return _http(409, {"error": "La asignacion ya fue respondida"})

    try:
        sfn.send_task_success(taskToken=token, output=json.dumps({"acepta": datos["acepta"], "motivo": datos.get("motivo")}))
    except (sfn.exceptions.TaskTimedOut, sfn.exceptions.InvalidToken, sfn.exceptions.TaskDoesNotExist):
        return _http(409, {"error": "La asignacion ya vencio"})

    return _http(200, {"asignacion_id": asignacion_id, "acepta": datos["acepta"]})


def completar(event, context):
    orden = event["detail"]
    lista = _consultar_todo(asignaciones, IndexName="por_orden",
                            KeyConditionExpression=Key("orden_id").eq(str(orden["orden_id"])))
    completadas = 0
    for a in lista:
        if a.get("estado") != "aceptada":
            continue
        actualizar(asignaciones, clave={"asignacion_id": a["asignacion_id"]},
                   campos={"estado": "completada", "ts_completada": _ahora()})
        tecnico = tecnicos.get_item(Key={"tecnico_id": a["tecnico_id"]}).get("Item", {})
        actualizar(tecnicos, clave={"tecnico_id": a["tecnico_id"]}, campos={
            "estado": "disponible",
            "asignaciones_activas": max(int(tecnico.get("asignaciones_activas", 0) or 0) - 1, 0),
        })
        completadas += 1
    print(f"Orden {orden['orden_id']} cerrada: {completadas} asignaciones completadas")
    return {"completadas": completadas}


def registrar_tecnico(event, context):
    try:
        datos = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _http(400, {"error": "El cuerpo no es JSON valido"})
    if not datos.get("nombre") or not datos.get("especialidades") or not datos.get("zona_id"):
        return _http(400, {"error": "Faltan nombre, especialidades o zona_id"})

    tecnico_id = str(datos.get("tecnico_id") or uuid.uuid4())
    previo = tecnicos.get_item(Key={"tecnico_id": tecnico_id}).get("Item", {})
    tecnico = {
        **previo,
        "tecnico_id": tecnico_id,
        "nombre": datos["nombre"],
        "contacto": datos.get("contacto") or previo.get("contacto"),
        "especialidades": [str(e).lower() for e in datos["especialidades"]],
        "zona_id": datos["zona_id"],
        "lat": datos.get("lat", previo.get("lat")),
        "lon": datos.get("lon", previo.get("lon")),
        "estado": previo.get("estado", "disponible"),
        "asignaciones_activas": previo.get("asignaciones_activas", 0),
        "ts_actualizado": _ahora(),
    }

    contacto = tecnico.get("contacto")
    if contacto and contacto != previo.get("contacto"):
        suscripcion = sns.subscribe(
            TopicArn=env("SNS_TOPIC_ARN"),
            Protocol="email" if "@" in contacto else "sms",
            Endpoint=contacto,
            Attributes={"FilterPolicy": json.dumps({"destinatario": [tecnico_id]})},
            ReturnSubscriptionArn=True,
        )
        tecnico["suscripcion_arn"] = suscripcion["SubscriptionArn"]

    tecnicos.put_item(Item=a_dynamo({k: v for k, v in tecnico.items() if v is not None}))
    return _http(200 if previo else 201, tecnico)


def listar_tecnicos(event, context):
    params = event.get("queryStringParameters") or {}
    lista = _escanear_todo(tecnicos)
    if params.get("zona"):
        lista = [t for t in lista if t.get("zona_id") == params["zona"]]
    if params.get("estado"):
        lista = [t for t in lista if t.get("estado") == params["estado"]]
    lista.sort(key=lambda t: str(t.get("nombre", "")))
    return _http(200, {"cantidad": len(lista), "tecnicos": lista})


def listar_asignaciones(event, context):
    params = event.get("queryStringParameters") or {}
    if params.get("orden"):
        lista = _consultar_todo(asignaciones, IndexName="por_orden",
                                KeyConditionExpression=Key("orden_id").eq(params["orden"]))
    elif params.get("tecnico"):
        lista = _consultar_todo(asignaciones, IndexName="por_tecnico",
                                KeyConditionExpression=Key("tecnico_id").eq(params["tecnico"]))
    else:
        lista = _escanear_todo(asignaciones)
    if params.get("estado"):
        lista = [a for a in lista if a.get("estado") == params["estado"]]
    for a in lista:
        a.pop("token", None)
    lista.sort(key=lambda a: str(a.get("ts_creada", "")), reverse=True)
    return _http(200, {"cantidad": len(lista), "asignaciones": lista})


def _avisar(destinatario, asunto, mensaje):
    sns.publish(
        TopicArn=env("SNS_TOPIC_ARN"),
        Subject=asunto[:100],
        Message=mensaje,
        MessageAttributes={"destinatario": {"DataType": "String", "StringValue": destinatario}},
    )


def _publicar(tipo, detalle):
    events.put_events(Entries=[{
        "EventBusName": env("BUS"),
        "Source": "arquifusion.asignacion",
        "DetailType": tipo,
        "Detail": a_json(detalle),
    }])


def _escanear_todo(tabla_ddb, **parametros):
    items = []
    while True:
        respuesta = tabla_ddb.scan(**parametros)
        items.extend(respuesta.get("Items", []))
        if "LastEvaluatedKey" not in respuesta:
            return items
        parametros["ExclusiveStartKey"] = respuesta["LastEvaluatedKey"]


def _consultar_todo(tabla_ddb, **parametros):
    items = []
    while True:
        respuesta = tabla_ddb.query(**parametros)
        items.extend(respuesta.get("Items", []))
        if "LastEvaluatedKey" not in respuesta:
            return items
        parametros["ExclusiveStartKey"] = respuesta["LastEvaluatedKey"]


def _ahora():
    return datetime.now(timezone.utc).isoformat()


def _plano(valor):
    return json.loads(a_json(valor))


def _http(codigo, cuerpo):
    return {
        "statusCode": codigo,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": a_json(cuerpo),
    }