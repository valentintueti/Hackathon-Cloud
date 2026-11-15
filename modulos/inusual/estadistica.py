from datetime import datetime, timedelta

VARIABLES = ["temperatura", "vibracion", "presion", "consumo_combustible", "rpm"]
ORDEN_SEVERIDAD = {"normal": 0, "baja": 1, "media": 2, "alta": 3}
Z_EXTREMO = 6


def z(valor, media, desv):
    if valor is None or media is None or not desv:
        return None
    return (float(valor) - float(media)) / float(desv)


def comparar(lectura, base_maquina, base_modelo, z_umbral, min_muestras):
    referencias = []
    if base_maquina and int(base_maquina.get("n", 0)) >= min_muestras:
        referencias.append(("propio", base_maquina))
    if base_modelo and int(base_modelo.get("n", 0)) >= min_muestras:
        referencias.append(("pares", base_modelo))

    desvios = []
    for variable in VARIABLES:
        for nombre, base in referencias:
            stats = base.get("variables", {}).get(variable, {})
            valor_z = z(lectura.get(variable), stats.get("media"), stats.get("desv"))
            if valor_z is not None and abs(valor_z) >= z_umbral:
                desvios.append({
                    "variable": variable,
                    "valor": lectura.get(variable),
                    "referencia": nombre,
                    "media": round(float(stats["media"]), 2),
                    "desv": round(float(stats["desv"]), 2),
                    "z": round(valor_z, 2),
                })
    return desvios


def severidad(desvios):
    if not desvios:
        return "normal"
    variables = {d["variable"] for d in desvios}
    en_ambas = {v for v in variables if {d["referencia"] for d in desvios if d["variable"] == v} == {"propio", "pares"}}
    if len(en_ambas) >= 3 or any(abs(d["z"]) >= Z_EXTREMO for d in desvios):
        return "alta"
    if len(variables) >= 2 or en_ambas:
        return "media"
    return "baja"


def debe_alertar(severidad_nueva, anterior, ts_anterior, ahora, minutos_entre_alertas):
    if severidad_nueva == "normal":
        return False
    if not anterior or not ts_anterior:
        return True
    if ORDEN_SEVERIDAD[severidad_nueva] > ORDEN_SEVERIDAD.get(anterior, 0):
        return True
    return ahora - datetime.fromisoformat(ts_anterior) >= timedelta(minutes=minutos_entre_alertas)


def descripcion(desvios):
    return "; ".join(
        f"{d['variable']} {d['valor']} ({d['referencia']}: media {d['media']}, z {d['z']})" for d in desvios
    )