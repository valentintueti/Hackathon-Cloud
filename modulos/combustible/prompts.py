import json

SISTEMA = (
    "Eres analista de mantenimiento de ArquiFusion, empresa de maquinaria pesada. "
    "Explicas en español, en texto plano sin markdown ni emojis, por qué el consumo de combustible "
    "de una máquina salió anómalo y qué conviene revisar primero. "
    "Usa solo los datos que se te entregan: no inventes valores. "
    "Presenta la causa como una hipótesis a revisar, no como una certeza. "
    "Responde únicamente un objeto JSON cuyas claves son los maquina_id y cuyos valores son "
    "la explicación de cada una (máximo 400 caracteres)."
)

CASOS = {
    "propio": "ayer consumió más que su propio historial de las últimas semanas",
    "modelo": "consume más que las otras máquinas de su mismo modelo",
    "tendencia": "su consumo sube de forma constante en los últimos días",
}

PISTAS = {
    "propio": "un cambio reciente (filtros obstruidos, fuga, inyectores o un trabajo más pesado de lo normal)",
    "modelo": "un problema que viene de antes (calibración, desgaste del motor o hábitos de operación)",
    "tendencia": "un desgaste progresivo (filtros que se saturan, neumáticos con baja presión o inyectores deteriorándose)",
}


def construir(sospechosas):
    lineas = ["Máquinas con consumo de combustible anómalo detectadas hoy:", ""]
    for s in sospechosas:
        datos = {k: v for k, v in s.items() if v not in (None, "", [])}
        lineas.append(json.dumps(datos, ensure_ascii=False, default=str))
    lineas += ["", "Significado de cada caso:"]
    lineas += [f"- {caso}: {texto}" for caso, texto in CASOS.items()]
    lineas += [
        "",
        "Para cada maquina_id, explica en una o dos frases qué se detectó (con los números) "
        "y qué conviene revisar primero.",
    ]
    return "\n".join(lineas)


def respaldo(s):
    partes = []
    if "propio" in s["casos"]:
        partes.append(
            f"ayer consumió {s.get('consumo_ayer')} {s.get('unidad')}, "
            f"{s.get('pct_propio')}% más que su promedio ({s.get('media_propia')})"
        )
    if "modelo" in s["casos"]:
        partes.append(f"consume {s.get('pct_modelo')}% más que las otras máquinas de su modelo")
    if "tendencia" in s["casos"]:
        partes.append(f"su consumo sube {s.get('pendiente_diaria')} {s.get('unidad')} por día de forma constante")
    revisar = "; ".join(PISTAS[c] for c in s["casos"] if c in PISTAS)
    return f"Máquina {s['maquina_id']}: " + "; ".join(partes) + f". Posibles causas a revisar: {revisar}."