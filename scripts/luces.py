#!/usr/bin/env python3
"""Luces nocturnas por satélite (NASA Black Marble, VIIRS NOAA-20).

Cada noche el satélite mide cuánta luz emite cada zona de la Tierra. Cuando una ciudad se
apaga de golpe —bombardeos a la red eléctrica, cortes de suministro, una ciudad que se vacía—
se ve desde el espacio, sin depender de lo que cuente la prensa.

Cómo se mide:
  - Se vigilan los lugares con más violencia en GDELT de los países en guerra o en alerta
    (hasta 3 por país), y se guardan para seguirlos aunque dejen de salir en las noticias.
  - Cada día se lee el producto diario VJ146A1 (satélite NOAA-20, con unos 2 días de retraso),
    en un cuadrado de 13 × 13 píxeles (unos 6 km de lado) alrededor de cada lugar. Los productos ya corregidos de luna y
    atmósfera (A2 y A3) hoy solo cubren una parte del planeta, así que se filtra a mano: solo
    cuentan los píxeles sin nubes, vistos casi desde arriba (menos de 60°) y con la luna baja
    o poco iluminada, que es cuando la luz de la ciudad se mide bien.
  - Lo normal es la mediana de las noches buenas de los 30 días anteriores en el mismo sitio.
    Al empezar a vigilar un lugar se rellenan sus días pasados poco a poco.
  - Hay aviso si la última noche buena cae a la mitad o menos de lo normal y la anterior también
    estaba al 60 % o menos: una sola noche puede ser una nube mal detectada.

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
DIARIO = "VJ146A1"
CAMPOS = "HDFEOS/GRIDS/VIIRS_Grid_DNB_2d/Data Fields/"

FIJOS = ("UKR", "RUS", "SDN", "PSE", "ISR", "MMR", "COD", "SYR", "YEM", "LBN", "SSD", "ETH")
MAX_PAISES = 20
PUNTOS_POR_PAIS = 3
RADIO = 6               # píxeles de 15" (~460 m) a cada lado: un cuadrado de 13 × 13, unos 6 km
MIN_VALIDOS = 0.4       # parte del círculo sin nubes para fiarse del dato
MIN_BASE = 8.0          # nW/cm²/sr: por debajo, el sitio es demasiado oscuro para juzgar
MIN_NOCHES = 6          # noches buenas para saber qué es lo normal
ATRAS = 30              # días que se miran hacia atrás
RELLENO_POR_EJECUCION = 3
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
                       "alta": hoy, "visto": hoy}
        por_pais[pais] = por_pais.get(pais, 0) + 1
    corte = (AHORA - timedelta(days=DIAS_HISTORIAL)).strftime("%Y-%m-%d")
    return {k: v for k, v in puntos.items() if v.get("visto", "") >= corte}


def mascara_buena(g, sl):
    """Píxeles medibles: sin nubes, buena calidad, vistos casi desde arriba y sin luna fuerte."""
    nubes = (g["QF_Cloud_Mask"][sl] >> 6) & 3          # 0 despejado seguro, 1 probablemente despejado
    calidad = g["QF_DNB"][sl] == 0
    cenit = g["Sensor_Zenith"][sl] * 0.01 < 60
    luna = (g["Moon_Illumination_Fraction"][sl] * 0.01 <= 50) | (g["Lunar_Zenith"][sl] * 0.01 >= 90)
    return (nubes <= 1) & calidad & cenit & luna


def leer_valores(ruta, puntos):
    """Media de la luz en el círculo de cada punto, solo con los píxeles medibles."""
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
            v = g["DNB_At_Sensor_Radiance"][sl].astype("float64")
            ok = mascara_buena(g, sl) & (v >= 0) & (v < 10000)
            if ok.mean() >= MIN_VALIDOS:
                salida[ide] = round(float(v[ok].mean()), 2)
            elif DEPURAR:
                log(f"    {ide}: {ok.mean():.0%} medible")
    return salida


def procesar_dia(dia, lista, puntos, historial, tmp):
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
        valores = leer_valores(ruta, grupo)
        ruta.unlink(missing_ok=True)
        for k, v in valores.items():
            historial.setdefault(k, {})[dia.isoformat()] = v
            leidos += 1
    log(f"Black Marble {dia}: {len(por_baldosa)} baldosas, {leidos} de {len(puntos)} lugares medibles")


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
    hechos = set(estado.get("dias", []))
    # 1. El día más reciente, si no se ha leído ya
    if diatxt not in hechos:
        procesar_dia(dia, lista, puntos, historial, tmp)
        hechos.add(diatxt)
    # 2. Rellenar días pasados para los lugares que aún no tienen bastantes noches buenas
    faltan = [k for k in puntos if len(historial.get(k, {})) < MIN_NOCHES * 2]
    if faltan:
        pendientes = [dia - timedelta(days=d) for d in range(1, ATRAS + 1)
                      if (dia - timedelta(days=d)).isoformat() not in hechos][:RELLENO_POR_EJECUCION]
        for d in pendientes:
            procesar_dia(d, ficheros_del_dia(DIARIO, d), {k: puntos[k] for k in faltan}, historial, tmp)
            hechos.add(d.isoformat())
    corte = (dia - timedelta(days=ATRAS + 5)).isoformat()
    estado["dias"] = sorted(x for x in hechos if x >= corte)
    try:
        tmp.rmdir()
    except OSError:
        pass

    # 3. Comparar con lo normal (mediana de las noches buenas anteriores, sin las dos últimas)
    import statistics
    corte = (dia - timedelta(days=DIAS_HISTORIAL)).isoformat()
    historial = {k: {d: v for d, v in s.items() if d >= corte} for k, s in historial.items() if k in puntos}
    eventos, paises, medidas = [], {}, {}
    for k, p in puntos.items():
        obs = sorted(historial.get(k, {}).items())
        if len(obs) < MIN_NOCHES + 2:
            continue
        ultima_fecha, ultimo = obs[-1]
        desde = (date.fromisoformat(ultima_fecha) - timedelta(days=ATRAS)).isoformat()
        previas = [v for d, v in obs[:-2] if d >= desde]
        if len(previas) < MIN_NOCHES:
            continue
        base = statistics.median(previas)
        if base < MIN_BASE:
            continue
        razon = ultimo / base
        penultima = obs[-2][1] / base
        medidas[k] = {"pais": p["pais"], "lugar": p["lugar"], "lat": p["lat"], "lon": p["lon"],
                      "fecha": ultima_fecha, "luz": ultimo, "normal": round(base, 2), "razon": round(razon, 2),
                      "serie": [[d, round(v / base, 2)] for d, v in obs[-30:]]}
        cerca = (date.fromisoformat(ultima_fecha) - date.fromisoformat(obs[-2][0])).days <= 7
        if razon <= CAIDA and penultima <= CAIDA + 0.1 and cerca:
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
    escribir("luces.json", {"actualizado": AHORA.strftime("%Y-%m-%dT%H:%M:%SZ"), "dia": diatxt,
                            "eventos": eventos, "paises": paises, "lugares": medidas})
    log(f"Black Marble: {len(medidas)} lugares medidos, {len(eventos)} caídas fuertes")


if __name__ == "__main__":
    sys.exit(principal())
