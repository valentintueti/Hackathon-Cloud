import argparse
import json
import random
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import boto3

LIMA = timezone(timedelta(hours=-5))
PASO = timedelta(minutes=30)
ESPACIO_IDS = uuid.UUID("6f1c2a52-1d0b-4c5e-9a57-6a1f3b2c9d10")

ZONAS = [
    {"zona_id": "Z-NORTE", "nombre": "Tajo Norte", "lat": -11.020, "lon": -76.250, "tipo_terreno": "roca dura", "clima_actual": "frio seco"},
    {"zona_id": "Z-CENTRO", "nombre": "Planta Centro", "lat": -11.050, "lon": -76.230, "tipo_terreno": "mixto", "clima_actual": "templado"},
    {"zona_id": "Z-SUR", "nombre": "Botadero Sur", "lat": -11.085, "lon": -76.210, "tipo_terreno": "arcilloso humedo", "clima_actual": "lluvioso"},
]
ZONA_POR_ID = {z["zona_id"]: z for z in ZONAS}

UMBRALES = {
    "temperatura": {"normal": 90, "limite": 110},
    "vibracion": {"normal": 4, "limite": 8},
    "presion": {"normal": 30, "limite": 20},
    "consumo_combustible": {"normal": 30, "limite": 45},
}

MODELOS = {
    "CAMION-T40": {"nombre": "Camion minero T40", "capacidad": 35, "intervalo": 250, "consumo": 26, "carga": 30, "velocidad": 22, "rpm": 1750},
    "EXCAVADORA-E20": {"nombre": "Excavadora E20", "capacidad": 4, "intervalo": 250, "consumo": 22, "carga": 3.2, "velocidad": 1.5, "rpm": 1650},
    "CARGADOR-L50": {"nombre": "Cargador frontal L50", "capacidad": 6, "intervalo": 250, "consumo": 18, "carga": 5, "velocidad": 8, "rpm": 1600},
}

MAQUINAS = [
    {"id": "CAM-01", "modelo": "CAMION-T40", "zona": "Z-NORTE"},
    {"id": "CAM-02", "modelo": "CAMION-T40", "zona": "Z-NORTE"},
    {"id": "CAM-03", "modelo": "CAMION-T40", "zona": "Z-CENTRO"},
    {"id": "CAM-04", "modelo": "CAMION-T40", "zona": "Z-SUR", "carga": 0.65, "consumo": 1.35},
    {"id": "EXC-01", "modelo": "EXCAVADORA-E20", "zona": "Z-NORTE"},
    {"id": "EXC-02", "modelo": "EXCAVADORA-E20", "zona": "Z-CENTRO"},
    {"id": "EXC-03", "modelo": "EXCAVADORA-E20", "zona": "Z-CENTRO"},
    {"id": "EXC-04", "modelo": "EXCAVADORA-E20", "zona": "Z-SUR"},
    {"id": "CAR-01", "modelo": "CARGADOR-L50", "zona": "Z-CENTRO", "inicio": 5, "horas": 14},
    {"id": "CAR-02", "modelo": "CARGADOR-L50", "zona": "Z-SUR"},
    {"id": "CAR-03", "modelo": "CARGADOR-L50", "zona": "Z-NORTE", "horas": 3},
    {"id": "CAR-04", "modelo": "CARGADOR-L50", "zona": "Z-SUR"},
]
MAQUINA_POR_ID = {m["id"]: m for m in MAQUINAS}

MANTENIMIENTO_DIAS = {"EXC-01": 29, "CAR-02": 28}

FALLAS = [
    ("CAM-01", 24, "motor"),
    ("EXC-02", 21, "hidraulica"),
    ("EXC-03", 19, "motor"),
    ("CAR-04", 15, "hidraulica"),
    ("CAM-03", 13, "motor"),
    ("EXC-01", 10, "hidraulica"),
    ("EXC-04", 8, "motor"),
    ("CAM-01", 6, "motor"),
]
PRECURSOR = {
    "motor": {"temperatura": 12, "vibracion": 2.6},
    "hidraulica": {"presion": -8, "consumo_combustible": 8},
}
VARIABLES_FALLA = {"motor": ["temperatura", "vibracion"], "hidraulica": ["consumo_combustible", "presion"]}
REPARACION_HORAS = {"motor": 20, "hidraulica": 12}
COMPONENTES_FALLA = {
    "motor": [("termostato", 1), ("rodamiento", 2)],
    "hidraulica": [("sello_hidraulico", 2), ("manguera_hidraulica", 1)],
}
CAUSAS = {
    "motor": ("Sobrecalentamiento por radiador obstruido y rodamiento desgastado",
              "Limpieza de radiador, cambio de termostato y de rodamientos"),
    "hidraulica": ("Fuga en el sello del cilindro hidraulico",
                   "Cambio de sellos y de manguera de alta presion"),
}
RIESGO_ACTUAL = ("EXC-03", "motor")
COMBUSTIBLE_TENDENCIA = "CAM-02"
COMBUSTIBLE_PICO = "EXC-02"

TECNICOS = [
    {"tecnico_id": "T-01", "nombre": "Ana Quispe", "especialidades": ["motor", "electrica"], "zona_id": "Z-NORTE"},
    {"tecnico_id": "T-02", "nombre": "Luis Mamani", "especialidades": ["hidraulica"], "zona_id": "Z-NORTE"},
    {"tecnico_id": "T-03", "nombre": "Rosa Huaman", "especialidades": ["motor"], "zona_id": "Z-CENTRO"},
    {"tecnico_id": "T-04", "nombre": "Jorge Condori", "especialidades": ["hidraulica", "motor"], "zona_id": "Z-CENTRO"},
    {"tecnico_id": "T-05", "nombre": "Carla Flores", "especialidades": ["electrica"], "zona_id": "Z-SUR"},
    {"tecnico_id": "T-06", "nombre": "Pedro Ramos", "especialidades": ["motor", "hidraulica"], "zona_id": "Z-SUR"},
]

COMPONENTES = [
    {"componente_id": "termostato", "nombre": "Termostato de motor", "categoria": "motor", "dias_reposicion": 10, "costo": 180},
    {"componente_id": "rodamiento", "nombre": "Rodamiento de rueda", "categoria": "motor", "dias_reposicion": 14, "costo": 320},
    {"componente_id": "radiador", "nombre": "Radiador", "categoria": "motor", "dias_reposicion": 21, "costo": 2400},
    {"componente_id": "sello_hidraulico", "nombre": "Kit de sellos hidraulicos", "categoria": "hidraulica", "dias_reposicion": 7, "costo": 150},
    {"componente_id": "manguera_hidraulica", "nombre": "Manguera de alta presion", "categoria": "hidraulica", "dias_reposicion": 5, "costo": 260},
    {"componente_id": "bomba_hidraulica", "nombre": "Bomba hidraulica", "categoria": "hidraulica", "dias_reposicion": 30, "costo": 5200},
    {"componente_id": "filtro_aceite", "nombre": "Filtro de aceite", "categoria": "mantenimiento", "dias_reposicion": 3, "costo": 45},
    {"componente_id": "filtro_combustible", "nombre": "Filtro de combustible", "categoria": "mantenimiento", "dias_reposicion": 3, "costo": 60},
    {"componente_id": "inyector", "nombre": "Inyector de combustible", "categoria": "motor", "dias_reposicion": 12, "costo": 640},
    {"componente_id": "alternador", "nombre": "Alternador", "categoria": "electrica", "dias_reposicion": 15, "costo": 900},
]
STOCK_BAJO = {("Z-NORTE", "termostato"): 0, ("Z-CENTRO", "sello_hidraulico"): 1, ("Z-SUR", "filtro_aceite"): 1}


def id_fijo(texto):
    return str(uuid.uuid5(ESPACIO_IDS, texto))


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def a_dynamo(valor):
    return json.loads(json.dumps(valor), parse_float=Decimal)


def hora_lima(dias_atras, hora, ahora):
    base = (ahora.astimezone(LIMA) - timedelta(days=dias_atras)).replace(hour=hora, minute=0, second=0, microsecond=0)
    return base.astimezone(timezone.utc)


def lectura_base(m, ts, horometro):
    modelo = MODELOS[m["modelo"]]
    zona = ZONA_POR_ID[m["zona"]]
    return {
        "maquina_id": m["id"],
        "ts": iso(ts),
        "modelo_id": m["modelo"],
        "zona_id": m["zona"],
        "lat": round(zona["lat"] + random.gauss(0, 0.004), 6),
        "lon": round(zona["lon"] + random.gauss(0, 0.004), 6),
        "estado": "operando",
        "horas_funcionamiento": round(horometro, 2),
        "temperatura": random.gauss(80, 2.5),
        "vibracion": random.gauss(2.5, 0.35),
        "presion": random.gauss(32, 1.2),
        "consumo_combustible": random.gauss(modelo["consumo"] * m.get("consumo", 1.0), 1.2),
        "carga_transportada": modelo["carga"] * m.get("carga", 1.0) * random.uniform(0.85, 1.05),
        "velocidad": modelo["velocidad"] * random.uniform(0.6, 1.2),
        "rpm": random.gauss(modelo["rpm"], 60),
        "lote_combustible": f"L{ts.isocalendar()[1]:02d}-{m['zona']}",
    }


def redondear(lectura):
    for campo, decimales in (("temperatura", 1), ("vibracion", 2), ("presion", 1), ("consumo_combustible", 2),
                             ("carga_transportada", 2), ("velocidad", 1), ("rpm", 0)):
        lectura[campo] = round(max(lectura[campo], 0), decimales)
    return lectura


def generar_telemetria(dias, ahora, fallas):
    inicio = (ahora.astimezone(LIMA) - timedelta(days=dias)).replace(hour=0, minute=0, second=0, microsecond=0)
    fin = ahora - timedelta(hours=1)
    ayer = ahora.astimezone(LIMA).date() - timedelta(days=1)
    lecturas = []

    for m in MAQUINAS:
        propias = [f for f in fallas if f["maquina_id"] == m["id"]]
        horometro = random.uniform(1500, 6000)
        dia = inicio
        while dia.date() <= fin.astimezone(LIMA).date():
            t = dia.replace(hour=m.get("inicio", 7))
            fin_turno = t + timedelta(hours=m.get("horas", 10))
            while t < fin_turno and t.astimezone(timezone.utc) <= fin:
                ts = t.astimezone(timezone.utc)
                if any(f["ts"] <= ts < f["fin"] for f in propias):
                    t += PASO
                    continue
                lectura = lectura_base(m, ts, horometro)
                for f in propias:
                    if f["ts"] - timedelta(hours=72) <= ts < f["ts"]:
                        for variable, delta in PRECURSOR[f["categoria"]].items():
                            lectura[variable] += delta
                if m["id"] == RIESGO_ACTUAL[0] and ts >= ahora - timedelta(hours=30):
                    for variable, delta in PRECURSOR[RIESGO_ACTUAL[1]].items():
                        lectura[variable] += delta
                dias_atras = (ahora - ts).total_seconds() / 86400
                if m["id"] == COMBUSTIBLE_TENDENCIA and dias_atras <= 7:
                    lectura["consumo_combustible"] += (7 - dias_atras) * 1.0
                if m["id"] == COMBUSTIBLE_PICO and t.date() == ayer:
                    lectura["consumo_combustible"] *= 1.5
                lecturas.append(redondear(lectura))
                horometro += PASO.total_seconds() / 3600
                t += PASO
            dia += timedelta(days=1)

        for f in propias:
            previas = [l for l in lecturas if l["maquina_id"] == m["id"] and l["ts"] < iso(f["ts"])]
            horas = max(previas, key=lambda l: l["ts"])["horas_funcionamiento"] if previas else round(horometro, 2)
            falla = redondear(lectura_base(m, f["ts"], horas))
            falla.update({"estado": "requiere_intervencion", "rpm": 0, "velocidad": 0, "carga_transportada": 0,
                          "consumo_combustible": 0})
            lecturas.append(falla)

    lecturas.sort(key=lambda l: (l["ts"], l["maquina_id"]))
    return lecturas


def preparar_fallas(ahora):
    fallas = []
    for maquina_id, dias_atras, categoria in FALLAS:
        ts = hora_lima(dias_atras, 11, ahora)
        fallas.append({
            "maquina_id": maquina_id,
            "categoria": categoria,
            "ts": ts,
            "fin": ts + timedelta(hours=REPARACION_HORAS[categoria]),
        })
    return sorted(fallas, key=lambda f: f["ts"])


def tecnico_para(zona_id, categoria):
    candidatos = [t for t in TECNICOS if categoria in t["especialidades"]]
    en_zona = [t for t in candidatos if t["zona_id"] == zona_id]
    return (en_zona or candidatos or TECNICOS)[0]["tecnico_id"]


def minutos(desde, hasta):
    return round((hasta - desde).total_seconds() / 60, 1)


def generar_ordenes_y_alertas(fallas):
    ordenes, alertas, consumos = [], [], []
    for f in fallas:
        m = MAQUINA_POR_ID[f["maquina_id"]]
        orden_id = id_fijo(f"orden-{m['id']}-{iso(f['ts'])}")
        alerta_id = id_fijo(f"alerta-{m['id']}-{iso(f['ts'])}")
        variables = VARIABLES_FALLA[f["categoria"]]
        ts_alerta = f["ts"] - timedelta(hours=3)
        alertas.append({
            "alerta_id": alerta_id,
            "ts": ts_alerta.isoformat(),
            "origen": "anomalias",
            "tipo": "anomalia",
            "estado": "cerrada",
            "maquina_id": m["id"],
            "zona_id": m["zona"],
            "modelo_id": m["modelo"],
            "severidad": "alta",
            "puntaje": round(random.uniform(70, 82), 1),
            "variables_afectadas": variables,
            "tendencia_creciente": True,
            "descripcion": f"Combinacion de {' y '.join(variables)} fuera de lo normal durante varias horas",
        })

        ts_asignada = f["ts"] + timedelta(minutes=25)
        ts_inicio = f["ts"] + timedelta(minutes=90)
        ts_fin = f["fin"]
        causa, trabajo = CAUSAS[f["categoria"]]
        componentes = [{"componente": c, "cantidad": n} for c, n in COMPONENTES_FALLA[f["categoria"]]]
        previa = next(
            (o for o in reversed(ordenes)
             if o["maquina_id"] == m["id"] and o["categoria"] == f["categoria"]
             and timedelta(0) <= f["ts"] - datetime.fromisoformat(o["ts_completada"]) <= timedelta(days=30)),
            None,
        )
        orden = {
            "orden_id": orden_id,
            "maquina_id": m["id"],
            "ts_creada": f["ts"].isoformat(),
            "tipo": "correctivo",
            "estado": "hecha",
            "origen": "alerta",
            "alerta_id": alerta_id,
            "descripcion": f"Alerta automatica: {', '.join(variables)}",
            "severidad": "alta",
            "categoria": f["categoria"],
            "tecnico_id": tecnico_para(m["zona"], f["categoria"]),
            "causa_raiz": causa,
            "trabajo_realizado": trabajo,
            "componentes_reemplazados": componentes,
            "ts_asignada": ts_asignada.isoformat(),
            "ts_inicio_atencion": ts_inicio.isoformat(),
            "ts_completada": ts_fin.isoformat(),
            "tiempo_respuesta_min": minutos(f["ts"], ts_inicio),
            "tiempo_reparacion_min": minutos(ts_inicio, ts_fin),
            "tiempo_detenido_min": minutos(f["ts"], ts_fin),
            "resumen_ia": f"Falla de {f['categoria']} resuelta: {causa.lower()}.",
            "acciones_ia": [],
            "resumen_por": "reglas",
        }
        if previa:
            orden["reincidente_de"] = previa["orden_id"]
        ordenes.append(orden)
        for c in componentes:
            consumos.append({
                "consumo_id": f"{orden_id}#{c['componente']}",
                "componente_id": c["componente"],
                "zona_id": m["zona"],
                "maquina_id": m["id"],
                "orden_id": orden_id,
                "cantidad": c["cantidad"],
                "ts": ts_fin.isoformat(),
                "origen": "orden",
            })
    return ordenes, alertas, consumos


def generar_mantenimientos(ahora):
    fechas, ordenes, consumos = {}, [], []
    for m in MAQUINAS:
        dias_atras = MANTENIMIENTO_DIAS.get(m["id"], random.randint(4, 15))
        inicio = hora_lima(dias_atras, 8, ahora)
        fin = inicio + timedelta(hours=6)
        fechas[m["id"]] = inicio.astimezone(LIMA).date().isoformat()
        orden_id = id_fijo(f"preventivo-{m['id']}-{fechas[m['id']]}")
        ordenes.append({
            "orden_id": orden_id,
            "maquina_id": m["id"],
            "ts_creada": (inicio - timedelta(hours=16)).isoformat(),
            "tipo": "preventivo",
            "prioridad": "media",
            "estado": "hecha",
            "ts_completada": fin.isoformat(),
        })
        for componente in ("filtro_aceite", "filtro_combustible"):
            consumos.append({
                "consumo_id": f"{orden_id}#{componente}",
                "componente_id": componente,
                "zona_id": m["zona"],
                "maquina_id": m["id"],
                "orden_id": orden_id,
                "cantidad": 1,
                "ts": fin.isoformat(),
                "origen": "orden",
            })
    return fechas, ordenes, consumos


def generar_consumos_manuales(dias, ahora):
    consumos = []
    for zona in ZONAS:
        for dias_atras in range(dias, 0, -2):
            ts = hora_lima(dias_atras, 15, ahora)
            consumos.append({
                "consumo_id": id_fijo(f"manual-{zona['zona_id']}-{dias_atras}"),
                "componente_id": "filtro_aceite",
                "zona_id": zona["zona_id"],
                "cantidad": 1,
                "ts": ts.isoformat(),
                "origen": "manual",
            })
    return consumos


def generar_inventario():
    filas = []
    for zona in ZONAS:
        for c in COMPONENTES:
            clave = (zona["zona_id"], c["componente_id"])
            filas.append({
                "zona_id": zona["zona_id"],
                "componente_id": c["componente_id"],
                "stock_actual": STOCK_BAJO.get(clave, random.randint(2, 9)),
            })
    return filas


def generar_maquinas(lecturas, fechas_mantenimiento):
    ultimas = {}
    for lectura in lecturas:
        ultimas[lectura["maquina_id"]] = lectura
    items = []
    for m in MAQUINAS:
        ultima = ultimas[m["id"]]
        items.append({
            "maquina_id": m["id"],
            "zona_id": m["zona"],
            "modelo_id": m["modelo"],
            "lat": ultima["lat"],
            "lon": ultima["lon"],
            "estado": ultima["estado"],
            "horas_totales": ultima["horas_funcionamiento"],
            "ultima_lectura": ultima,
            "ultima_lectura_ts": ultima["ts"],
            "ultima_recepcion_ts": ultima["ts"],
            "fecha_ult_mantenimiento": fechas_mantenimiento[m["id"]],
        })
    return items


def tabla_existe(dynamo, nombre):
    try:
        dynamo.meta.client.describe_table(TableName=nombre)
        return True
    except dynamo.meta.client.exceptions.ResourceNotFoundException:
        return False


def escribir(dynamo, stage, nombre, items):
    tabla_nombre = f"arquifusion-{stage}-{nombre}"
    if not tabla_existe(dynamo, tabla_nombre):
        print(f"  {tabla_nombre}: no existe (modulo no desplegado), se omite")
        return
    with dynamo.Table(tabla_nombre).batch_writer() as escritor:
        for item in items:
            escritor.put_item(Item=a_dynamo({k: v for k, v in item.items() if v is not None}))
    print(f"  {tabla_nombre}: {len(items)} items")


def subir_telemetria(s3, bucket, lecturas):
    por_fecha = defaultdict(list)
    for lectura in lecturas:
        por_fecha[lectura["ts"][:10]].append(lectura)
    for fecha, grupo in sorted(por_fecha.items()):
        s3.put_object(
            Bucket=bucket,
            Key=f"telemetria/fecha={fecha}/simulado-{fecha}.jsonl",
            Body="\n".join(json.dumps(l) for l in grupo).encode("utf-8"),
            ContentType="application/x-ndjson",
        )
    print(f"  s3://{bucket}/telemetria/: {len(lecturas)} lecturas en {len(por_fecha)} archivos")


def bucket_telemetria(region, stage):
    cf = boto3.client("cloudformation", region_name=region)
    salidas = cf.describe_stacks(StackName=f"arquifusion-nucleo-{stage}")["Stacks"][0]["Outputs"]
    return next(o["OutputValue"] for o in salidas if o["OutputKey"] == "BucketTelemetria")


def main():
    parser = argparse.ArgumentParser(description="Genera datos simulados directo en S3 y DynamoDB (sin invocar Lambdas)")
    parser.add_argument("--stage", default="dev")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--dias", type=int, default=30)
    parser.add_argument("--semilla", type=int, default=42)
    parser.add_argument("--sin-telemetria", action="store_true")
    args = parser.parse_args()

    random.seed(args.semilla)
    ahora = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    dynamo = boto3.resource("dynamodb", region_name=args.region)

    fallas = preparar_fallas(ahora)
    lecturas = generar_telemetria(args.dias, ahora, fallas)
    ordenes, alertas, consumos_falla = generar_ordenes_y_alertas(fallas)
    fechas_mant, preventivas, consumos_prev = generar_mantenimientos(ahora)
    consumos = consumos_falla + consumos_prev + generar_consumos_manuales(args.dias, ahora)

    print(f"Datos generados hasta {iso(ahora - timedelta(hours=1))}")
    if not args.sin_telemetria:
        subir_telemetria(boto3.client("s3", region_name=args.region), bucket_telemetria(args.region, args.stage), lecturas)

    escribir(dynamo, args.stage, "zona", ZONAS)
    escribir(dynamo, args.stage, "modelo", [
        {"modelo_id": mid, "nombre": d["nombre"], "capacidad": d["capacidad"], "intervalo": d["intervalo"], "umbrales": UMBRALES}
        for mid, d in MODELOS.items()
    ])
    escribir(dynamo, args.stage, "maquina", generar_maquinas(lecturas, fechas_mant))
    escribir(dynamo, args.stage, "orden_trabajo", ordenes + preventivas)
    escribir(dynamo, args.stage, "alerta", alertas)
    escribir(dynamo, args.stage, "tecnico", [
        {**t, "lat": ZONA_POR_ID[t["zona_id"]]["lat"] + 0.003, "lon": ZONA_POR_ID[t["zona_id"]]["lon"] - 0.003,
         "estado": "disponible", "asignaciones_activas": 0}
        for t in TECNICOS
    ])
    escribir(dynamo, args.stage, "componente", COMPONENTES)
    escribir(dynamo, args.stage, "inventario", generar_inventario())
    escribir(dynamo, args.stage, "consumo_repuesto", consumos)
    print("Listo. Siguiente paso: python3 datos/ejecutar_procesos.py")


if __name__ == "__main__":
    main()
