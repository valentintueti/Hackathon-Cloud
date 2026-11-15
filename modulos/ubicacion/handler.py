import math
from datetime import datetime, timezone

from comun.config import env
from comun.ddb import tabla, a_json

maquinas = tabla("TABLA_MAQUINA")
MINUTOS_SIN_SENAL = int(env("MINUTOS_SIN_SENAL", "15"))

def _http(codigo, cuerpo):
    return {
        "statusCode": codigo,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": a_json(cuerpo),
    }

def _escanear_todo(tabla_ddb):
    items = []
    respuesta = tabla_ddb.scan()
    items.extend(respuesta.get("Items", []))
    while "LastEvaluatedKey" in respuesta:
        respuesta = tabla_ddb.scan(ExclusiveStartKey=respuesta["LastEvaluatedKey"])
        items.extend(respuesta.get("Items", []))
    return items

def listar(event, context):
    params = event.get("queryStringParameters") or {}
    zona = params.get("zona")
    estado = params.get("estado")

    todas = _escanear_todo(maquinas)

    resultado = []
    for m in todas:
        m["estado"] = _estado_efectivo(m)
        if (zona is not None and m.get("zona_id")!=zona):
            continue
        if (estado is not None and m.get("estado")!=estado):
            continue
        resultado.append(m)
    return _http(200, {"cantidad": len(resultado), "maquinas": resultado})

def _estado_efectivo(m):
    ts = m.get("ultima_lectura_ts")
    if not ts:
        return "sin_senal"
    ultima = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    if ultima.tzinfo is None:
        ultima = ultima.replace(tzinfo=timezone.utc)
    minutos = (datetime.now(timezone.utc) - ultima).total_seconds() / 60
    if minutos > MINUTOS_SIN_SENAL:
        return "sin_senal"
    return m.get("estado")

def resumen(event, context):
    todas = _escanear_todo(maquinas)
    por_estado = {}
    por_zona = {}
    for m in todas:
        est = _estado_efectivo(m)
        zona = m.get("zona_id", "sin_zona")

        por_estado[est] = por_estado.get(est, 0) + 1

        if zona not in por_zona:
            por_zona[zona] = {}
        por_zona[zona][est] = por_zona[zona].get(est, 0) + 1

    return _http(200, {
        "total_maquinas": len(todas),
        "por_estado": por_estado,
        "por_zona": por_zona,
    })

def _haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def cercanas(event, context):
    params = event.get("queryStringParameters") or {}
    try:
        lat = float(params["lat"])
        lon = float(params["lon"])
        radio = float(params.get("radio_km", 5))
    except (KeyError, ValueError):
        return _http(400, {"error": "Debes enviar lat y lon numericos"})

    resultado = []
    for m in _escanear_todo(maquinas):
        if m.get("lat") is None or m.get("lon") is None:
            continue
        d = _haversine_km(lat, lon, float(m["lat"]), float(m["lon"]))
        if d <= radio:
            m["distancia_km"] = round(d, 2)
            m["estado"] = _estado_efectivo(m)
            resultado.append(m)

    resultado.sort(key=lambda x: x["distancia_km"])
    return _http(200, {"cantidad": len(resultado), "maquinas": resultado})