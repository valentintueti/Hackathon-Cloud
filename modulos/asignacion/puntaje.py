import math

PESO_ESPECIALIDAD = 40
PESO_DISTANCIA = 25
PESO_TIEMPO = 15
PESO_CARGA = 20

DISTANCIA_MAX_KM = 50
TIEMPO_MAX_MIN = 180
CARGA_MAX = 3


def haversine_km(lat1, lon1, lat2, lon2):
    radio = 6371
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * radio * math.asin(math.sqrt(a))


def _limitar(valor):
    return max(0.0, min(1.0, valor))


def _numero(texto):
    return f"{texto:.1f}".replace(".", ",")


def puntuar(tecnico, maquina, categoria, velocidad_kmh, reparacion_min):
    especialidades = [str(e).lower() for e in tecnico.get("especialidades", [])]
    coincide = bool(categoria) and str(categoria).lower() in especialidades
    puntos = PESO_ESPECIALIDAD if coincide else PESO_ESPECIALIDAD * 0.25

    distancia = None
    if None not in (tecnico.get("lat"), tecnico.get("lon"), maquina.get("lat"), maquina.get("lon")):
        distancia = haversine_km(float(tecnico["lat"]), float(tecnico["lon"]),
                                 float(maquina["lat"]), float(maquina["lon"]))

    if distancia is not None:
        viaje_min = distancia / velocidad_kmh * 60
        tiempo_min = viaje_min + reparacion_min
        puntos += PESO_DISTANCIA * _limitar(1 - distancia / DISTANCIA_MAX_KM)
        puntos += PESO_TIEMPO * _limitar(1 - tiempo_min / TIEMPO_MAX_MIN)
    else:
        viaje_min = tiempo_min = None

    activas = int(tecnico.get("asignaciones_activas", 0) or 0)
    puntos += PESO_CARGA * _limitar(1 - activas / CARGA_MAX)

    partes = [f"especialidad {categoria}" if coincide else f"sin especialidad en {categoria or 'la categoria'}"]
    if distancia is not None:
        partes.append(f"a {_numero(distancia)} km (~{round(viaje_min)} min)")
    else:
        partes.append("sin ubicacion conocida")
    if activas == 0:
        partes.append("sin otras asignaciones")
    else:
        partes.append(f"{activas} asignacion(es) activa(s)")

    return {
        "tecnico_id": tecnico["tecnico_id"],
        "nombre": tecnico.get("nombre"),
        "puntaje": round(puntos, 1),
        "distancia_km": round(distancia, 2) if distancia is not None else None,
        "tiempo_estimado_min": round(tiempo_min) if tiempo_min is not None else None,
        "justificacion": ", ".join(partes),
    }


def ranking(tecnicos, maquina, categoria, rechazados, velocidad_kmh, reparacion_min, maximo=5):
    candidatos = [
        puntuar(t, maquina, categoria, velocidad_kmh, reparacion_min)
        for t in tecnicos
        if t.get("estado") == "disponible" and t["tecnico_id"] not in rechazados
    ]
    candidatos.sort(key=lambda c: c["puntaje"], reverse=True)
    return candidatos[:maximo]