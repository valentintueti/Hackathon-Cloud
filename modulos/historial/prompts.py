import json

SISTEMA = (
    "Eres analista de confiabilidad de maquinaria pesada en ArquiFusion. "
    "Al cerrarse un incidente, resumes el historial de la maquina para el jefe de mantenimiento, "
    "en español simple, sin markdown ni emojis. "
    "Busca patrones: fallas que se repiten, misma categoria o componente, reincidencias y tiempo detenido. "
    "Usa solo los datos entregados; no inventes fechas, valores ni componentes. "
    "Responde solo un JSON con las claves: "
    "\"resumen\" (maximo 5 oraciones) y "
    "\"acciones\" (lista de 1 a 3 acciones concretas para que la falla no se repita)."
)

CAMPOS = (
    "ts_creada", "tipo", "categoria", "severidad", "descripcion", "causa_raiz",
    "trabajo_realizado", "componentes_reemplazados", "observaciones",
    "tiempo_detenido_min", "tiempo_reparacion_min", "reincidente_de",
)


def _compacta(orden):
    datos = {k: orden.get(k) for k in CAMPOS if orden.get(k) not in (None, "", [], {})}
    if "ts_creada" in datos:
        datos["ts_creada"] = str(datos["ts_creada"])[:10]
    return datos


def construir(orden, previas, resumen):
    return "\n".join([
        f"Maquina: {orden.get('maquina_id')}",
        "Incidente que se acaba de cerrar:",
        json.dumps(_compacta(orden), ensure_ascii=False, default=str),
        "",
        "Incidentes y mantenimientos anteriores (mas reciente primero):",
        json.dumps([_compacta(o) for o in previas], ensure_ascii=False, default=str) if previas else "Ninguno.",
        "",
        "Metricas calculadas del historial completo:",
        json.dumps(resumen, ensure_ascii=False, default=str),
    ])


def respaldo(resumen):
    partes = [f"{resumen.get('incidentes_correctivos', 0)} incidentes correctivos registrados"]
    if resumen.get("reincidencias"):
        partes.append(f"{resumen['reincidencias']} reincidencias")
    partes.append(f"tiempo detenido total {resumen.get('tiempo_detenido_total_min', 0)} min")
    if resumen.get("mttr_min") is not None:
        partes.append(f"tiempo medio de reparacion {resumen['mttr_min']} min")
    componentes = [(c, n) for c, n in resumen.get("componentes_mas_reemplazados") or [] if c]
    if componentes:
        partes.append("componentes mas cambiados: " + ", ".join(f"{c} ({n})" for c, n in componentes))
    return "Historial de la maquina: " + "; ".join(partes) + "."