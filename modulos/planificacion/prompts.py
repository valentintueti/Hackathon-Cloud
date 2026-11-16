import json

SISTEMA = (
    "Eres planificador de mantenimiento de ArquiFusion, empresa de maquinaria pesada. "
    "Con los patrones de falla aprendidos del historial y el riesgo de cada maquina, "
    "propones acciones de planificacion concretas, en español, en texto plano sin markdown ni emojis. "
    "Usa solo los datos que se te entregan: no inventes valores, fechas ni fallas. "
    "Presenta las causas como hipotesis a revisar, no como certezas. "
    "Responde unicamente un objeto JSON con dos claves: "
    "\"maquinas\": un objeto cuyas claves son los maquina_id y cuyos valores son objetos con "
    "\"programar\" (que programar y cuando) y \"revisar\" (que sistemas revisar y por que, citando el patron "
    "y en cuantas fallas aparecio); "
    "\"modelos\": un objeto, que puede ir vacio, cuyas claves son modelo_id y cuyos valores son un ajuste sugerido "
    "(por ejemplo, evaluar bajar su intervalo de mantenimiento)."
)

PISTAS_VARIABLE = {
    "temperatura": "sistema de refrigeracion",
    "vibracion": "rodamientos y anclajes",
    "presion": "sistema hidraulico",
    "consumo_combustible": "sistema de inyeccion y filtros",
    "rpm": "motor y transmision",
}


def construir(patrones, maquinas):
    lineas = ["Patrones de falla aprendidos del historial (combinacion: en cuantas fallas aparecio, lift):"]
    if patrones:
        lineas += [f"- {p['combinacion']}: {p['soporte']} fallas, lift {p['lift']}" for p in patrones]
    else:
        lineas.append("- No hay patrones suficientes en el historial todavia.")

    lineas += ["", "Maquinas con riesgo medio o alto hoy:"]
    for m in maquinas:
        datos = {
            k: m.get(k)
            for k in ("maquina_id", "modelo_id", "zona_id", "puntaje", "nivel", "factores")
            if m.get(k) not in (None, "", {}, [])
        }
        datos["patrones_presentes"] = [p["combinacion"] for p in m.get("patrones_presentes", [])]
        lineas.append(json.dumps(datos, ensure_ascii=False, default=str))

    lineas += [
        "",
        "Que sistema revisar segun la variable: " + json.dumps(PISTAS_VARIABLE, ensure_ascii=False),
        "",
        "Para riesgo alto propone una inspeccion en las proximas 24 a 48 horas; para riesgo medio, "
        "la proxima parada programada. Si varias maquinas del mismo modelo estan en riesgo, "
        "sugiere un ajuste para ese modelo.",
    ]
    return "\n".join(lineas)