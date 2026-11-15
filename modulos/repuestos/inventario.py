import math
from collections import defaultdict
from datetime import date, timedelta


def serie_diaria(consumos, dias, hoy):
    inicio = hoy - timedelta(days=dias)
    totales = defaultdict(float)
    for c in consumos:
        dia = date.fromisoformat(str(c["ts"])[:10])
        if inicio <= dia < hoy:
            totales[dia] += float(c.get("cantidad", 1))
    return [totales[inicio + timedelta(days=i)] for i in range(dias)]


def estadisticas(serie):
    n = len(serie)
    media = sum(serie) / n if n else 0.0
    desv = math.sqrt(sum((x - media) ** 2 for x in serie) / n) if n else 0.0
    dias_uso = [i for i, x in enumerate(serie) if x > 0]
    if len(dias_uso) >= 2:
        huecos = [b - a for a, b in zip(dias_uso, dias_uso[1:])]
        dias_entre_usos = sum(huecos) / len(huecos)
    else:
        dias_entre_usos = float(n)
    return {
        "demanda_diaria": media,
        "desviacion": desv,
        "dias_con_uso": len(dias_uso),
        "dias_entre_usos": dias_entre_usos,
    }


def clasificar(est, cv_max, dias_entre_usos_max):
    if est["demanda_diaria"] == 0:
        return "sin_movimiento"
    cv = est["desviacion"] / est["demanda_diaria"]
    if cv > cv_max or est["dias_entre_usos"] > dias_entre_usos_max:
        return "irregular"
    return "regular"


def _entero(valor):
    return math.ceil(round(valor, 6))


def calcular(est, clasificacion, dias_reposicion, z, dias_objetivo, minimo_irregular):
    demanda = est["demanda_diaria"]
    if clasificacion == "regular":
        seguridad = z * est["desviacion"] * math.sqrt(dias_reposicion)
        punto = demanda * dias_reposicion + seguridad
        objetivo = punto + demanda * dias_objetivo
    elif clasificacion == "irregular":
        seguridad = 0
        punto = minimo_irregular
        objetivo = minimo_irregular
    else:
        seguridad = punto = objetivo = 0
    return {
        "stock_seguridad": _entero(seguridad),
        "punto_reorden": _entero(punto),
        "stock_objetivo": _entero(objetivo),
    }


def ranking(filas, top=10):
    total = defaultdict(float)
    for f in filas:
        total[f["componente_id"]] += f["demanda_diaria"]
    ordenado = sorted(total.items(), key=lambda par: par[1], reverse=True)
    return [{"componente_id": c, "demanda_diaria": round(v, 3)} for c, v in ordenado[:top] if v > 0]


def mensaje_stock_bajo(piezas):
    por_zona = defaultdict(list)
    for p in piezas:
        por_zona[p["zona_id"]].append(p)

    lineas = [f"Hay {len(piezas)} piezas por debajo de su punto de reorden.", ""]
    for zona in sorted(por_zona):
        lineas.append(f"Zona {zona}:")
        for p in sorted(por_zona[zona], key=lambda x: x["componente_id"]):
            pedir = max(p["stock_objetivo"] - p["stock_actual"], 0)
            nombre = p.get("nombre") or p["componente_id"]
            lineas.append(
                f"  - {nombre}: stock {p['stock_actual']}, punto de reorden {p['punto_reorden']}, "
                f"pedir {pedir} (hasta {p['stock_objetivo']})"
            )
        lineas.append("")
    return "\n".join(lineas).strip()