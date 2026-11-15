import json

SISTEMA = (
    "Eres analista de operaciones de una flota de maquinaria pesada en ArquiFusion. "
    "Recibes maquinas con hallazgos de productividad de la ultima semana y acciones ya calculadas por reglas. "
    "Redactas para el supervisor de flota, en español simple, sin markdown ni emojis. "
    "Usa solo los datos entregados; no inventes maquinas, zonas ni valores, y no contradigas las acciones calculadas. "
    "Responde solo un JSON con las claves: "
    "\"resumen\" (maximo 5 oraciones con la situacion general de la flota) y "
    "\"recomendaciones\" (lista de 1 a 5 acciones priorizadas, cada una en una frase)."
)

HALLAZGOS = {
    "baja_utilizacion": "trabajo menos horas de las que permite su turno",
    "jornada_excesiva": "varios dias trabajo mas horas que la jornada maxima",
    "baja_productividad_alto_costo": "mueve menos carga que las de su modelo y cada hora le cuesta mas",
}

CAMPOS = (
    "maquina_id", "modelo_id", "zona_id", "hallazgos", "utilizacion_pct", "horas_promedio",
    "dias_excesivos", "ralenti_pct", "costo_total", "carga_promedio_t", "costo_hora_por_t",
    "carga_mediana_modelo", "costo_mediana_modelo",
)


def construir(maquinas, acciones):
    lineas = ["Significado de cada hallazgo:"]
    lineas += [f"- {k}: {v}" for k, v in HALLAZGOS.items()]
    lineas += ["", "Maquinas con hallazgos en los ultimos dias:"]
    for m in maquinas:
        datos = {k: m.get(k) for k in CAMPOS if m.get(k) not in (None, "", [])}
        lineas.append(json.dumps(datos, ensure_ascii=False, default=str))
    lineas += ["", "Acciones calculadas por reglas:"]
    lineas += [f"- {a['detalle']}" for a in acciones] or ["- Ninguna"]
    return "\n".join(lineas)


def respaldo(maquinas, acciones):
    conteo = {h: sum(1 for m in maquinas if h in m.get("hallazgos", [])) for h in HALLAZGOS}
    partes = [f"{n} con {h.replace('_', ' ')}" for h, n in conteo.items() if n]
    return (
        f"En los ultimos dias {len(maquinas)} maquinas tuvieron hallazgos de productividad: "
        + ", ".join(partes)
        + f". Se proponen {len(acciones)} acciones."
    )