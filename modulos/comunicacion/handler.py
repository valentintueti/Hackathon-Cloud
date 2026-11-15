import json
import os
import uuid
from datetime import datetime, timezone

import boto3

import plantillas
from comun.ddb import a_dynamo, actualizar, tabla

sns = boto3.client("sns")
sfn = boto3.client("stepfunctions")

TOPICS_POR_ROL = {
    "operador": os.environ.get("TOPIC_OPERADOR"),
    "tecnico": os.environ.get("TOPIC_TECNICO"),
    "jefe-mantenimiento": os.environ.get("TOPIC_JEFE_MANTENIMIENTO"),
    "supervisor": os.environ.get("TOPIC_SUPERVISOR"),
    "gerencia": os.environ.get("TOPIC_GERENCIA"),
}

CADENA_ESCALAMIENTO = {
    "jefe-mantenimiento": ["supervisor", "gerencia"],
    "supervisor": ["gerencia"],
}

EVENTO_ALERTA_CREADA = os.environ.get("EVENTO_ALERTA_CREADA", "AlertaCreada")
EVENTO_ORDEN_CREADA = os.environ.get("EVENTO_ORDEN_CREADA", "OrdenCreada")
EVENTO_ORDEN_CERRADA = os.environ.get("EVENTO_ORDEN_CERRADA", "OrdenCerrada")
TIEMPO_LIMITE_CONFIRMACION_SEGUNDOS = int(os.environ.get("TIEMPO_LIMITE_CONFIRMACION_SEGUNDOS", 900))


def iniciar(event, context):
    respuesta = sfn.start_execution(
        stateMachineArn=os.environ["STATE_MACHINE_ARN"],
        input=json.dumps(event, default=str),
    )
    return {"executionArn": respuesta["executionArn"]}


def clasificar(event, context):
    detalle = event.get("detail", {})
    tipo_evento = event.get("detail-type")

    if tipo_evento == EVENTO_ALERTA_CREADA:
        return _clasificar_alerta(detalle)
    if tipo_evento == EVENTO_ORDEN_CREADA:
        return _clasificar_orden_creada(detalle)
    if tipo_evento == EVENTO_ORDEN_CERRADA:
        return _clasificar_orden_cerrada(detalle)

    return {
        "rolesInformativos": [],
        "rolPrincipal": None,
        "mensajes": {},
        "requiereConfirmacion": False,
        "tiempoLimiteSegundos": TIEMPO_LIMITE_CONFIRMACION_SEGUNDOS,
        "incidenteRef": {},
        "severidad": "desconocida",
        "cadenaEscalamiento": [],
    }


def enviar(event, context):
    paquete = event
    notificaciones = tabla("TABLA_NOTIFICACION")
    ahora = datetime.now(timezone.utc).isoformat()
    incidente_ref = paquete.get("incidenteRef", {})
    maquina_id = incidente_ref.get("maquinaId") or "desconocida"

    roles_a_notificar = list(paquete.get("rolesInformativos", []))
    rol_principal = paquete.get("rolPrincipal")
    if rol_principal and rol_principal not in roles_a_notificar:
        roles_a_notificar.append(rol_principal)

    notificacion_principal_id = None
    for rol in roles_a_notificar:
        topic_arn = TOPICS_POR_ROL.get(rol)
        if not topic_arn:
            continue

        mensaje = paquete.get("mensajes", {}).get(rol, f"Notificacion para {rol}")
        notificacion_id = str(uuid.uuid4())
        es_principal = rol == rol_principal

        notificaciones.put_item(
            Item={
                "notificacion_id": notificacion_id,
                "maquina_id": maquina_id,
                "rol": rol,
                "mensaje": mensaje,
                "estado": "enviada",
                "requiere_confirmacion": es_principal,
                "incidente_ref": a_dynamo(incidente_ref),
                "ts_enviado": ahora,
            }
        )
        sns.publish(TopicArn=topic_arn, Message=mensaje, Subject=f"ArquiFusion - {rol}")

        if es_principal:
            notificacion_principal_id = notificacion_id

    return {
        "requiereConfirmacion": bool(rol_principal) and notificacion_principal_id is not None,
        "tiempoLimiteSegundos": paquete.get("tiempoLimiteSegundos", TIEMPO_LIMITE_CONFIRMACION_SEGUNDOS),
        "notificacionPrincipalId": notificacion_principal_id,
        "paquete": paquete,
    }


def verificar_confirmacion(event, context):
    if not event.get("requiereConfirmacion"):
        return {"confirmado": True, "escalar": False}

    notificacion_id = event.get("notificacionPrincipalId")
    notificaciones = tabla("TABLA_NOTIFICACION")
    item = notificaciones.get_item(Key={"notificacion_id": notificacion_id}).get("Item") if notificacion_id else None

    if item and item.get("estado") == "confirmada":
        return {"confirmado": True, "escalar": False}

    paquete = event.get("paquete", {})
    cadena = paquete.get("cadenaEscalamiento", [])

    if item:
        actualizar(notificaciones, clave={"notificacion_id": notificacion_id}, campos={"estado": "escalada"})

    if not cadena:
        return {"confirmado": False, "escalar": False}

    siguiente_rol = cadena[0]
    incidente_ref = paquete.get("incidenteRef", {})

    nuevo_paquete = dict(paquete)
    nuevo_paquete["rolesInformativos"] = []
    nuevo_paquete["rolPrincipal"] = siguiente_rol
    nuevo_paquete["cadenaEscalamiento"] = cadena[1:]
    nuevo_paquete["mensajes"] = plantillas.generar_mensajes(
        "escalada", paquete.get("severidad", ""), incidente_ref, {siguiente_rol}
    )

    return {"confirmado": False, "escalar": True, "paqueteEscalado": nuevo_paquete}


def confirmar(event, context):
    notificacion_id = event.get("pathParameters", {}).get("notificacion_id")
    if not notificacion_id:
        return _respuesta_http(400, {"error": "Falta notificacion_id en la ruta"})

    try:
        cuerpo = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _respuesta_http(400, {"error": "El cuerpo no es JSON valido"})

    notificaciones = tabla("TABLA_NOTIFICACION")
    item = notificaciones.get_item(Key={"notificacion_id": notificacion_id}).get("Item")
    if not item:
        return _respuesta_http(404, {"error": "Notificacion no encontrada"})

    actualizar(
        notificaciones,
        clave={"notificacion_id": notificacion_id},
        campos={
            "estado": "confirmada",
            "confirmada_por": cuerpo.get("confirmado_por", ""),
            "ts_confirmada": datetime.now(timezone.utc).isoformat(),
        },
    )
    return _respuesta_http(200, {"notificacionId": notificacion_id, "estado": "confirmada"})


def registrar_destinatario(event, context):
    try:
        cuerpo = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _respuesta_http(400, {"error": "El cuerpo no es JSON valido"})

    rol = cuerpo.get("rol")
    contacto = cuerpo.get("contacto")
    nombre = cuerpo.get("nombre")
    if not rol or not contacto or not nombre:
        return _respuesta_http(400, {"error": "Faltan nombre, rol o contacto"})

    topic_arn = TOPICS_POR_ROL.get(rol)
    if not topic_arn:
        return _respuesta_http(400, {"error": f"Rol desconocido: {rol}"})

    protocolo = "email" if "@" in contacto else "sms"
    suscripcion = sns.subscribe(TopicArn=topic_arn, Protocol=protocolo, Endpoint=contacto)

    destinatario_id = str(uuid.uuid4())
    destinatarios = tabla("TABLA_DESTINATARIO")
    destinatarios.put_item(
        Item={
            "destinatario_id": destinatario_id,
            "nombre": nombre,
            "rol": rol,
            "contacto": contacto,
            "zona_id": cuerpo.get("zona_id", ""),
            "suscripcion_arn": suscripcion.get("SubscriptionArn", ""),
            "ts_registrado": datetime.now(timezone.utc).isoformat(),
        }
    )
    return _respuesta_http(201, {"destinatarioId": destinatario_id})


def _clasificar_alerta(detalle):
    severidad = detalle.get("severidad", "baja")
    maquina_id = detalle.get("maquina_id")
    incidente_ref = {"tipo": "alerta", "refId": detalle.get("alerta_id"), "maquinaId": maquina_id}

    roles_informativos = ["operador"]
    rol_principal = None
    if severidad in ("alta", "critica"):
        roles_informativos.append("tecnico")
        if severidad == "critica":
            rol_principal = "jefe-mantenimiento"
        else:
            roles_informativos.append("jefe-mantenimiento")

    roles_mensaje = set(roles_informativos + ([rol_principal] if rol_principal else []))
    mensajes = plantillas.generar_mensajes("alerta", severidad, detalle, roles_mensaje)

    return {
        "rolesInformativos": roles_informativos,
        "rolPrincipal": rol_principal,
        "mensajes": mensajes,
        "requiereConfirmacion": rol_principal is not None,
        "tiempoLimiteSegundos": TIEMPO_LIMITE_CONFIRMACION_SEGUNDOS,
        "incidenteRef": incidente_ref,
        "severidad": severidad,
        "cadenaEscalamiento": CADENA_ESCALAMIENTO.get(rol_principal, []) if rol_principal else [],
    }


def _clasificar_orden_creada(detalle):
    prioridad = detalle.get("prioridad") or (
        "alta" if detalle.get("severidad") in ("alta", "critica") else detalle.get("severidad", "media")
    )
    maquina_id = detalle.get("maquina_id")
    orden_id = detalle.get("orden_id")
    incidente_ref = {"tipo": "orden", "refId": orden_id, "maquinaId": maquina_id}

    roles_informativos = ["tecnico"]
    rol_principal = "jefe-mantenimiento" if prioridad in ("alta", "urgente") else None
    if rol_principal is None:
        roles_informativos.append("jefe-mantenimiento")

    roles_mensaje = set(roles_informativos + ([rol_principal] if rol_principal else []))
    mensajes = plantillas.generar_mensajes("orden_creada", prioridad, detalle, roles_mensaje)

    return {
        "rolesInformativos": roles_informativos,
        "rolPrincipal": rol_principal,
        "mensajes": mensajes,
        "requiereConfirmacion": rol_principal is not None,
        "tiempoLimiteSegundos": TIEMPO_LIMITE_CONFIRMACION_SEGUNDOS,
        "incidenteRef": incidente_ref,
        "severidad": prioridad,
        "cadenaEscalamiento": CADENA_ESCALAMIENTO.get(rol_principal, []) if rol_principal else [],
    }


def _clasificar_orden_cerrada(detalle):
    maquina_id = detalle.get("maquina_id")
    orden_id = detalle.get("orden_id")
    incidente_ref = {"tipo": "orden", "refId": orden_id, "maquinaId": maquina_id}

    roles_informativos = ["jefe-mantenimiento", "supervisor"]
    mensajes = plantillas.generar_mensajes("orden_cerrada", "informativa", detalle, set(roles_informativos))

    return {
        "rolesInformativos": roles_informativos,
        "rolPrincipal": None,
        "mensajes": mensajes,
        "requiereConfirmacion": False,
        "tiempoLimiteSegundos": TIEMPO_LIMITE_CONFIRMACION_SEGUNDOS,
        "incidenteRef": incidente_ref,
        "severidad": "informativa",
        "cadenaEscalamiento": [],
    }


def _respuesta_http(codigo, cuerpo):
    return {
        "statusCode": codigo,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps(cuerpo, ensure_ascii=False),
    }