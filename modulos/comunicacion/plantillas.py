def generar_mensajes(tipo_evento, severidad, datos, roles):
    mensajes = {}
    for rol in roles:
        if tipo_evento == "alerta" and datos.get("tipo") == "masiva":
            mensajes[rol] = _alerta_masiva(severidad, datos)
            continue
        constructor = _CONSTRUCTORES.get((tipo_evento, rol), _mensaje_generico)
        mensajes[rol] = constructor(severidad, datos)
    return mensajes


def _mensaje_generico(severidad, datos):
    return f"Evento {severidad} en maquina {datos.get('maquina_id', datos.get('maquinaId', 'desconocida'))}"


def _alerta_masiva(severidad, datos):
    maquinas = ", ".join(datos.get("maquinas_afectadas", [])) or "varias maquinas"
    return (
        f"Incidente masivo {severidad} en la zona {datos.get('zona_id', 'desconocida')}: "
        f"{len(datos.get('maquinas_afectadas', []))} maquinas afectadas ({maquinas}). "
        f"{datos.get('descripcion', '')}"
    ).strip()


def _alerta_operador(severidad, datos):
    return (
        f"Atencion: tu maquina {datos.get('maquina_id')} presenta una alerta de severidad {severidad}. "
        "Sigue el protocolo de seguridad correspondiente."
    )


def _alerta_tecnico(severidad, datos):
    variables = ", ".join(datos.get("variables_afectadas", [])) or "varias variables"
    return (
        f"Alerta {severidad} en maquina {datos.get('maquina_id')}. "
        f"Variables afectadas: {variables} (puntaje {datos.get('puntaje')}/100). "
        "Revisa la maquina y registra tu intervencion en el sistema."
    )


def _alerta_jefe_mantenimiento(severidad, datos):
    variables = ", ".join(datos.get("variables_afectadas", [])) or "varias variables"
    return (
        f"Alerta {severidad.upper()} en maquina {datos.get('maquina_id')} "
        f"(zona {datos.get('zona_id', 'desconocida')}). "
        f"Variables afectadas: {variables} (puntaje {datos.get('puntaje')}/100). "
        "Requiere tu confirmacion."
    )


def _orden_creada_tecnico(prioridad, datos):
    return f"Nueva orden {prioridad} para maquina {datos.get('maquina_id')} (orden {datos.get('orden_id')})."


def _orden_creada_jefe_mantenimiento(prioridad, datos):
    return (
        f"Se genero una orden de prioridad {prioridad} para la maquina {datos.get('maquina_id')} "
        f"(orden {datos.get('orden_id')}). Confirma que fue asignada."
    )


def _orden_cerrada_jefe_mantenimiento(severidad, datos):
    return f"La orden {datos.get('orden_id')} de la maquina {datos.get('maquina_id')} fue completada."


def _orden_cerrada_supervisor(severidad, datos):
    return f"Orden {datos.get('orden_id')} cerrada en maquina {datos.get('maquina_id')}."


def _orden_cerrada_gerencia(severidad, datos):
    return f"Resumen: orden {datos.get('orden_id')} cerrada en maquina {datos.get('maquina_id')}."


def _escalada_supervisor(severidad, datos):
    maquina_id = datos.get("maquinaId", datos.get("maquina_id", "desconocida"))
    return f"ESCALADO: jefe de mantenimiento no confirmo a tiempo la alerta {severidad} en maquina {maquina_id}."


def _escalada_gerencia(severidad, datos):
    maquina_id = datos.get("maquinaId", datos.get("maquina_id", "desconocida"))
    return f"ESCALADO: supervisor no confirmo a tiempo la alerta {severidad} en maquina {maquina_id}."


_CONSTRUCTORES = {
    ("alerta", "operador"): _alerta_operador,
    ("alerta", "tecnico"): _alerta_tecnico,
    ("alerta", "jefe-mantenimiento"): _alerta_jefe_mantenimiento,
    ("orden_creada", "tecnico"): _orden_creada_tecnico,
    ("orden_creada", "jefe-mantenimiento"): _orden_creada_jefe_mantenimiento,
    ("orden_cerrada", "jefe-mantenimiento"): _orden_cerrada_jefe_mantenimiento,
    ("orden_cerrada", "supervisor"): _orden_cerrada_supervisor,
    ("orden_cerrada", "gerencia"): _orden_cerrada_gerencia,
    ("escalada", "supervisor"): _escalada_supervisor,
    ("escalada", "gerencia"): _escalada_gerencia,
}