from datetime import datetime, timedelta


UMBRALES_POR_DEFECTO = {
    "temperatura": {"normal": 90, "limite": 110},
    "vibracion": {"normal": 4, "limite": 8},
    "presion": {"normal": 30, "limite": 20},
    "consumo_combustible": {"normal": 30, "limite": 45},
}

PESOS = {"temperatura": 0.30, "vibracion": 0.35, "presion": 0.15, "consumo_combustible": 0.20}

DESVIACION_RELEVANTE = 0.3
BONUS_DOS_VARIABLES = 15
BONUS_TRES_O_MAS = 25
BONUS_TENDENCIA = 10


SEVERIDADES = [("critica", 85), ("alta", 70), ("media", 50), ("baja", 30)]
ORDEN_SEVERIDAD = {"normal": 0, "baja": 1, "media": 2, "alta": 3, "critica": 4}


def debe_evaluar(lectura):
    return lectura.get("estado") != "detenida" and (lectura.get("rpm") or 0) > 0


def desviacion(valor, normal, limite):
    if valor is None or limite == normal:
        return 0.0
    return max(0.0, (valor - normal) / (limite - normal))


def puntaje(lectura, umbrales):
    desviaciones = {}
    for variable, peso in PESOS.items():
        if variable in umbrales and lectura.get(variable) is not None:
            u = umbrales[variable]
            desviaciones[variable] = desviacion(float(lectura[variable]), float(u["normal"]), float(u["limite"]))
    if not desviaciones:
        return 0.0, []

    peso_total = sum(PESOS[v] for v in desviaciones)
    base = sum(min(d, 1.5) * PESOS[v] for v, d in desviaciones.items()) / peso_total * 100 / 1.5 * 1.2
    afectadas = sorted(v for v, d in desviaciones.items() if d >= DESVIACION_RELEVANTE)

    bonus = BONUS_TRES_O_MAS if len(afectadas) >= 3 else BONUS_DOS_VARIABLES if len(afectadas) == 2 else 0
    return min(100.0, round(base + bonus, 1)), afectadas


def tendencia(ventana):
    if len(ventana) < 5:
        return 0
    mitad = len(ventana) // 2
    antes = sum(ventana[:mitad]) / mitad
    despues = sum(ventana[mitad:]) / (len(ventana) - mitad)
    return BONUS_TENDENCIA if despues > antes + 10 else 0


def severidad(valor):
    for nombre, minimo in SEVERIDADES:
        if valor >= minimo:
            return nombre
    return "normal"


def debe_alertar(severidad_nueva, maquina, ahora, minutos_entre_alertas):
    if severidad_nueva == "normal":
        return False
    anterior = maquina.get("ultima_alerta_severidad")
    ts_anterior = maquina.get("ultima_alerta_ts")
    if not anterior or not ts_anterior:
        return True
    if ORDEN_SEVERIDAD[severidad_nueva] > ORDEN_SEVERIDAD.get(anterior, 0):
        return True
    return ahora - datetime.fromisoformat(ts_anterior) >= timedelta(minutes=minutos_entre_alertas)