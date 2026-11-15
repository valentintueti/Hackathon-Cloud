from boto3.dynamodb.conditions import Key

from comun.ddb import a_json, tabla

alertas = tabla("TABLA_ALERTA")
ordenes = tabla("TABLA_ORDEN_TRABAJO")

LIMITE_DEFECTO = 100
LIMITE_MAXIMO = 500


def listar_alertas(event, context):
    params = event.get("queryStringParameters") or {}
    limite = _limite(params)
    if limite is None:
        return _http(400, {"error": f"limite debe ser un numero entre 1 y {LIMITE_MAXIMO}"})

    if params.get("maquina"):
        items = _consultar(alertas, "por_maquina", Key("maquina_id").eq(params["maquina"]), params.get("desde"))
    elif params.get("zona"):
        items = _consultar(alertas, "por_zona", Key("zona_id").eq(params["zona"]), params.get("desde"))
    else:
        items = _escanear(alertas)
        if params.get("desde"):
            items = [a for a in items if str(a.get("ts", "")) >= params["desde"]]

    for campo in ("origen", "severidad", "estado", "zona_id"):
        valor = params.get("zona" if campo == "zona_id" else campo)
        if valor:
            items = [a for a in items if a.get(campo) == valor]

    items.sort(key=lambda a: str(a.get("ts", "")), reverse=True)
    return _http(200, {"cantidad": min(len(items), limite), "total": len(items), "alertas": items[:limite]})


def listar_ordenes(event, context):
    params = event.get("queryStringParameters") or {}
    limite = _limite(params)
    if limite is None:
        return _http(400, {"error": f"limite debe ser un numero entre 1 y {LIMITE_MAXIMO}"})

    if params.get("maquina"):
        items = _consultar(ordenes, "por_maquina", Key("maquina_id").eq(params["maquina"]), None, campo_ts="ts_creada")
    else:
        items = _escanear(ordenes)

    if params.get("tipo"):
        items = [o for o in items if o.get("tipo", "correctivo") == params["tipo"]]
    estado = params.get("estado")
    if estado == "abiertas":
        items = [o for o in items if o.get("estado") != "hecha"]
    elif estado:
        items = [o for o in items if o.get("estado") == estado]

    for o in items:
        o.pop("token_pendiente", None)
        o.pop("etapa_esperada", None)
    items.sort(key=lambda o: str(o.get("ts_creada", "")), reverse=True)
    return _http(200, {"cantidad": min(len(items), limite), "total": len(items), "ordenes": items[:limite]})


def _consultar(tabla_ddb, indice, condicion, desde, campo_ts="ts"):
    if desde:
        condicion = condicion & Key(campo_ts).gte(desde)
    parametros = {"IndexName": indice, "KeyConditionExpression": condicion, "ScanIndexForward": False}
    items = []
    while True:
        respuesta = tabla_ddb.query(**parametros)
        items.extend(respuesta.get("Items", []))
        if "LastEvaluatedKey" not in respuesta:
            return items
        parametros["ExclusiveStartKey"] = respuesta["LastEvaluatedKey"]


def _escanear(tabla_ddb):
    items = []
    respuesta = tabla_ddb.scan()
    items.extend(respuesta.get("Items", []))
    while "LastEvaluatedKey" in respuesta:
        respuesta = tabla_ddb.scan(ExclusiveStartKey=respuesta["LastEvaluatedKey"])
        items.extend(respuesta.get("Items", []))
    return items


def _limite(params):
    try:
        limite = int(params.get("limite", LIMITE_DEFECTO))
    except (TypeError, ValueError):
        return None
    return limite if 1 <= limite <= LIMITE_MAXIMO else None


def _http(codigo, cuerpo):
    return {
        "statusCode": codigo,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": a_json(cuerpo),
    }
