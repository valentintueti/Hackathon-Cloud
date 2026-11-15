import json
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import boto3
from boto3.dynamodb.conditions import Key

import inventario
from comun.config import env
from comun.ddb import a_dynamo, a_json, actualizar, tabla

sns = boto3.client("sns")
maquinas = tabla("TABLA_MAQUINA")
componentes = tabla("TABLA_COMPONENTE")
inventarios = tabla("TABLA_INVENTARIO")
consumos = tabla("TABLA_CONSUMO")

def registrar_consumo(event, context):
    if "detail-type" in event:
        return _desde_orden(event["detail"])
    return _desde_http(event)

def _desde_http(event):
    try:
        datos = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _http(400, {"error": "El cuerpo no es JSON valido"})

    piezas = datos if isinstance(datos, list) else [datos]
    registrados, errores = [], []
    for i, p in enumerate(piezas):
        try:
            cantidad = int(p.get("cantidad", 0))
        except (TypeError, ValueError):
            cantidad = 0
        if not p.get("componente_id") or cantidad <= 0:
            errores.append({"indice": i, "error": "faltan componente_id o una cantidad mayor a 0"})
            continue
        zona_id = p.get("zona_id") or _zona_de(p.get("maquina_id"))
        if not zona_id:
            errores.append({"indice": i, "error": "falta zona_id (o un maquina_id con zona)"})
            continue
        registrados.append(_registrar(p["componente_id"], cantidad, zona_id,
                                      p.get("maquina_id"), p.get("orden_id"), "manual"))

    codigo = 201 if registrados else 400
    return _http(codigo, {"registrados": registrados, "errores": errores})

def _desde_orden(orden):
    orden_id = orden.get("orden_id")
    zona_id = _zona_de(orden.get("maquina_id"))
    if not zona_id:
        print(f"Orden {orden_id}: no se encontro la zona de la maquina {orden.get('maquina_id')}")
        return {"registrados": 0}

    por_componente = defaultdict(int)
    for c in orden.get("componentes_reemplazados") or []:
        if c.get("componente"):
            por_componente[str(c["componente"])] += int(c.get("cantidad", 1))

    registrados = 0
    for componente_id, cantidad in por_componente.items():
        hecho = _registrar(componente_id, cantidad, zona_id, orden.get("maquina_id"), orden_id,
                           "orden", consumo_id=f"{orden_id}#{componente_id}")
        if hecho:
            registrados += 1
    print(f"Orden {orden_id}: {registrados} repuestos registrados en {zona_id}")
    return {"registrados": registrados}

def _registrar(componente_id, cantidad, zona_id, maquina_id, orden_id, origen, consumo_id=None):
    consumo = {
        "consumo_id": consumo_id or str(uuid.uuid4()),
        "componente_id": str(componente_id),
        "zona_id": zona_id,
        "maquina_id": maquina_id,
        "orden_id": orden_id,
        "cantidad": cantidad,
        "ts": _ahora(),
        "origen": origen,
    }
    try:
        consumos.put_item(
            Item=a_dynamo({k: v for k, v in consumo.items() if v is not None}),
            ConditionExpression="attribute_not_exists(consumo_id)",
        )
    except consumos.meta.client.exceptions.ConditionalCheckFailedException:
        print(f"El consumo {consumo['consumo_id']} ya estaba registrado; no se descuenta otra vez")
        return None

    inventarios.update_item(
        Key={"zona_id": zona_id, "componente_id": str(componente_id)},
        UpdateExpression="SET stock_actual = if_not_exists(stock_actual, :cero) - :cantidad",
        ExpressionAttributeValues={":cero": 0, ":cantidad": cantidad},
    )
    return consumo

def _zona_de(maquina_id):
    if not maquina_id:
        return None
    return maquinas.get_item(Key={"maquina_id": str(maquina_id)}).get("Item", {}).get("zona_id")

def calcular_reposicion(event, context):
    dias = int(env("DIAS_VENTANA", "90"))
    ahora = datetime.now(timezone.utc)
    desde = (ahora - timedelta(days=dias + 1)).isoformat()

    catalogo = {c["componente_id"]: c for c in _escanear_todo(componentes)}
    stock = {(i["zona_id"], i["componente_id"]): i for i in _escanear_todo(inventarios)}

    consumos_por_par = defaultdict(list)
    for componente_id in set(catalogo) | {c for _, c in stock}:
        lista = _consultar_todo(
            consumos,
            IndexName="por_componente",
            KeyConditionExpression=Key("componente_id").eq(componente_id) & Key("ts").gte(desde),
        )
        for c in lista:
            consumos_por_par[(c["zona_id"], componente_id)].append(c)

    filas, bajo = [], []
    for zona_id, componente_id in sorted(set(stock) | set(consumos_por_par)):
        comp = catalogo.get(componente_id, {})
        dias_reposicion = float(comp.get("dias_reposicion") or env("DIAS_REPOSICION_DEFECTO", "7"))

        serie = inventario.serie_diaria(consumos_por_par.get((zona_id, componente_id), []), dias, ahora.date())
        est = inventario.estadisticas(serie)
        clase = inventario.clasificar(est, float(env("CV_IRREGULAR", "1")), float(env("DIAS_ENTRE_USOS_IRREGULAR", "30")))
        calculo = inventario.calcular(
            est, clase, dias_reposicion,
            float(env("Z_SERVICIO", "1.65")),
            float(env("DIAS_STOCK_OBJETIVO", "30")),
            int(env("MINIMO_IRREGULAR", "1")),
        )
        stock_actual = int(stock.get((zona_id, componente_id), {}).get("stock_actual", 0))

        actualizar(inventarios, clave={"zona_id": zona_id, "componente_id": componente_id}, campos={
            **calculo,
            "clasificacion": clase,
            "demanda_diaria": round(est["demanda_diaria"], 4),
            "desviacion": round(est["desviacion"], 4),
            "fecha_calculo": ahora.isoformat(),
        })

        fila = {
            "zona_id": zona_id,
            "componente_id": componente_id,
            "nombre": comp.get("nombre"),
            "stock_actual": stock_actual,
            "clasificacion": clase,
            "demanda_diaria": round(est["demanda_diaria"], 4),
            **calculo,
        }
        filas.append(fila)
        if stock_actual < calculo["punto_reorden"]:
            bajo.append(fila)

    sin_movimiento = [f"{f['zona_id']}/{f['componente_id']}" for f in filas
                      if f["clasificacion"] == "sin_movimiento" and f["stock_actual"] > 0]
    print(f"Pares zona/componente: {len(filas)} | bajo punto de reorden: {len(bajo)} | sin movimiento con stock: {len(sin_movimiento)}")
    return _plano({
        "cantidad": len(bajo),
        "piezas": bajo,
        "ranking": inventario.ranking(filas),
        "sin_movimiento": sin_movimiento,
    })

def avisar_stock_bajo(event, context):
    piezas = event["piezas"]
    zonas = sorted({p["zona_id"] for p in piezas})
    sns.publish(
        TopicArn=env("SNS_TOPIC_ARN"),
        Subject=f"Stock bajo: {len(piezas)} piezas por reponer en {len(zonas)} zonas"[:100],
        Message=inventario.mensaje_stock_bajo(piezas),
    )
    print(f"Aviso enviado: {len(piezas)} piezas en {zonas}")
    return {"notificadas": len(piezas), "zonas": zonas}

def listar_inventario(event, context):
    params = event.get("queryStringParameters") or {}
    if params.get("zona"):
        filas = _consultar_todo(inventarios, KeyConditionExpression=Key("zona_id").eq(params["zona"]))
    else:
        filas = _escanear_todo(inventarios)
    catalogo = {c["componente_id"]: c for c in _escanear_todo(componentes)}
    for f in filas:
        f["nombre"] = catalogo.get(f["componente_id"], {}).get("nombre")
        punto = f.get("punto_reorden")
        f["bajo_reorden"] = punto is not None and f.get("stock_actual", 0) < punto
    if params.get("bajo_reorden") == "true":
        filas = [f for f in filas if f["bajo_reorden"]]
    filas.sort(key=lambda f: (f["zona_id"], f["componente_id"]))
    return _http(200, {"cantidad": len(filas), "inventario": filas})

def ingresar_stock(event, context):
    try:
        datos = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _http(400, {"error": "El cuerpo no es JSON valido"})

    piezas = datos if isinstance(datos, list) else [datos]
    guardados, errores = [], []
    for i, p in enumerate(piezas):
        if not p.get("zona_id") or not p.get("componente_id"):
            errores.append({"indice": i, "error": "faltan zona_id o componente_id"})
            continue
        clave = {"zona_id": str(p["zona_id"]), "componente_id": str(p["componente_id"])}
        try:
            if p.get("stock_actual") is not None:
                valor = int(p["stock_actual"])
                expresion = "SET stock_actual = :valor"
            else:
                valor = int(p.get("cantidad", 0))
                expresion = "SET stock_actual = if_not_exists(stock_actual, :cero) + :valor"
        except (TypeError, ValueError):
            valor = -1
        if valor < 0 or (p.get("stock_actual") is None and valor == 0):
            errores.append({"indice": i, "error": "envia cantidad (ingreso mayor a 0) o stock_actual (conteo, 0 o mas)"})
            continue
        valores = {":valor": valor, ":ahora": _ahora()}
        if "if_not_exists" in expresion:
            valores[":cero"] = 0
        respuesta = inventarios.update_item(
            Key=clave,
            UpdateExpression=expresion + ", ultimo_ingreso_ts = :ahora",
            ExpressionAttributeValues=valores,
            ReturnValues="ALL_NEW",
        )
        guardados.append(respuesta["Attributes"])

    return _http(200 if guardados else 400, {"guardados": guardados, "errores": errores})

def listar_componentes(event, context):
    lista = sorted(_escanear_todo(componentes), key=lambda c: c["componente_id"])
    return _http(200, {"cantidad": len(lista), "componentes": lista})

def registrar_componente(event, context):
    try:
        datos = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _http(400, {"error": "El cuerpo no es JSON valido"})

    piezas = datos if isinstance(datos, list) else [datos]
    guardados, errores = [], []
    for i, p in enumerate(piezas):
        componente_id = str(p.get("componente_id") or "").strip()
        if not componente_id or not p.get("nombre"):
            errores.append({"indice": i, "error": "faltan componente_id o nombre"})
            continue
        item = {
            "componente_id": componente_id,
            "nombre": p["nombre"],
            "categoria": p.get("categoria"),
            "dias_reposicion": p.get("dias_reposicion"),
            "costo": p.get("costo"),
        }
        componentes.put_item(Item=a_dynamo({k: v for k, v in item.items() if v is not None}))
        guardados.append(item)

    return _http(201 if guardados else 400, {"guardados": guardados, "errores": errores})

def _escanear_todo(tabla_ddb):
    items = []
    respuesta = tabla_ddb.scan()
    items.extend(respuesta.get("Items", []))
    while "LastEvaluatedKey" in respuesta:
        respuesta = tabla_ddb.scan(ExclusiveStartKey=respuesta["LastEvaluatedKey"])
        items.extend(respuesta.get("Items", []))
    return items


def _consultar_todo(tabla_ddb, **parametros):
    items = []
    while True:
        respuesta = tabla_ddb.query(**parametros)
        items.extend(respuesta.get("Items", []))
        if "LastEvaluatedKey" not in respuesta:
            return items
        parametros["ExclusiveStartKey"] = respuesta["LastEvaluatedKey"]


def _ahora():
    return datetime.now(timezone.utc).isoformat()


def _plano(valor):
    return json.loads(a_json(valor))


def _http(codigo, cuerpo):
    return {
        "statusCode": codigo,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": a_json(cuerpo),
    }