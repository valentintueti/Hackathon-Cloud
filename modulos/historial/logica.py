from collections import Counter
from datetime import datetime, timedelta

ESTADOS = ["pendiente", "asignada", "en_atencion", "hecha"]


TRANSICIONES = {"pendiente": "asignada", "asignada": "en_atencion", "en_atencion": "hecha"}

CAMPO_TS = {"asignada": "ts_asignada", "en_atencion": "ts_inicio_atencion", "hecha": "ts_completada"}

SEVERIDADES = ["baja", "media", "alta", "critica"]


def _fecha(valor):
    return datetime.fromisoformat(str(valor)) if valor else None


def _minutos(desde, hasta):
    if not desde or not hasta:
        return None
    return round((hasta - desde).total_seconds() / 60, 1)


def transicion_valida(estado_actual, estado_nuevo):
    return TRANSICIONES.get(estado_actual) == estado_nuevo


def tiempos(orden):
    creada = _fecha(orden.get("ts_creada"))
    inicio = _fecha(orden.get("ts_inicio_atencion"))
    fin = _fecha(orden.get("ts_completada"))
    return {
        "tiempo_respuesta_min": _minutos(creada, inicio),
        "tiempo_reparacion_min": _minutos(inicio, fin),
        "tiempo_detenido_min": _minutos(creada, fin),
    }


def buscar_reincidencia(nueva, anteriores, dias):
    creada = _fecha(nueva["ts_creada"])
    for previa in sorted(anteriores, key=lambda o: o.get("ts_completada") or "", reverse=True):
        fin = _fecha(previa.get("ts_completada"))
        if (
            previa.get("estado") == "hecha"
            and fin
            and timedelta(0) <= creada - fin <= timedelta(days=dias)
            and previa.get("categoria") == nueva.get("categoria")
        ):
            return previa["orden_id"]
    return None


def resumen(ordenes):
    correctivas = [o for o in ordenes if o.get("tipo", "correctivo") == "correctivo"]
    cerradas = [o for o in correctivas if o.get("estado") == "hecha"]
    detenidos = [tiempos(o)["tiempo_detenido_min"] for o in cerradas]
    detenidos = [d for d in detenidos if d is not None]

    componentes = Counter()
    for o in ordenes:
        for c in o.get("componentes_reemplazados", []):
            componentes[c.get("componente")] += int(c.get("cantidad", 1))

    return {
        "incidentes_correctivos": len(correctivas),
        "mantenimientos_preventivos": len(ordenes) - len(correctivas),
        "abiertos": sum(1 for o in ordenes if o.get("estado") != "hecha"),
        "tiempo_detenido_total_min": round(sum(detenidos), 1),
        "mttr_min": round(sum(detenidos) / len(detenidos), 1) if detenidos else None,
        "reincidencias": sum(1 for o in correctivas if o.get("reincidente_de")),
        "componentes_mas_reemplazados": componentes.most_common(5),
    }