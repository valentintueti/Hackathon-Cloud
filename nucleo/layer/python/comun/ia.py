import json
import urllib.error
import urllib.request

from comun.config import secreto

URL = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
MODELO_DEFECTO = "gemini-2.5-flash"


def _llamar(prompt, instrucciones=None, json_salida=False, temperatura=0.3, max_tokens=800, timeout=20):
    s = secreto()
    clave = s.get("gemini_api_key")
    if not clave:
        print("Gemini sin configurar: falta gemini_api_key en el secreto")
        return None

    cuerpo = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperatura, "maxOutputTokens": max_tokens},
    }
    if instrucciones:
        cuerpo["systemInstruction"] = {"parts": [{"text": instrucciones}]}
    if json_salida:
        cuerpo["generationConfig"]["responseMimeType"] = "application/json"

    peticion = urllib.request.Request(
        URL.format(modelo=s.get("gemini_modelo") or MODELO_DEFECTO),
        data=json.dumps(cuerpo).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": clave},
        method="POST",
    )
    try:
        with urllib.request.urlopen(peticion, timeout=timeout) as respuesta:
            datos = json.loads(respuesta.read())
        return datos["candidates"][0]["content"]["parts"][0]["text"].strip()
    except urllib.error.HTTPError as error:
        print(f"Gemini respondio {error.code}: {error.read()[:300]}")
    except Exception as error:
        print(f"No se pudo usar Gemini: {error}")
    return None


def generar_texto(prompt, instrucciones=None, **opciones):
    return _llamar(prompt, instrucciones, json_salida=False, **opciones)


def generar_json(prompt, instrucciones=None, **opciones):
    texto = _llamar(prompt, instrucciones, json_salida=True, **opciones)
    if not texto:
        return None
    texto = texto.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        print(f"Gemini no devolvio JSON valido: {texto[:300]}")
        return None