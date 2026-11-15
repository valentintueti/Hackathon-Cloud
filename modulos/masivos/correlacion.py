from collections import defaultdict

ESTADOS_AFECTADOS = ("detenida", "requiere_intervencion")
SEVERIDADES_CONSIDERADAS = ("media", "alta", "critica")


def _mas_antiguo(actual, nuevo):
    if not nuevo:
        return actual
    if actual is None or nuevo < actual:
        return nuevo
    return actual


def afectadas_por_zona(alertas, maquinas, desde):
    por_zona = defaultdict(dict)
    for a in alertas:
        zona = a.get("zona_id")
        mid = a.get("maquina_id")
        if not zona or not mid or a.get("severidad") not in SEVERIDADES_CONSIDERADAS:
            continue
        por_zona[zona][mid] = _mas_antiguo(por_zona[zona].get(mid), a.get("ts"))
    for m in maquinas:
        zona = m.get("zona_id")
        mid = m.get("maquina_id")
        if not zona or m.get("estado") not in ESTADOS_AFECTADOS:
            continue
        recepcion = m.get("ultima_recepcion_ts") or m.get("ultima_lectura_ts")
        if not recepcion or str(recepcion) < desde:
            continue
        por_zona[zona][mid] = _mas_antiguo(por_zona[zona].get(mid), m.get("ultima_lectura_ts"))
    return por_zona


def armar_grupos(por_zona, min_maquinas):
    grupos = []
    for zona, afectadas in por_zona.items():
        if len(afectadas) < min_maquinas:
            continue
        inicios = [ts for ts in afectadas.values() if ts]
        grupos.append({
            "zona_id": zona,
            "maquinas": sorted(afectadas),
            "inicio": min(inicios) if inicios else None,
        })
    return grupos


def factores_compartidos(tipo, valor_por_maquina):
    maquinas_por_valor = defaultdict(list)
    for mid, valor in valor_por_maquina.items():
        if valor is not None and valor != "":
            maquinas_por_valor[valor].append(mid)
    return [
        {"tipo": tipo, "valor": valor, "maquinas": sorted(ms), "cantidad": len(ms)}
        for valor, ms in maquinas_por_valor.items()
        if len(ms) >= 2
    ]


def factores_variables(filas):
    por_variable = defaultdict(list)
    for f in filas:
        direccion = "subio" if float(f["direccion"]) > 0 else "bajo"
        por_variable[(f["variable"], direccion)].append(f)
    factores = []
    for (variable, direccion), grupo in por_variable.items():
        maquinas = sorted({f["maquina_id"] for f in grupo})
        if len(maquinas) < 2:
            continue
        inicios = sorted(str(f["inicio"]) for f in grupo)
        factores.append({
            "tipo": "variable",
            "valor": f"{variable} {direccion}",
            "maquinas": maquinas,
            "cantidad": len(maquinas),
            "desde": inicios[0],
            "hasta": inicios[-1],
        })
    return factores


def ordenar(factores):
    return sorted(factores, key=lambda f: f["cantidad"], reverse=True)


def descripcion(zona_id, maquinas, factores):
    texto = f"{len(maquinas)} maquinas afectadas en la zona {zona_id} ({', '.join(maquinas)})."
    if not factores:
        return texto + " No se encontro un factor comun."
    partes = []
    for f in factores[:3]:
        parte = f"{f['tipo']} {f['valor']} ({f['cantidad']} de {len(maquinas)})"
        if f.get("desde"):
            parte += f" entre {f['desde'][11:16]} y {f['hasta'][11:16]}"
        partes.append(parte)
    return texto + " Posibles causas comunes: " + "; ".join(partes) + "."