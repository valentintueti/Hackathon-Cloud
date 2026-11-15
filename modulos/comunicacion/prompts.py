import json

SISTEMA = (
    "Eres el asistente de comunicaciones de ArquiFusion, empresa de maquinaria pesada. "
    "Redactas avisos en español, claros y directos, en texto plano sin markdown ni emojis. "
    "Usa solo los datos que se te entregan: no inventes valores, causas, nombres ni plazos. "
    "Si un dato no esta, no lo menciones. "
    "Responde unicamente un objeto JSON cuyas claves son los roles pedidos y cuyos valores son los mensajes."
)

ROLES = {
    "operador": "Operador de la maquina. Necesita saber si debe detenerse o tener precaucion. Maximo 300 caracteres, puede llegar por SMS.",
    "tecnico": "Tecnico de campo. Necesita que variables revisar, valores observados y por donde empezar. Maximo 600 caracteres.",
    "jefe-mantenimiento": "Jefe de mantenimiento. Necesita gravedad, maquina, zona y que decision tomar (asignar, priorizar). Maximo 500 caracteres.",
    "supervisor": "Supervisor de operaciones. Necesita el impacto en la operacion de la zona y si hay maquinas detenidas. Maximo 400 caracteres.",
    "gerencia": "Gerencia. Necesita el impacto en la operacion y el riesgo, sin detalle tecnico. Maximo 400 caracteres.",
}

EVENTOS = {
    "alerta": "Se detecto una alerta en la flota",
    "orden_creada": "Se creo una orden de trabajo",
    "orden_cerrada": "Se cerro una orden de trabajo",
}

CAMPOS_EXCLUIDOS = {"token_pendiente", "etapa_esperada"}


def construir(tipo_evento, severidad, datos, roles):
    contexto = {k: v for k, v in datos.items() if k not in CAMPOS_EXCLUIDOS and v not in (None, "", [], {})}
    lineas = [
        f"Evento: {EVENTOS.get(tipo_evento, tipo_evento)}.",
        f"Severidad o prioridad: {severidad}.",
        "Datos del evento:",
        json.dumps(contexto, ensure_ascii=False, default=str),
        "",
        "Redacta un mensaje para cada uno de estos roles:",
    ]
    lineas += [f"- {rol}: {ROLES.get(rol, 'Destinatario general.')}" for rol in sorted(roles)]
    return "\n".join(lineas)