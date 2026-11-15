def presentes(items_maquina, patrones):
    items = set(items_maquina)
    return [p for p in patrones if set(p["items"]) <= items]


def _limitar(valor, minimo=0.0, maximo=1.0):
    return max(minimo, min(maximo, valor))


def puntaje(patrones_presentes, porcentaje_intervalo=None, health_score=None,
            reincidencias=0, dias_desde_falla=None):
    factores = {}

    if patrones_presentes:
        fuerza = sum(min(float(p["lift"]), 5.0) for p in patrones_presentes)
        factores["patrones"] = round(40 * _limitar(fuerza / 5), 1)

    if porcentaje_intervalo is not None:
        factores["preventivo"] = round(20 * _limitar(float(porcentaje_intervalo) / 100), 1)

    if health_score is not None:
        factores["salud"] = round(20 * _limitar((100 - float(health_score)) / 100), 1)

    historial = 0.0
    if reincidencias:
        historial += min(10.0, 5.0 * reincidencias)
    if dias_desde_falla is not None:
        historial += 10 * _limitar(1 - dias_desde_falla / 30)
    if historial:
        factores["historial"] = round(historial, 1)

    total = round(min(100.0, sum(factores.values())), 1)
    return total, factores


def nivel(valor, umbral_medio, umbral_alto):
    if valor >= umbral_alto:
        return "alto"
    if valor >= umbral_medio:
        return "medio"
    return "bajo"


def variables_de(patrones_presentes):
    vistas = []
    for p in patrones_presentes:
        for item in p["items"]:
            variable = item.rsplit(" ", 1)[0]
            if variable not in vistas:
                vistas.append(variable)
    return vistas


def respaldo(m):
    variables = variables_de(m.get("patrones_presentes", []))
    detalle = ", ".join(variables) if variables else "sus variables principales"
    if m["nivel"] == "alto":
        return f"Programar inspeccion de {m['maquina_id']} en las proximas 48 h, revisando {detalle}."
    return f"Revisar {m['maquina_id']} en la proxima parada programada, con atencion a {detalle}."