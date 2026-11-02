#!/usr/bin/env python3
"""Avisos de atalaya por Telegram.

Se ejecuta en la Action justo después de calcular las alertas. Compara con lo que había en
la ejecución anterior y avisa solo de lo nuevo:
  - un país sube de nivel o empieza a empeorar,
  - una señal clave: corte de internet o bloqueo de mensajería nuevos, Exteriores o EE. UU.
    suben su aviso de viaje, desastre con alerta roja, brote grave,
  - una ruta marítima pasa a riesgo alto,
y una vez al día manda un resumen del informe.

Necesita los secretos TELEGRAM_TOKEN (del bot, creado con @BotFather) y TELEGRAM_CHAT (el
chat, grupo o canal). Sin ellos no hace nada. Un fallo al enviar nunca rompe la actualización.

Cada mensaje recuerda que es una estimación automática sin validez oficial.
"""

import html
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

SALIDA = Path(os.environ.get("ATALAYA_SALIDA") or Path(__file__).resolve().parent.parent / "data")
TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
CHAT = os.environ.get("TELEGRAM_CHAT", "").strip()
WEB = (os.environ.get("ATALAYA_URL", "").strip() or "https://serbenda.github.io/atalaya/").rstrip("/") + "/"
AHORA = datetime.now(timezone.utc)
HORA_RESUMEN_UTC = 7            # el resumen diario sale en la primera ejecución a partir de las 7:00 UTC
MAX_MENSAJES = 5                # si hay más avisos, se agrupan en uno
ESPERA_PAIS = timedelta(hours=6)  # no repetir avisos del mismo país en menos de 6 h (salvo que pase a alerta)
PIE = "<i>Estimación automática a partir de fuentes públicas, sin validez oficial.</i>"
RANGO = {"verde": 0, "ambar": 1, "rojo": 2}
NIVEL = {"verde": "sin alerta", "ambar": "vigilar", "rojo": "alerta"}
ICONO = {"verde": "🟢", "ambar": "🟠", "rojo": "🔴"}
CONFIANZA = {"alta": "lo confirman varios tipos de fuente", "media": "lo confirma una fuente oficial o técnica",
             "baja": "solo lo recoge la prensa"}


def leer(nombre, defecto):
    try:
        return json.loads((SALIDA / nombre).read_text("utf-8"))
    except (OSError, ValueError):
        return defecto


def esc(texto):
    return html.escape(str(texto or ""), quote=False)


def nombres_es():
    try:
        lista = json.loads((Path(__file__).resolve().parent.parent / "data" / "paises.json").read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    return {p["a3"]: (p.get("nombres_es") or p["nombres"])[0] for p in lista}


NOMBRES = nombres_es()


def nombre(a3):
    return NOMBRES.get(a3, a3)


def enlace(a3=None):
    return f'<a href="{WEB}{"#pais=" + a3 if a3 else ""}">Ver en atalaya</a>'


def enviar(texto):
    """Envía un mensaje. Devuelve True si Telegram lo acepta."""
    datos = json.dumps({"chat_id": CHAT, "text": texto, "parse_mode": "HTML",
                        "disable_web_page_preview": True}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data=datos,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read()).get("ok", False)
    except Exception as e:  # noqa: BLE001
        print(f"  Telegram no ha aceptado el mensaje: {e}", file=sys.stderr)
        return False


# ------------------------------------------------------------ qué avisar

SEÑALES = {
    "censura": lambda e: e.get("nivel") != "verde",
    "internet": lambda e: e.get("nivel") != "verde",
    "aviso": lambda e: e.get("peso", 0) > 0,
    "desastre": lambda e: e.get("nivel") == "rojo",
    "terremoto": lambda e: e.get("nivel") == "rojo",
    "epidemia": lambda e: e.get("nivel") != "verde",
}


def avisos_nuevos(alertas, eventos, estado):
    """Lista de (clave, país, texto) con lo que ha cambiado desde la ejecución anterior."""
    previos = estado.get("niveles", {})
    escaladas = set(estado.get("escaladas", []))
    enviados = set(estado.get("enviados", {}))
    avisos = []
    for a3, p in alertas.get("paises", {}).items():
        antes = previos.get(a3, "verde")
        if RANGO[p["nivel"]] > RANGO[antes]:
            motivos = ". ".join(p.get("motivos", [])[:3])
            pron = (p.get("pronostico") or {}).get("texto")
            lineas = [f"{ICONO[p['nivel']]} <b>{esc(nombre(a3))} pasa a {NIVEL[p['nivel']]}</b>"
                      + (f" ({CONFIANZA[p['confianza']]})" if p.get("confianza") in CONFIANZA else "")]
            if motivos:
                lineas.append(esc(motivos))
            if pron:
                lineas.append(esc(pron) + ".")
            lineas.append(enlace(a3))
            texto = "\n".join(lineas)
            avisos.append((f"nivel-{a3}-{p['nivel']}", a3, texto, p["nivel"] == "rojo"))
        elif p.get("escalada") and a3 not in escaladas and p["nivel"] != "verde":
            texto = (f"📈 <b>{esc(nombre(a3))} empeora respecto a lo habitual</b>\n"
                     f"{esc('. '.join(p.get('motivos', [])[:3]))}\n{enlace(a3)}")
            avisos.append((f"escalada-{a3}", a3, texto, False))
    for e in eventos.get("eventos", []):
        regla = SEÑALES.get(e.get("tipo"))
        if not regla or not regla(e) or e["id"] in enviados:
            continue
        fecha = e.get("fecha", "")
        if fecha and fecha < (AHORA - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ"):
            continue  # solo lo de las últimas 24 h
        pais = f"{nombre(e['pais'])}: " if e.get("pais") else ""
        texto = f"⚠️ <b>{esc(pais)}{esc(e.get('titulo'))}</b>\n{esc(e.get('fuente'))}"
        if e.get("url"):
            texto += f' · <a href="{esc(e["url"])}">fuente</a>'
        texto += f"\n{enlace(e.get('pais'))}"
        avisos.append((e["id"], e.get("pais"), texto, e.get("nivel") == "rojo"))
    pasos_previos = estado.get("pasos", {})
    for paso in alertas.get("pasos", []):
        if paso["nivel"] == "rojo" and pasos_previos.get(paso["id"]) != "rojo":
            texto = (f"⚓ <b>Riesgo alto en {esc(paso['nombre'])}</b>\n{esc(paso['porque'])}. "
                     f"{paso['hechos']} hechos violentos en la zona en 24 horas.\n{enlace()}")
            avisos.append((f"paso-{paso['id']}", None, texto, True))
    return avisos


def filtrar(avisos, estado):
    """Quita repeticiones: lo ya enviado y el mismo país en menos de 6 h (salvo que pase a alerta)."""
    enviados = estado.get("enviados", {})
    ultimo_pais = estado.get("ultimo_pais", {})
    quedan = []
    for clave, pais, texto, urgente in avisos:
        if clave in enviados:
            continue
        ultimo = ultimo_pais.get(pais) if pais else None
        if ultimo and not urgente and ultimo > (AHORA - ESPERA_PAIS).strftime("%Y-%m-%dT%H:%M:%SZ"):
            continue
        quedan.append((clave, pais, texto, urgente))
    return quedan


def resumen_diario(alertas):
    inf = alertas.get("informe", {})
    paises = alertas.get("paises", {})
    c = inf.get("conclusion", {})
    rojos = sum(1 for p in paises.values() if p["nivel"] == "rojo")
    ambar = sum(1 for p in paises.values() if p["nivel"] == "ambar")
    lineas = [f"🗺️ <b>atalaya, {AHORA.strftime('%d/%m/%Y')}</b>",
              f"{rojos} {'país' if rojos == 1 else 'países'} en alerta y {ambar} para vigilar.", ""]
    if c.get("pais"):
        lineas.append(f"<b>Conclusión principal:</b> {esc(nombre(c['pais']))}, {esc((c.get('texto') or '').lower())}.")
    juicios = inf.get("juicios", [])[:4]
    if juicios:
        lineas += ["", "<b>Juicios clave</b>"]
        lineas += [f"{ICONO[j['nivel']]} {esc(nombre(j['pais']))}: {esc((j.get('escenario') or j.get('pronostico') or '').lower())}"
                   for j in juicios]
    espana = [e for e in inf.get("espana", []) if e.get("pais")][:3]
    if espana:
        lineas += ["", "<b>Interés para España</b>"]
        lineas += [f"• {esc(nombre(e['pais']))}: {esc(e['por'][0].lower())}" for e in espana]
    sim = (alertas.get("simulacion") or {}).get("resumen", {})
    if sim.get("mas_escala"):
        lineas += ["", f"<b>Simulación, más riesgo de escalada:</b> {esc(', '.join(nombre(a) for a in sim['mas_escala']))}"]
    lineas += ["", enlace(), PIE]
    return "\n".join(lineas)


def rss(alertas, eventos, estado):
    """Feed RSS con los últimos cambios (los mismos que irían a Telegram), en la rama datos."""
    previos = leer("rss.json", [])
    nuevos = []
    if estado:  # la primera vez no hay con qué comparar
        for clave, pais, texto, _ in filtrar(avisos_nuevos(alertas, eventos, estado), {}):
            titulo = html.unescape(re.sub(r"<[^>]+>", "", texto.split("\n")[0])).strip(" ⚠️📈🔴🟠🟢⚓")
            cuerpo = html.unescape(re.sub(r"<[^>]+>", "", "\n".join(texto.split("\n")[1:-1])))
            nuevos.append({"id": clave, "titulo": titulo, "texto": cuerpo, "pais": pais,
                           "fecha": AHORA.strftime("%a, %d %b %Y %H:%M:%S GMT")})
    vistos = {x["id"] for x in previos}
    items = ([x for x in nuevos if x["id"] not in vistos] + previos)[:50]
    (SALIDA / "rss.json").write_text(json.dumps(items, ensure_ascii=False), "utf-8")
    cuerpo = "".join(
        f"<item><title>{html.escape(x['titulo'])}</title>"
        f"<link>{html.escape(WEB + ('#pais=' + x['pais'] if x.get('pais') else ''))}</link>"
        f"<guid isPermaLink=\"false\">{html.escape(x['id'])}</guid><pubDate>{x['fecha']}</pubDate>"
        f"<description>{html.escape(x['texto'] + ' Estimación automática a partir de fuentes públicas, sin validez oficial.')}</description></item>"
        for x in items)
    (SALIDA / "avisos.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
        f"<title>atalaya: avisos</title><link>{WEB}</link>"
        "<description>Cambios de nivel y señales clave de atalaya. Estimaciones automáticas sin validez oficial.</description>"
        f"<language>es</language>{cuerpo}</channel></rss>", "utf-8")


def main():
    alertas = leer("alertas.json", {})
    eventos = leer("eventos.json", {})
    estado = leer("telegram.json", {})
    primera_vez = not estado
    rss(alertas, eventos, estado)
    ahora_txt = AHORA.strftime("%Y-%m-%dT%H:%M:%SZ")
    corte = (AHORA - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    enviados = {k: v for k, v in estado.get("enviados", {}).items() if v > corte}
    estado["enviados"] = enviados
    activo = bool(TOKEN and CHAT)
    if not activo:
        print("Telegram sin configurar (faltan TELEGRAM_TOKEN o TELEGRAM_CHAT): solo se actualiza el RSS.")

    avisos = [] if primera_vez or not activo else filtrar(avisos_nuevos(alertas, eventos, estado), estado)
    if len(avisos) > MAX_MENSAJES:
        # Demasiados a la vez: un solo mensaje con todo, para no saturar
        texto = f"🔔 <b>{len(avisos)} cambios en atalaya</b>\n\n" + "\n\n".join(t for _, _, t, _ in avisos[:12])
        if len(avisos) > 12:
            texto += f"\n\n… y {len(avisos) - 12} más."
        mensajes = [(texto + "\n\n" + PIE, avisos)]
    else:
        mensajes = [(t + "\n" + PIE, [(c, p, t, u)]) for c, p, t, u in avisos]
    for texto, incluidos in mensajes:
        if enviar(texto[:4000]):
            for clave, pais, _, _ in incluidos:
                enviados[clave] = ahora_txt
                if pais:
                    estado.setdefault("ultimo_pais", {})[pais] = ahora_txt

    hoy = AHORA.strftime("%Y-%m-%d")
    if activo and AHORA.hour >= HORA_RESUMEN_UTC and estado.get("resumen") != hoy and alertas.get("paises"):
        if enviar(resumen_diario(alertas)):
            estado["resumen"] = hoy

    # Se guarda la situación de ahora para comparar en la siguiente ejecución
    estado["niveles"] = {a3: p["nivel"] for a3, p in alertas.get("paises", {}).items()}
    estado["escaladas"] = [a3 for a3, p in alertas.get("paises", {}).items() if p.get("escalada")]
    estado["pasos"] = {p["id"]: p["nivel"] for p in alertas.get("pasos", [])}
    if primera_vez or not activo:
        # Sin envío (primera vez o sin bot), lo actual se marca como visto para no avisar luego de golpe
        for e in eventos.get("eventos", []):
            enviados.setdefault(e["id"], ahora_txt)
    (SALIDA / "telegram.json").write_text(json.dumps(estado, ensure_ascii=False), "utf-8")
    print(f"Telegram: {len(avisos)} avisos{', primera ejecución: solo se guarda el estado' if primera_vez else ''}.")


if __name__ == "__main__":
    main()
