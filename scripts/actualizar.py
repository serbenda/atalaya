#!/usr/bin/env python3
"""Descarga los datos de las fuentes públicas, los normaliza y calcula el nivel
de alerta de cada país. Solo usa la biblioteca estándar de Python.

Genera:
  data/eventos.json    eventos geolocalizados + titulares
  data/alertas.json    nivel de alerta por país
  data/historial.json  puntuación diaria por país (últimos 30 días)
"""

import html
import json
import math
import re
import statistics
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DATOS = RAIZ / "data"
AHORA = datetime.now(timezone.utc)
VENTANA_PUNTUACION = timedelta(hours=48)   # qué cuenta para el nivel de hoy
VENTANA_MAPA = timedelta(days=7)           # qué se pinta en el mapa
DIAS_HISTORIAL = 30
DIAS_CALIBRADO = 7                         # días de historial antes de fiarse de la anomalía

USGS_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_week.geojson"
GDACS_URL = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/MAP"
EONET_URL = "https://eonet.gsfc.nasa.gov/api/v3/events?status=open&days=7"
GDELT_TERMINOS = ('(airstrike OR shelling OR missile OR bombing OR clashes OR '
                  '"armed conflict" OR insurgents OR coup OR militants OR "military offensive")')
GDELT_GEO_URL = "https://api.gdeltproject.org/api/v2/geo/geo?" + urllib.parse.urlencode({
    "query": GDELT_TERMINOS, "format": "GeoJSON", "timespan": "24h", "maxpoints": "500"})
GDELT_DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc?" + urllib.parse.urlencode({
    "query": GDELT_TERMINOS + " sourcelang:spanish", "mode": "artlist", "format": "json",
    "maxrecords": "60", "timespan": "24h", "sort": "hybridrel"})


# ---------------------------------------------------------------- utilidades

def log(*a):
    print(*a, file=sys.stderr, flush=True)


def descargar(url, intentos=3, espera=6):
    req = urllib.request.Request(url, headers={"User-Agent": "atalaya/1.0 (+https://github.com/serbenda/atalaya)"})
    for i in range(intentos):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception as e:  # noqa: BLE001
            log(f"  fallo {i + 1}/{intentos} en {url[:80]}: {e}")
            time.sleep(espera * (i + 1))
    return None


def leer(nombre, defecto):
    try:
        return json.loads((DATOS / nombre).read_text("utf-8"))
    except (OSError, ValueError):
        return defecto


def escribir(nombre, datos):
    (DATOS / nombre).write_text(json.dumps(datos, ensure_ascii=False, separators=(",", ":")), "utf-8")


def normalizar(texto):
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fecha(texto):
    """Convierte las distintas fechas de las fuentes a datetime UTC."""
    if texto is None:
        return None
    if isinstance(texto, (int, float)):
        return datetime.fromtimestamp(texto / 1000, timezone.utc)
    t = str(texto).strip()
    for fmt in ("%Y%m%dT%H%M%SZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%fZ"):
        try:
            return datetime.strptime(t, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


# ------------------------------------------------------------------- países

# Lugares que GDELT etiqueta con el país vecino ("Gaza, Israel (general), Israel")
TERRITORIOS = {"gaza": "PSE", "gaza strip": "PSE", "west bank": "PSE", "ramallah": "PSE",
               "khan yunis": "PSE", "rafah": "PSE", "jenin": "PSE", "nablus": "PSE"}

class Paises:
    """Asigna un país (ISO alfa-3) por nombre o por coordenadas."""

    def __init__(self):
        lista = json.loads((DATOS / "paises.json").read_text("utf-8"))
        self.por_nombre = {}
        for p in lista:
            for n in p["nombres"]:
                self.por_nombre[normalizar(n)] = p["a3"]
        self.formas = []  # (a3, bbox, [anillos])
        mundo = json.loads((DATOS / "mundo.geojson").read_text("utf-8"))
        for f in mundo["features"]:
            g = f["geometry"]
            poligonos = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
            for anillos in poligonos:
                xs = [p[0] for p in anillos[0]]
                ys = [p[1] for p in anillos[0]]
                self.formas.append((f["id"], (min(xs), min(ys), max(xs), max(ys)), anillos))
        log(f"  {len(self.formas)} polígonos de países")

    def nombre(self, texto):
        if not texto:
            return None
        partes = [normalizar(x) for x in re.split(r"[,;]| - ", texto)]
        if any(x in TERRITORIOS for x in partes):
            return TERRITORIOS[next(x for x in partes if x in TERRITORIOS)]
        n = normalizar(texto)
        if n in self.por_nombre:
            return self.por_nombre[n]
        # "Kharkiv, Kharkiv, Ukraine" o "45 km SW of Ovalle, Chile": la última parte es el país
        for parte in reversed(re.split(r"[,;]| - ", texto)):
            n = normalizar(parte)
            if n in self.por_nombre:
                return self.por_nombre[n]
        return None

    @staticmethod
    def _dentro(x, y, anillo):
        dentro = False
        j = len(anillo) - 1
        for i in range(len(anillo)):
            xi, yi = anillo[i]
            xj, yj = anillo[j]
            if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                dentro = not dentro
            j = i
        return dentro

    def punto(self, lon, lat):
        for a3, (x0, y0, x1, y1), anillos in self.formas:
            if x0 <= lon <= x1 and y0 <= lat <= y1 and self._dentro(lon, lat, anillos[0]):
                if not any(self._dentro(lon, lat, h) for h in anillos[1:]):
                    return a3
        return None

    def asignar(self, nombre, lon, lat):
        # Primero las coordenadas; el nombre sirve para puntos en la costa o en el mar
        return self.punto(lon, lat) or self.nombre(nombre)


# ------------------------------------------------------------------ fuentes

RANGO = {"verde": 0, "ambar": 1, "rojo": 2}


def nivel_por_peso(peso):
    return "rojo" if peso >= 12 else "ambar" if peso >= 4 else "verde"


def usgs(paises):
    datos = descargar(USGS_URL)
    if datos is None:
        return None
    eventos = []
    for f in datos.get("features", []):
        p = f["properties"]
        lon, lat = f["geometry"]["coordinates"][:2]
        mag = p.get("mag") or 0
        peso = max(mag - 4, 0) ** 2
        peso += {"yellow": 3, "orange": 10, "red": 25}.get(p.get("alert"), 0)
        eventos.append({
            "id": "usgs-" + f["id"], "tipo": "terremoto", "titulo": f"Terremoto de magnitud {mag:.1f}",
            "lugar": p.get("place") or "", "pais": paises.asignar(p.get("place"), lon, lat),
            "lat": round(lat, 3), "lon": round(lon, 3), "fecha": iso(fecha(p["time"])),
            "peso": round(peso, 2), "nivel": nivel_por_peso(peso), "magnitud": mag,
            "fuente": "USGS", "url": p.get("url"),
        })
    return eventos


GDACS_TIPOS = {"TC": "Ciclón tropical", "FL": "Inundación", "VO": "Erupción volcánica",
               "DR": "Sequía", "WF": "Incendio forestal", "TS": "Tsunami"}


def gdacs(paises):
    datos = descargar(GDACS_URL)
    if datos is None:
        return None
    eventos = []
    for f in datos.get("features", []):
        p = f.get("properties", {})
        tipo = p.get("eventtype")
        # Los terremotos ya vienen de USGS; GDACS también trae polígonos, solo queremos el punto
        if tipo == "EQ" or tipo not in GDACS_TIPOS or (f.get("geometry") or {}).get("type") != "Point":
            continue
        lon, lat = f["geometry"]["coordinates"][:2]
        alerta = (p.get("alertlevel") or "Green").lower()
        peso = {"green": 1, "orange": 6, "red": 15}.get(alerta, 1)
        url = p.get("url") or {}
        eventos.append({
            "id": f"gdacs-{tipo}-{p.get('eventid')}", "tipo": "desastre",
            "titulo": GDACS_TIPOS[tipo] + (f" {p['name']}" if p.get("name") and tipo == "TC" else ""),
            "lugar": p.get("country") or p.get("name") or "",
            "pais": (p.get("iso3") or "").upper() or paises.asignar(p.get("country"), lon, lat),
            "lat": round(lat, 3), "lon": round(lon, 3),
            "fecha": iso(fecha(p.get("todate")) or fecha(p.get("fromdate")) or AHORA),
            "peso": peso, "nivel": {"green": "verde", "orange": "ambar", "red": "rojo"}.get(alerta, "verde"),
            "fuente": "GDACS", "url": url.get("report") if isinstance(url, dict) else None,
        })
    return eventos


EONET_TIPOS = {"wildfires": ("Incendio", 0.5), "severeStorms": ("Tormenta severa", 2),
               "volcanoes": ("Volcán activo", 2), "floods": ("Inundación", 2),
               "landslides": ("Deslizamiento de tierra", 2), "dustHaze": ("Polvo o calima", 0.5),
               "drought": ("Sequía", 1), "earthquakes": None, "seaLakeIce": None, "snow": ("Nevada", 0.5)}


def eonet(paises):
    datos = descargar(EONET_URL)
    if datos is None:
        return None
    eventos = []
    for e in datos.get("events", []):
        cat = (e.get("categories") or [{}])[0].get("id")
        info = EONET_TIPOS.get(cat, ("Fenómeno natural", 1))
        geos = [g for g in e.get("geometry", []) if g.get("type") == "Point"]
        if not info or not geos:
            continue
        g = geos[-1]
        lon, lat = g["coordinates"][:2]
        eventos.append({
            "id": "eonet-" + e["id"], "tipo": "desastre", "titulo": info[0],
            "lugar": e.get("title") or "", "pais": paises.asignar(None, lon, lat),
            "lat": round(lat, 3), "lon": round(lon, 3), "fecha": iso(fecha(g.get("date")) or AHORA),
            "peso": info[1], "nivel": "verde", "fuente": "NASA EONET",
            "url": ((e.get("sources") or [{}])[0]).get("url") or e.get("link"),
        })
    return eventos


def gdelt_geo(paises):
    datos = descargar(GDELT_GEO_URL)
    if datos is None:
        return None
    eventos = []
    for f in datos.get("features", []):
        p = f.get("properties", {})
        if (f.get("geometry") or {}).get("type") != "Point":
            continue
        lon, lat = f["geometry"]["coordinates"][:2]
        nombre = p.get("name") or ""
        menciones = int(p.get("count") or 1)
        enlaces = re.findall(r'<a href="([^"]+)"[^>]*title="([^"]*)"', p.get("html") or "")
        eventos.append({
            "id": "gdelt-" + normalizar(nombre).replace(" ", "-")[:60], "tipo": "conflicto",
            "titulo": f"{menciones} noticia{'s' if menciones != 1 else ''} sobre violencia o conflicto",
            "lugar": nombre, "pais": paises.asignar(nombre, lon, lat),
            "lat": round(lat, 3), "lon": round(lon, 3), "fecha": iso(AHORA),
            "menciones": menciones, "peso": 0, "nivel": "verde", "fuente": "GDELT",
            "url": enlaces[0][0] if enlaces else None,
            "enlaces": [{"url": u, "titulo": html.unescape(t)} for u, t in enlaces[:3]],
        })
    return eventos


def gdelt_titulares():
    datos = descargar(GDELT_DOC_URL)
    if datos is None:
        return None
    vistos, titulares = set(), []
    for a in datos.get("articles", []):
        clave = normalizar(a.get("title"))[:70]
        if not clave or clave in vistos:
            continue
        vistos.add(clave)
        titulares.append({"titulo": a.get("title", "").strip(), "url": a.get("url"),
                          "medio": a.get("domain"), "fecha": iso(fecha(a.get("seendate")) or AHORA)})
    return titulares[:40]


# ----------------------------------------------------------------- alertas

def puntuar(eventos):
    """Puntuación de cada país con lo ocurrido en las últimas 48 h."""
    limite = AHORA - VENTANA_PUNTUACION
    comp = {}
    for e in eventos:
        if not e.get("pais") or (fecha(e["fecha"]) or AHORA) < limite:
            continue
        c = comp.setdefault(e["pais"], {"desastres": 0.0, "menciones": 0, "eventos": 0, "rango": 0})
        c["eventos"] += 1
        c["rango"] = max(c["rango"], RANGO[e["nivel"]])
        if e["tipo"] == "conflicto":
            c["menciones"] += e.get("menciones", 0)
        else:
            c["desastres"] += e["peso"]
    resultado = {}
    for a3, c in comp.items():
        conflicto = 3 * math.log2(1 + c["menciones"])
        resultado[a3] = {"desastres": round(c["desastres"], 1), "conflicto": round(conflicto, 1),
                         "puntuacion": round(c["desastres"] + conflicto, 1), "eventos": c["eventos"],
                         "rango_evento": c["rango"]}
    return resultado


def calcular_alertas(puntos, historial):
    hoy = AHORA.strftime("%Y-%m-%d")
    previos = sorted(d for d in historial if d < hoy)[-DIAS_HISTORIAL:]
    calibrando = len(previos) < DIAS_CALIBRADO
    paises = {}
    for a3 in set(puntos) | {a for d in previos for a in historial[d]}:
        actual = puntos.get(a3, {}).get("puntuacion", 0)
        serie = [historial[d].get(a3, 0) for d in previos]
        media = statistics.fmean(serie) if serie else 0
        desv = statistics.pstdev(serie) if len(serie) > 1 else 0
        # z: cuántas desviaciones por encima de lo normal está hoy (con suelo para no exagerar el ruido)
        z = (actual - media) / max(desv, 2, 0.25 * media) if serie else 0
        # Un evento oficial en ámbar o rojo (GDACS, USGS) fija el nivel mínimo del país
        rango_evento = puntos.get(a3, {}).get("rango_evento", 0)
        if actual >= 35 or rango_evento == 2 or (not calibrando and z >= 3 and actual >= 15):
            nivel = "rojo"
        elif actual >= 18 or rango_evento == 1 or (not calibrando and z >= 1.5 and actual >= 8):
            nivel = "ambar"
        elif actual > 0:
            nivel = "verde"
        else:
            continue
        tendencia = "sube" if z >= 1 else "baja" if z <= -1 else "estable"
        paises[a3] = {"nivel": nivel, "puntuacion": actual, "media": round(media, 1), "z": round(z, 2),
                      "tendencia": tendencia if serie else "sin datos",
                      **{k: v for k, v in puntos.get(a3, {}).items() if k not in ("puntuacion", "rango_evento")}}
    return {"actualizado": iso(AHORA), "calibrando": calibrando, "dias_historial": len(previos), "paises": paises}


# --------------------------------------------------------------------- main

def main():
    DATOS.mkdir(exist_ok=True)
    anterior = leer("eventos.json", {"eventos": [], "titulares": []})
    log("Cargando países…")
    paises = Paises()

    fuentes = [("USGS", usgs), ("GDACS", gdacs), ("NASA EONET", eonet), ("GDELT", gdelt_geo)]
    eventos, estado = [], {}
    for nombre, funcion in fuentes:
        log(f"Descargando {nombre}…")
        nuevos = funcion(paises)
        if nuevos is None:  # si una fuente cae, se conservan sus últimos datos
            nuevos = [e for e in anterior["eventos"] if e.get("fuente") == nombre]
            estado[nombre] = {"ok": False, "eventos": len(nuevos)}
        else:
            estado[nombre] = {"ok": True, "eventos": len(nuevos)}
        eventos.extend(nuevos)

    time.sleep(6)  # GDELT pide no más de una petición cada 5 s
    titulares = gdelt_titulares()
    estado["GDELT titulares"] = {"ok": titulares is not None, "eventos": len(titulares or [])}
    if titulares is None:
        titulares = anterior.get("titulares", [])

    limite = AHORA - VENTANA_MAPA
    eventos = [e for e in eventos if (fecha(e["fecha"]) or AHORA) >= limite]
    eventos.sort(key=lambda e: e["fecha"], reverse=True)

    puntos = puntuar(eventos)
    historial = leer("historial.json", {})
    hoy = AHORA.strftime("%Y-%m-%d")
    dia = historial.setdefault(hoy, {})
    for a3, p in puntos.items():
        dia[a3] = max(dia.get(a3, 0), p["puntuacion"])
    historial = {d: historial[d] for d in sorted(historial)[-(DIAS_HISTORIAL + 1):]}

    escribir("eventos.json", {"actualizado": iso(AHORA), "fuentes": estado, "eventos": eventos, "titulares": titulares})
    escribir("alertas.json", calcular_alertas(puntos, historial))
    escribir("historial.json", historial)
    log("Listo:", {k: v["eventos"] for k, v in estado.items()})
    if not any(v["ok"] for v in estado.values()):
        sys.exit("Ninguna fuente respondió")


if __name__ == "__main__":
    main()
