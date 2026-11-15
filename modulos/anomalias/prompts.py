import json

SISTEMA = (
    "Eres analista de mantenimiento predictivo de maquinaria pesada (excavadoras, camiones, cargadores). "
    "Explicas alertas a un responsable de mantenimiento en español simple, sin markdown ni emojis. "
    "Explica por que la combinacion de variables es preocupante, no cada variable por separado. "
    "Puedes mencionar causas mecanicas posibles como orientacion, pero nunca inventes valores ni datos que no esten. "
    "Responde solo un JSON con las claves: "
    "\"explicacion\" (texto de maximo 4 oraciones) y "
    "\"revisar_primero\" (lista de 1 a 3 acciones concretas, de la mas urgente a la menos)."
)


def construir(alerta):
    datos = {
        "maquina": alerta.get("maquina_id"),
        "modelo": alerta.get("modelo_id"),
        "zona": alerta.get("zona_id"),
        "severidad": alerta.get("severidad"),
        "puntaje_riesgo_0_a_100": alerta.get("puntaje"),
        "variables_fuera_de_rango": alerta.get("variables_afectadas"),
        "valores_actuales": alerta.get("valores"),
        "umbrales_del_modelo": alerta.get("umbrales"),
        "riesgo_en_aumento": alerta.get("tendencia_creciente"),
    }
    datos = {k: v for k, v in datos.items() if v not in (None, "", [], {})}
    return (
        "Alerta de anomalia multivariable en una maquina de la flota.\n"
        "En los umbrales, 'normal' es el valor esperado y 'limite' el valor critico "
        "(en presion el limite es menor que lo normal porque lo peligroso es que baje).\n"
        f"Datos: {json.dumps(datos, ensure_ascii=False, default=str)}"
    )