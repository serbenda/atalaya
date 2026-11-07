#!/usr/bin/env python3
"""Luces nocturnas por satélite (NASA Black Marble, VIIRS NOAA-20).

Cada noche el satélite mide cuánta luz emite cada zona de la Tierra. Cuando una ciudad se
apaga de golpe —bombardeos a la red eléctrica, cortes de suministro, una ciudad que se vacía—
se ve desde el espacio, sin depender de lo que cuente la prensa.

Cómo se mide:
  - Se vigilan los lugares con más violencia en GDELT de los países en guerra o en alerta
    (hasta 3 por país), y se guardan para seguirlos aunque dejen de salir en las noticias.
  - Cada día se lee el producto diario corregido de luna, atmósfera y nieve (VJ146A2), que llega
    con unos 3 días de retraso, en un círculo de unos 3 km alrededor de cada lugar. Solo cuentan
    los píxeles de calidad alta (sin nubes).
  - Lo normal es el compuesto mensual del mes anterior (VJ146A3) en el mismo sitio.
  - Hay aviso si la luz cae a la mitad o menos de lo normal en dos observaciones seguidas:
    una sola noche puede ser una nube mal detectada.

Necesita EARTHDATA_TOKEN y los paquetes h5py y numpy (solo este script; el resto de atalaya
sigue en Python estándar). Escribe luces.json, que actualizar.py lee como una fuente más.

Uso: python scripts/luces.py
"""

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = Path(os.environ.get("ATALAYA_SALIDA") or RAIZ / "data")
TOKEN = os.environ.get("EARTHDATA_TOKEN", "").strip()
LAADS = "https://ladsweb.modaps.eosdis.nasa.gov/api/v2/content"
DIARIO, MENSUAL = "VJ146A2", "VJ146A3"
CAMPOS = "HDFEOS/GRIDS/VIIRS_Grid_DNB_2d/Data Fields/"

FIJOS = ("UKR", "RUS", "SDN", "PSE", "ISR", "MMR", "COD", "SYR", "YEM", "LBN", "SSD", "ETH")
MAX_PAISES = 20
PUNTOS_POR_PAIS = 3
RADIO = 6               # píxeles de 15" (~460 m): unos 3 km
MIN_VALIDOS = 0.4       # parte del círculo sin nubes para fiarse del dato
MIN_BASE = 3.0          # nW/cm²/sr: por debajo, el sitio es demasiado oscuro para juzgar
CAIDA = 0.5             # aviso si la luz baja a la mitad o menos
CAIDA_GRAVE = 0.3
DIAS_HISTORIAL = 60
AHORA = datetime.now(timezone.utc)
DEPURAR = os.environ.get("ATALAYA_DEPURAR") == "1"


def log(*a):
    print(*a, flush=True)


def leer(nombre, defecto):
    try:
        return json.loads((SALIDA / nombre).read_text("utf-8"))
    except (OSError, ValueError):
        return defecto


def escribir(nombre, datos):
    (SALIDA / nombre).write_text(json.dumps(datos, ensure_ascii=False, separators=(",", ":")), "utf-8")


def pedir(url, destino=None):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOKEN}", "User-Agent": "atalaya/1.0"})
    for intento in range(3):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                datos = r.read()
            if destino:
                destino.write_bytes(datos)
                return destino
            return datos
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            log(f"  NASA ha respondido HTTP {e.code} a {url.split('?')[0].rsplit('/', 1)[-1]}")
            if e.code in (401, 403):
                raise SystemExit("El token de Earthdata no vale o falta autorizar LAADS DAAC en tu cuenta.")
        except (urllib.error.URLError, TimeoutError) as e:
            log(f"  sin respuesta ({e}), reintento")
    return None


def baldosa(lat, lon):
    """Cuadrícula de Black Marble: baldosas de 10° (h de 0 a 35, v de 0 a 17)."""
    return f"h{int((lon + 180) // 10):02d}v{int((90 - lat) // 10):02d}"


def ficheros_del_dia(producto, dia):
    """Baldosas de un día: {"h21v07": enlace}. El listado del archivo trae todas; el de la API v2
    va por páginas, así que solo se usa de reserva siguiendo sus páginas."""
    ruta = f"allData/5200/{producto}/{dia.year}/{dia.timetuple().tm_yday:03d}"
    datos = pedir(f"https://ladsweb.modaps.eosdis.nasa.gov/archive/{ruta}.json")
    salida = {}
    if datos:
        try:
            contenido = json.loads(datos)
            contenido = contenido.get("content", contenido) if isinstance(contenido, dict) else contenido
            for x in contenido:
                nombre = x.get("name", "")
                if nombre.endswith(".h5"):
                    salida[nombre.split(".")[2]] = f"https://ladsweb.modaps.eosdis.nasa.gov/archive/{ruta}/{nombre}"
        except (ValueError, AttributeError):
            salida = {}
    if salida:
        return salida
    url = f"{LAADS}/details/{ruta}?format=json"
    for _ in range(10):
        datos = pedir(url)
        if not datos:
            break
        j = json.loads(datos)
        for x in j.get("content", []):
            if x.get("name", "").endswith(".h5"):
                salida[x["name"].split(".")[2]] = x["downloadsLink"]
        url = j.get("nextPageLink") or j.get("next") or (j.get("links") or {}).get("next")
        if not url:
            break
    return salida


def ultimo_dia(producto, desde, dias=10):
    for d in range(dias):
        dia = desde - timedelta(days=d)
        lista = ficheros_del_dia(producto, dia)
        if len(lista) > 150:  # el día está completo
            return dia, lista
    return None, {}


def elegir_puntos(puntos):
    """Añade lugares nuevos con violencia en GDELT; conserva los ya vigilados."""
    alertas = leer("alertas.json", {}).get("paises", {})
    eventos = leer("eventos.json", {}).get("eventos", [])
    paises = sorted((a for a, p in alertas.items() if (p.get("conflicto") or 0) >= 5 and p.get("nivel") in ("rojo", "ambar")),
                    key=lambda a: -(alertas[a].get("conflicto") or 0))[:MAX_PAISES]
    paises += [a for a in FIJOS if a not in paises]
    hoy = AHORA.strftime("%Y-%m-%d")
    lugares = {}
    for e in eventos:
        # Solo lugares concretos ("Jartum, Khartoum, Sudan"); "Sudan" a secas es el centro del país
        # Ciudad concreta: "ciudad, región, país" (dos partes suele ser una región entera)
        partes = [x.strip() for x in (e.get("lugar") or "").split(",")]
        if e.get("tipo") != "conflicto" or e.get("pais") not in paises or len(partes) < 3 or "(general)" in partes[1]:
            continue
        clave = (e["pais"], e["lugar"].split(",")[0].strip())
        x = lugares.setdefault(clave, {"n": 0, "lat": e["lat"], "lon": e["lon"]})
        x["n"] += e.get("hechos", 1) or 1
    por_pais = {}
    for p in puntos.values():
        por_pais[p["pais"]] = por_pais.get(p["pais"], 0) + 1
    for (pais, lugar), x in sorted(lugares.items(), key=lambda kv: -kv[1]["n"]):
        ide = f"{pais}-{lugar}".lower().replace(" ", "-")
        if ide in puntos:
            puntos[ide]["visto"] = hoy
            continue
        if por_pais.get(pais, 0) >= PUNTOS_POR_PAIS:
            continue
        # no dos puntos a menos de 20 km en el mismo país
        if any(p["pais"] == pais and abs(p["lat"] - x["lat"]) < 0.2 and abs(p["lon"] - x["lon"]) < 0.2
               for p in puntos.values()):
            continue
        puntos[ide] = {"pais": pais, "lugar": lugar, "lat": round(x["lat"], 4), "lon": round(x["lon"], 4),
                       "alta": hoy, "visto": hoy, "base": {}}
        por_pais[pais] = por_pais.get(pais, 0) + 1
    corte = (AHORA - timedelta(days=DIAS_HISTORIAL)).strftime("%Y-%m-%d")
    return {k: v for k, v in puntos.items() if v.get("visto", "") >= corte}


def leer_valores(ruta, campo, calidad, puntos, condicion_calidad):
    """Media de la luz en el círculo de cada punto, con los píxeles de calidad alta."""
    import h5py
    import numpy as np
    salida = {}
    with h5py.File(ruta, "r") as h:
        g = h[CAMPOS]
        lat, lon = g["lat"][:], g["lon"][:]
        for ide, p in puntos:
            i = int(np.argmin(np.abs(lat - p["lat"])))
            j = int(np.argmin(np.abs(lon - p["lon"])))
            sl = (slice(max(i - RADIO, 0), i + RADIO + 1), slice(max(j - RADIO, 0), j + RADIO + 1))
            v = g[campo][sl].astype("float64")
            q = g[calidad][sl]
            ok = condicion_calidad(q) & (v >= 0)
            if "Snow_Flag" in g and campo.startswith("DNB"):
                ok &= g["Snow_Flag"][sl] == 0
            if ok.mean() >= MIN_VALIDOS:
                salida[ide] = round(float(v[ok].mean()), 2)
            elif DEPURAR:
                log(f"    {ide}: {ok.mean():.0%} válido; calidad {sorted(set(q.ravel().tolist()))[:6]}, luz {float(v.max()):.1f}")
    return salida


def principal():
    if not TOKEN:
        log("Sin EARTHDATA_TOKEN: no se miran las luces nocturnas.")
        return
    SALIDA.mkdir(parents=True, exist_ok=True)
    estado = leer("luces_estado.json", {})
    puntos = elegir_puntos(leer("luces_puntos.json", {}))
    historial = leer("luces_historial.json", {})
    dia, lista = ultimo_dia(DIARIO, AHORA.date() - timedelta(days=1))
    if not dia:
        log("Black Marble: no hay un día completo reciente.")
        return
    diatxt = dia.isoformat()
    tmp = SALIDA.parent / "tmp_luces"
    tmp.mkdir(exist_ok=True)

    # 1. Lo normal: compuesto mensual del mes anterior al del dato diario
    mes = (dia.replace(day=1) - timedelta(days=1)).replace(day=1)
    clave_mes = mes.strftime("%Y-%m")
    sin_base = [(k, p) for k, p in puntos.items() if clave_mes not in p.get("base", {})]
    if sin_base:
        mensual = ficheros_del_dia(MENSUAL, mes)
        log(f"Black Marble: {len(mensual)} baldosas mensuales de {clave_mes}")
        por_baldosa = {}
        for k, p in sin_base:
            por_baldosa.setdefault(baldosa(p["lat"], p["lon"]), []).append((k, p))
        for b, grupo in por_baldosa.items():
            if b not in mensual:
                log(f"  falta la baldosa mensual {b}")
                continue
            ruta = pedir(mensual[b], tmp / f"m_{b}.h5")
            if not ruta:
                continue
            valores = leer_valores(ruta, "AllAngle_Composite_Snow_Free", "AllAngle_Composite_Snow_Free_Quality",
                                   grupo, lambda q: q <= 1)
            ruta.unlink(missing_ok=True)
            for k, _ in grupo:
                puntos[k].setdefault("base", {})[clave_mes] = valores.get(k)
        log(f"Black Marble: línea base de {clave_mes} para {len(sin_base)} lugares")

    # 2. El dato diario (solo si es un día nuevo)
    if estado.get("dia") != diatxt:
        por_baldosa = {}
        for k, p in puntos.items():
            por_baldosa.setdefault(baldosa(p["lat"], p["lon"]), []).append((k, p))
        leidos = 0
        for b, grupo in por_baldosa.items():
            if b not in lista:
                continue
            ruta = pedir(lista[b], tmp / f"d_{b}.h5")
            if not ruta:
                continue
            valores = leer_valores(ruta, "DNB_BRDF-Corrected_NTL", "Mandatory_Quality_Flag", grupo, lambda q: q == 0)
            ruta.unlink(missing_ok=True)
            for k, v in valores.items():
                historial.setdefault(k, {})[diatxt] = v
                leidos += 1
        estado["dia"] = diatxt
        log(f"Black Marble: {diatxt}, {len(por_baldosa)} baldosas, {leidos} de {len(puntos)} lugares sin nubes")
    try:
        tmp.rmdir()
    except OSError:
        pass

    # 3. Comparar con lo normal
    corte = (dia - timedelta(days=DIAS_HISTORIAL)).isoformat()
    historial = {k: {d: v for d, v in s.items() if d >= corte} for k, s in historial.items() if k in puntos}
    eventos, paises, medidas = [], {}, {}
    for k, p in puntos.items():
        base = p.get("base", {}).get(clave_mes)
        obs = sorted(historial.get(k, {}).items())
        if base is None or base < MIN_BASE or not obs:
            continue
        ultima_fecha, ultimo = obs[-1]
        razon = ultimo / base
        medidas[k] = {"pais": p["pais"], "lugar": p["lugar"], "lat": p["lat"], "lon": p["lon"],
                      "fecha": ultima_fecha, "luz": ultimo, "normal": base, "razon": round(razon, 2),
                      "serie": [[d, round(v / base, 2)] for d, v in obs[-30:]]}
        recientes = [v / base for d, v in obs if d >= (date.fromisoformat(ultima_fecha) - timedelta(days=7)).isoformat()]
        if len(recientes) >= 2 and recientes[-1] <= CAIDA and recientes[-2] <= CAIDA + 0.1:
            paises[p["pais"]] = round(min(razon, paises.get(p["pais"], 1)), 2)
            eventos.append({
                "id": f"luces-{k}-{ultima_fecha}", "tipo": "apagon",
                "titulo": f"La luz nocturna de {p['lugar']} cae al {round(razon * 100)} % de lo normal",
                "lugar": p["lugar"], "pais": p["pais"], "lat": p["lat"], "lon": p["lon"],
                "fecha": f"{ultima_fecha}T02:00:00Z", "peso": 3 if razon <= CAIDA_GRAVE else 2, "nivel": "verde",
                "fuente": "NASA Black Marble", "familia": "tecnica",
                "url": "https://blackmarble.gsfc.nasa.gov/",
            })
    escribir("luces_puntos.json", puntos)
    escribir("luces_historial.json", historial)
    escribir("luces_estado.json", estado)
    escribir("luces.json", {"actualizado": AHORA.strftime("%Y-%m-%dT%H:%M:%SZ"), "dia": diatxt, "normal": clave_mes,
                            "eventos": eventos, "paises": paises, "lugares": medidas})
    log(f"Black Marble: {len(medidas)} lugares medidos, {len(eventos)} caídas fuertes")


if __name__ == "__main__":
    sys.exit(principal())
