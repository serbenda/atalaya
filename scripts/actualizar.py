#!/usr/bin/env python3
"""Descarga los datos de las fuentes públicas, los normaliza y calcula el nivel
de alerta de cada país. Solo usa la biblioteca estándar de Python.

El modelo separa dos cosas, como hacen los equipos de alerta temprana:
  - gravedad: lo mal que está un país (incluidas las crisis prolongadas)
  - escalada: si está empeorando respecto a lo que es normal para él
y añade una confianza según cuántos tipos de fuente independientes coinciden.

Lee de data/ (fijos, en main):
  paises.json, mundo.geojson
Escribe en $ATALAYA_SALIDA (por defecto data/; en la Action, la rama `datos`):
  eventos.json    eventos geolocalizados, titulares y estado de cada fuente
  alertas.json    nivel de alerta por país, pasos marítimos y parte de situación
  historial.json  puntuación diaria por país (últimos 30 días)
  avisos.json     último nivel de los avisos de viaje y sus cambios
"""

import csv
import io
import json
import math
import os
import re
import statistics
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FIJOS = RAIZ / "data"
SALIDA = Path(os.environ.get("ATALAYA_SALIDA") or FIJOS)
AHORA = datetime.now(timezone.utc)
HOY = AHORA.strftime("%Y-%m-%d")
VENTANA_PUNTUACION = timedelta(hours=48)   # qué cuenta para el nivel de hoy
VENTANA_MAPA = timedelta(days=7)           # qué se pinta en el mapa
VENTANA_EPIDEMIAS = timedelta(days=30)     # los brotes evolucionan despacio
DIAS_HISTORIAL = 30
DIAS_CALIBRADO = 7                         # días de historial antes de fiarse de la anomalía
FALLOS_PARA_AVISAR = 6                     # ejecuciones seguidas (3 h) antes de abrir un issue

USGS_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_week.geojson"
GDACS_URLS = ["https://www.gdacs.org/xml/rss_7d.xml", "https://www.gdacs.org/xml/rss.xml"]
EONET_URL = "https://eonet.gsfc.nasa.gov/api/v3/events?status=open&days=7"
GDELT_ULTIMO_URL = "http://data.gdeltproject.org/gdeltv2/lastupdate.txt"
GDELT_FICHERO_URL = "http://data.gdeltproject.org/gdeltv2/{}.export.CSV.zip"
GDELT_FICHEROS = 96                        # 24 h de ficheros de 15 minutos
TITULARES_URL = "https://news.google.com/rss/search?" + urllib.parse.urlencode({
    "q": '(bombardeo OR ataque OR ofensiva OR enfrentamientos OR "golpe de Estado" OR evacuación OR terremoto) when:1d',
    "hl": "es", "gl": "ES", "ceid": "ES:es"})
IODA_URL = "https://api.ioda.inetintel.cc.gatech.edu/v2/outages/summary?" + urllib.parse.urlencode({
    "from": int((AHORA - timedelta(hours=24)).timestamp()), "until": int(AHORA.timestamp()), "entityType": "country"})
AVISOS_URL = "https://travel.state.gov/_res/rss/TAsTWs.xml"
OMS_URL = "https://www.who.int/api/news/diseaseoutbreaknews?" + urllib.parse.urlencode(
    {"$orderby": "PublicationDateAndTime desc", "$top": "30"})
RELIEFWEB_APPNAME = os.environ.get("RELIEFWEB_APPNAME", "").strip()
RELIEFWEB_URL = "https://api.reliefweb.int/v2/disasters?" + urllib.parse.urlencode([
    ("appname", RELIEFWEB_APPNAME), ("limit", "200"), ("preset", "latest"),
    ("filter[field]", "status"), ("filter[value][]", "alert"), ("filter[value][]", "current"),
    ("fields[include][]", "name"), ("fields[include][]", "status"), ("fields[include][]", "country.iso3"),
    ("fields[include][]", "primary_type.name"), ("fields[include][]", "date.created"), ("fields[include][]", "url")])

# Pasos marítimos por los que pasa buena parte de la energía y el comercio que llega a Europa
PASOS = [
    {"id": "ormuz", "nombre": "Estrecho de Ormuz", "lon": 56.4, "lat": 26.6,
     "porque": "Salida del petróleo y el gas del golfo Pérsico"},
    {"id": "bab", "nombre": "Bab el-Mandeb", "lon": 43.4, "lat": 12.6,
     "porque": "Entrada al mar Rojo y al canal de Suez desde Asia"},
    {"id": "suez", "nombre": "Canal de Suez", "lon": 32.35, "lat": 30.6,
     "porque": "Ruta más corta entre Asia y Europa"},
    {"id": "bosforo", "nombre": "Bósforo", "lon": 29.05, "lat": 41.1,
     "porque": "Salida del mar Negro: cereal, petróleo y gas"},
    {"id": "gibraltar", "nombre": "Estrecho de Gibraltar", "lon": -5.6, "lat": 35.95,
     "porque": "Entrada al Mediterráneo, junto a España"},
    {"id": "malaca", "nombre": "Estrecho de Malaca", "lon": 100.4, "lat": 3.0,
     "porque": "Principal ruta entre el Índico y el Pacífico"},
    {"id": "taiwan", "nombre": "Estrecho de Taiwán", "lon": 119.5, "lat": 24.0,
     "porque": "Ruta de los semiconductores y del comercio de Asia oriental"},
    {"id": "panama", "nombre": "Canal de Panamá", "lon": -79.7, "lat": 9.1,
     "porque": "Paso entre el Atlántico y el Pacífico"},
]
RADIO_PASO_KM = 350


class FormatoInesperado(Exception):
    """La fuente respondió, pero no con la forma que esperamos."""


# ---------------------------------------------------------------- utilidades

def log(*a):
    print(*a, file=sys.stderr, flush=True)


def descargar(url, como="json", intentos=3, espera=6):
    """Devuelve el contenido o None si la fuente no responde tras varios intentos."""
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; atalaya/1.0; +https://github.com/serbenda/atalaya)"})
    for i in range(intentos):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                cuerpo = r.read()
            if como == "bytes":
                return cuerpo
            texto = cuerpo.decode("utf-8", "replace")
            if como == "texto":
                return texto
            return json.loads(texto) if texto.strip() else {}
        except urllib.error.HTTPError as e:
            log(f"  fallo {i + 1}/{intentos} en {url[:90]}: {e}")
            if e.code == 404 and como == "bytes":
                return None  # un fichero de GDELT que no existe: no merece reintentos
        except Exception as e:  # noqa: BLE001
            log(f"  fallo {i + 1}/{intentos} en {url[:90]}: {e}")
        if i + 1 < intentos:
            time.sleep(espera * (i + 1))
    return None


def leer(nombre, defecto):
    try:
        return json.loads((SALIDA / nombre).read_text("utf-8"))
    except (OSError, ValueError):
        return defecto


def escribir(nombre, datos):
    (SALIDA / nombre).write_text(json.dumps(datos, ensure_ascii=False, separators=(",", ":")), "utf-8")


def normalizar(texto):
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fecha(texto):
    """Convierte las distintas fechas de las fuentes a datetime UTC."""
    if texto is None or texto == "":
        return None
    if isinstance(texto, (int, float)):
        return datetime.fromtimestamp(texto / 1000, timezone.utc)
    t = str(texto).strip()
    for fmt in ("%Y%m%dT%H%M%SZ", "%Y%m%d%H%M%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
        try:
            d = datetime.strptime(t, fmt)
            return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(t.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(t).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def reciente(e, ventana):
    return (fecha(e.get("fecha")) or AHORA) >= AHORA - ventana


def xml_items(texto, origen):
    """Elementos <item> de un RSS, con las etiquetas sin espacio de nombres."""
    try:
        raiz = ET.fromstring(texto)
    except ET.ParseError as e:
        raise FormatoInesperado(f"{origen}: no es XML válido ({e})") from e
    items = []
    for it in raiz.iter():
        if it.tag.split("}")[-1] != "item":
            continue
        campos = {}
        for hijo in it.iter():
            nombre = hijo.tag.split("}")[-1]
            if hijo is not it and nombre not in campos:
                campos[nombre] = (hijo.text or "").strip()
                campos.update({f"{nombre}@{k.split('}')[-1]}": v for k, v in hijo.attrib.items()})
        items.append(campos)
    return items


def distancia_km(lon1, lat1, lon2, lat2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 12742 * math.asin(math.sqrt(a))


# ------------------------------------------------------------------- países

# Lugares que las fuentes etiquetan con el país vecino ("Gaza, Israel (general), Israel")
TERRITORIOS = {"gaza": "PSE", "gaza strip": "PSE", "west bank": "PSE", "ramallah": "PSE",
               "khan yunis": "PSE", "rafah": "PSE", "jenin": "PSE", "nablus": "PSE"}


class Paises:
    """Asigna un país (ISO alfa-3) por nombre o por coordenadas."""

    def __init__(self):
        lista = json.loads((FIJOS / "paises.json").read_text("utf-8"))
        self.por_nombre, self.por_a2 = {}, {}
        for p in lista:
            for n in p["nombres"]:
                self.por_nombre[normalizar(n)] = p["a3"]
            if p["a2"]:
                self.por_a2[p["a2"]] = p["a3"]
        self.formas = []   # (a3, bbox, [anillos])
        self.centros = {}  # a3 → (lon, lat) del polígono más grande
        mayor = {}
        mundo = json.loads((FIJOS / "mundo.geojson").read_text("utf-8"))
        for f in mundo["features"]:
            g = f["geometry"]
            poligonos = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
            for anillos in poligonos:
                xs = [p[0] for p in anillos[0]]
                ys = [p[1] for p in anillos[0]]
                caja = (min(xs), min(ys), max(xs), max(ys))
                self.formas.append((f["id"], caja, anillos))
                area = (caja[2] - caja[0]) * (caja[3] - caja[1])
                if area > mayor.get(f["id"], -1):
                    mayor[f["id"]] = area
                    self.centros[f["id"]] = (round(sum(xs) / len(xs), 2), round(sum(ys) / len(ys), 2))
        self._cache = {}

    def nombre(self, texto):
        if not texto:
            return None
        partes = [normalizar(x) for x in re.split(r"[,;]| - | – ", texto)]
        for x in partes:
            if x in TERRITORIOS:
                return TERRITORIOS[x]
        n = normalizar(texto)
        if n in self.por_nombre:
            return self.por_nombre[n]
        # "Kharkiv, Kharkiv, Ukraine" o "45 km SW of Ovalle, Chile": la última parte es el país
        for x in reversed(partes):
            if x in self.por_nombre:
                return self.por_nombre[x]
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
        clave = (round(lon, 2), round(lat, 2))
        if clave not in self._cache:
            self._cache[clave] = None
            for a3, (x0, y0, x1, y1), anillos in self.formas:
                if x0 <= lon <= x1 and y0 <= lat <= y1 and self._dentro(lon, lat, anillos[0]):
                    if not any(self._dentro(lon, lat, h) for h in anillos[1:]):
                        self._cache[clave] = a3
                        break
        return self._cache[clave]

    def asignar(self, nombre, lon, lat):
        # Los territorios mal etiquetados mandan; después las coordenadas y, si caen en el mar, el nombre
        for x in (normalizar(x) for x in re.split(r"[,;]| - ", nombre or "")):
            if x in TERRITORIOS:
                return TERRITORIOS[x]
        return self.punto(lon, lat) or self.nombre(nombre)

    def centro(self, a3):
        return self.centros.get(a3, (0.0, 0.0))


# ------------------------------------------------------------------ fuentes
# Cada fuente devuelve un dict con "eventos" (y opcionalmente otros datos agregados),
# None si no responde, o lanza FormatoInesperado si responde con otra forma.
# Cada evento lleva una "familia" de fuente para calcular la confianza:
#   prensa (GDELT), oficial (USGS, GDACS, EONET, avisos), tecnica (IODA),
#   sanitaria (OMS) y humanitaria (ReliefWeb).

RANGO = {"verde": 0, "ambar": 1, "rojo": 2}


def nivel_por_peso(peso):
    return "rojo" if peso >= 12 else "ambar" if peso >= 4 else "verde"


def exigir(condicion, mensaje):
    if not condicion:
        raise FormatoInesperado(mensaje)


def usgs(paises):
    datos = descargar(USGS_URL)
    if datos is None:
        return None
    exigir(isinstance(datos.get("features"), list), "no trae 'features'")
    eventos = []
    for f in datos["features"]:
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
            "fuente": "USGS", "familia": "oficial", "url": p.get("url"),
        })
    return {"eventos": eventos}


GDACS_TIPOS = {"TC": "Ciclón tropical", "FL": "Inundación", "VO": "Erupción volcánica",
               "DR": "Sequía", "WF": "Incendio forestal", "TS": "Tsunami"}


def gdacs(paises):
    """Alertas de desastres de GDACS (ONU y Comisión Europea), desde su RSS."""
    texto = None
    for url in GDACS_URLS:
        texto = descargar(url, como="texto", intentos=2)
        if texto:
            break
    if texto is None:
        return None
    items = xml_items(texto, "GDACS")
    exigir(items == [] or any("eventtype" in i for i in items), "el RSS no trae 'eventtype'")
    eventos, vistos = [], set()
    for it in items:
        tipo = it.get("eventtype")
        if tipo not in GDACS_TIPOS:  # los terremotos ya vienen de USGS
            continue
        clave = f"gdacs-{tipo}-{it.get('eventid')}"
        if clave in vistos:
            continue
        vistos.add(clave)
        try:
            lat, lon = float(it.get("lat")), float(it.get("long"))
        except (TypeError, ValueError):
            continue
        alerta = (it.get("alertlevel") or "Green").lower()
        peso = {"green": 1, "orange": 6, "red": 15}.get(alerta, 1)
        nombre = it.get("eventname") or ""
        iso3 = (it.get("iso3") or "").upper()[:3]
        eventos.append({
            "id": clave, "tipo": "desastre",
            "titulo": GDACS_TIPOS[tipo] + (f" {nombre.title()}" if nombre and tipo == "TC" else ""),
            "lugar": it.get("country") or "", "pais": iso3 if len(iso3) == 3 else paises.asignar(it.get("country"), lon, lat),
            "lat": round(lat, 3), "lon": round(lon, 3),
            "fecha": iso(fecha(it.get("todate")) or fecha(it.get("fromdate")) or fecha(it.get("pubDate")) or AHORA),
            "peso": peso, "nivel": {"green": "verde", "orange": "ambar", "red": "rojo"}.get(alerta, "verde"),
            "fuente": "GDACS", "familia": "oficial", "url": it.get("link"),
        })
    return {"eventos": eventos}


EONET_TIPOS = {"wildfires": ("Incendio", 0.5), "severeStorms": ("Tormenta severa", 2),
               "volcanoes": ("Volcán activo", 2), "floods": ("Inundación", 2),
               "landslides": ("Deslizamiento de tierra", 2), "dustHaze": ("Polvo o calima", 0.5),
               "drought": ("Sequía", 1), "earthquakes": None, "seaLakeIce": None, "snow": ("Nevada", 0.5)}


def eonet(paises):
    datos = descargar(EONET_URL)
    if datos is None:
        return None
    exigir(isinstance(datos.get("events"), list), "no trae 'events'")
    eventos = []
    for e in datos["events"]:
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
            "peso": info[1], "nivel": "verde", "fuente": "NASA EONET", "familia": "oficial",
            "url": ((e.get("sources") or [{}])[0]).get("url") or e.get("link"),
        })
    return {"eventos": eventos}


# Columnas del fichero de eventos de GDELT 2.0 (61 columnas separadas por tabuladores)
G_A1_GRUPO, G_A1_TIPOS = 8, (12, 13, 14)
G_A2_GRUPO, G_A2_TIPOS = 18, (22, 23, 24)
G_RAIZ_EVENTO, G_RAIZ, G_FUENTES, G_ARTICULOS = 25, 28, 32, 33
G_GEO_TIPO, G_GEO_NOMBRE, G_GEO_LAT, G_GEO_LON, G_FECHA, G_URL = 51, 52, 56, 57, 59, 60
# Códigos CAMEO raíz: 14 protestas; 18 agresiones, 19 combates, 20 violencia masiva
GDELT_VIOLENCIA = {"18", "19", "20"}
GDELT_PROTESTA = {"14"}
# Tipos de actor que hacen que la violencia sea política y no delincuencia común:
# ejército, rebeldes, insurgentes, separatistas, fuerzas armadas no estatales, gobierno,
# policía, inteligencia y oposición
ACTORES_POLITICOS = {"MIL", "REB", "INS", "SEP", "UAF", "GOV", "COP", "SPY", "OPP"}


def es_politico(f):
    tipos = {f[i] for i in G_A1_TIPOS + G_A2_TIPOS}
    return bool(tipos & ACTORES_POLITICOS) or bool(f[G_A1_GRUPO] or f[G_A2_GRUPO])


def gdelt_ficheros():
    """Nombres (marcas de tiempo) de los ficheros de las últimas 24 h."""
    ultimo = descargar(GDELT_ULTIMO_URL, como="texto")
    if ultimo is None:
        return None
    marca = re.search(r"/(\d{14})\.export\.CSV\.zip", ultimo)
    exigir(marca, "lastupdate.txt no tiene la forma esperada")
    t = datetime.strptime(marca.group(1), "%Y%m%d%H%M%S")
    return [(t - timedelta(minutes=15 * i)).strftime("%Y%m%d%H%M%S") for i in range(GDELT_FICHEROS)]


def gdelt_filas(marca):
    contenido = descargar(GDELT_FICHERO_URL.format(marca), como="bytes", intentos=2, espera=3)
    if not contenido:
        return []
    with zipfile.ZipFile(io.BytesIO(contenido)) as z:
        texto = z.read(z.namelist()[0]).decode("utf-8", "replace")
    return list(csv.reader(io.StringIO(texto), delimiter="\t", quoting=csv.QUOTE_NONE))


def gdelt(paises, filas=None):
    """Agrega los hechos de GDELT de las últimas 24 h por lugar, por país y cerca de los pasos marítimos."""
    if filas is None:
        marcas = gdelt_ficheros()
        if marcas is None:
            return None
        with ThreadPoolExecutor(max_workers=8) as hilos:
            bloques = list(hilos.map(gdelt_filas, marcas))
        exigir(sum(1 for b in bloques if b) >= len(marcas) // 2, "faltan más de la mitad de los ficheros")
        filas = [f for b in bloques for f in b]
    exigir(filas and len(filas[0]) >= 61, "los ficheros no tienen 61 columnas")

    lugares, por_pais = {}, {}
    pasos = {p["id"]: 0 for p in PASOS}
    for f in filas:
        if len(f) < 61 or not f[G_GEO_LAT] or not f[G_GEO_LON]:
            continue
        try:
            lat, lon = float(f[G_GEO_LAT]), float(f[G_GEO_LON])
            articulos = int(f[G_ARTICULOS] or 1)
        except ValueError:
            continue
        pais = paises.asignar(f[G_GEO_NOMBRE], lon, lat)
        raiz = f[G_RAIZ]
        tipo = None
        # Solo el hecho principal de cada noticia: las menciones de pasada a ataques antiguos meten mucho ruido
        if f[G_RAIZ_EVENTO] == "1":
            if raiz in GDELT_VIOLENCIA and es_politico(f):
                tipo = "conflicto"
            elif raiz in GDELT_PROTESTA:
                tipo = "protesta"
        if tipo == "conflicto" and f[G_GEO_TIPO] != "1":
            for p in PASOS:
                if abs(lat - p["lat"]) < 4 and distancia_km(lon, lat, p["lon"], p["lat"]) <= RADIO_PASO_KM:
                    pasos[p["id"]] += 1
        if not pais:
            continue
        agg = por_pais.setdefault(pais, {"total": 0, "conflicto": 0, "protesta": 0})
        agg["total"] += 1
        if not tipo:
            continue
        agg[tipo] += 1
        # El tipo 1 es "solo el país": son puntos en el centro del país, poco útiles en el mapa
        if f[G_GEO_TIPO] == "1":
            continue
        clave = (tipo, f[G_GEO_NOMBRE], round(lat, 1), round(lon, 1))
        l = lugares.setdefault(clave, {"hechos": 0, "menciones": 0, "fuentes": 0, "urls": [], "fecha": "",
                                       "pais": pais, "lat": lat, "lon": lon})
        l["hechos"] += 1
        l["menciones"] += articulos
        l["fuentes"] += int(f[G_FUENTES] or 1)
        l["fecha"] = max(l["fecha"], f[G_FECHA])
        if f[G_URL] and f[G_URL] not in l["urls"] and len(l["urls"]) < 3:
            l["urls"].append(f[G_URL])

    eventos = []
    # Solo los lugares con más cobertura, para que el mapa siga siendo legible
    for (tipo, nombre, _, _), l in sorted(lugares.items(), key=lambda x: -x[1]["menciones"])[:500]:
        if l["menciones"] < 3:
            continue
        eventos.append({
            "id": f"gdelt-{tipo}-" + normalizar(nombre).replace(" ", "-")[:60], "tipo": tipo,
            "titulo": "Ataques o enfrentamientos" if tipo == "conflicto" else "Protestas",
            "lugar": nombre, "pais": l["pais"], "lat": round(l["lat"], 3), "lon": round(l["lon"], 3),
            "fecha": iso(fecha(l["fecha"]) or AHORA), "hechos": l["hechos"], "menciones": l["menciones"],
            "peso": 0, "nivel": "verde", "fuente": "GDELT", "familia": "prensa",
            "url": l["urls"][0] if l["urls"] else None, "enlaces": l["urls"],
        })
    return {"eventos": eventos, "paises": por_pais, "pasos": pasos}


def titulares(paises=None):
    """Titulares en español de Google Noticias sobre crisis de las últimas 24 h."""
    texto = descargar(TITULARES_URL, como="texto")
    if texto is None:
        return None
    items = xml_items(texto, "Google Noticias")
    vistos, lista = set(), []
    for it in items:
        titulo = it.get("title", "")
        medio = it.get("source", "")
        # Google añade " - Medio" al final del titular
        if medio and titulo.endswith(" - " + medio):
            titulo = titulo[: -len(medio) - 3]
        clave = normalizar(titulo)[:70]
        if not clave or clave in vistos:
            continue
        vistos.add(clave)
        lista.append({"titulo": titulo.strip(), "url": it.get("link"), "medio": medio,
                      "fecha": iso(fecha(it.get("pubDate")) or AHORA)})
    lista.sort(key=lambda t: t["fecha"], reverse=True)
    return {"titulares": lista[:40]}


def ioda(paises):
    """Cortes de internet a escala de país detectados por IODA (Georgia Tech) en las últimas 24 h."""
    datos = descargar(IODA_URL)
    if datos is None:
        return None
    lista = datos.get("data") if isinstance(datos, dict) else datos
    exigir(isinstance(lista, list), "no trae una lista en 'data'")
    eventos = []
    for item in lista:
        entidad = item.get("entity") or {}
        a3 = paises.por_a2.get((entidad.get("code") or "").upper())
        if not a3 or a3 not in paises.centros:
            continue
        puntuacion = float((item.get("scores") or {}).get("overall") or 0)
        # IODA detecta a diario caídas pequeñas en muchos países. Solo cuentan los cortes grandes:
        # la puntuación crece en órdenes de magnitud y por debajo de 10^5 es ruido de fondo.
        peso = round(min(12.0, max(0.0, 3 * (math.log10(puntuacion + 1) - 5))), 1)
        if peso <= 0:
            continue
        lon, lat = paises.centro(a3)
        eventos.append({
            "id": f"ioda-{a3}", "tipo": "internet", "titulo": "Corte de internet",
            "lugar": entidad.get("name") or a3, "pais": a3, "lat": lat, "lon": lon,
            "fecha": iso(AHORA), "peso": peso, "nivel": "ambar" if peso >= 9 else "verde",
            "cortes": item.get("event_cnt"), "fuente": "IODA", "familia": "tecnica",
            "url": f"https://ioda.inetintel.cc.gatech.edu/country/{entidad.get('code')}",
        })
    return {"eventos": eventos}


AVISO_NIVELES = {1: "precauciones normales", 2: "más precaución", 3: "reconsiderar el viaje", 4: "no viajar"}


def avisos_viaje(paises):
    """Avisos de viaje del Departamento de Estado de EE. UU.: nivel actual y subidas."""
    texto = descargar(AVISOS_URL, como="texto")
    if texto is None:
        return None
    items = xml_items(texto, "avisos de viaje")
    exigir(items, "el RSS no tiene elementos")
    previos = leer("avisos.json", {"niveles": {}, "cambios": []})
    niveles = {}
    cambios = [c for c in previos.get("cambios", []) if reciente(c, VENTANA_MAPA)]
    for it in items:
        m = re.match(r"(.+?)\s+-\s+Level\s+(\d)", it.get("title", ""))
        if not m:
            continue
        a3 = paises.nombre(m.group(1))
        if not a3:
            continue
        nivel = int(m.group(2))
        niveles[a3] = max(nivel, niveles.get(a3, 0))
        anterior = previos.get("niveles", {}).get(a3)
        if anterior and nivel != anterior and not any(c["pais"] == a3 and c["a"] == nivel for c in cambios):
            cambios.append({"pais": a3, "de": anterior, "a": nivel, "url": it.get("link"),
                            "fecha": iso(fecha(it.get("pubDate")) or AHORA)})
    escribir("avisos.json", {"actualizado": iso(AHORA), "niveles": niveles, "cambios": cambios})
    eventos = []
    for c in cambios:
        sube = c["a"] > c["de"]
        lon, lat = paises.centro(c["pais"])
        eventos.append({
            "id": f"aviso-{c['pais']}-{c['a']}", "tipo": "aviso",
            "titulo": f"EE. UU. {'sube' if sube else 'baja'} su aviso de viaje a nivel {c['a']} ({AVISO_NIVELES[c['a']]})",
            "lugar": "", "pais": c["pais"], "lat": lat, "lon": lon, "fecha": c["fecha"],
            "peso": 4 * (c["a"] - c["de"]) if sube else 0, "nivel": "ambar" if sube and c["a"] >= 3 else "verde",
            "fuente": "Avisos de viaje EE. UU.", "familia": "oficial", "url": c["url"],
        })
    return {"eventos": eventos, "avisos": niveles}


# Enfermedades con alta letalidad o gran capacidad de expansión
EPIDEMIAS_GRAVES = re.compile(r"ebola|marburg|lassa|plague|nipah|cholera|yellow fever|mers|"
                              r"avian influenza a\(h5|mpox.*clade i|diphtheria|anthrax", re.I)


def oms(paises):
    """Brotes epidémicos publicados por la OMS (Disease Outbreak News) en los últimos 30 días."""
    datos = descargar(OMS_URL)
    if datos is None:
        return None
    lista = datos.get("value") if isinstance(datos, dict) else None
    exigir(isinstance(lista, list), "no trae una lista en 'value'")
    eventos = []
    for item in lista:
        titulo = item.get("Title") or item.get("OverrideTitle") or ""
        cuando = fecha(item.get("PublicationDateAndTime") or item.get("PublicationDate"))
        if not titulo or not cuando or cuando < AHORA - VENTANA_EPIDEMIAS:
            continue
        # "Marburg virus disease - Ethiopia": lo que va tras el guion es el país
        partes = re.split(r"\s+[-–—]\s+", titulo, maxsplit=1)
        enfermedad, lugar = (partes + [""])[:2]
        a3 = paises.nombre(lugar)
        if not a3:
            continue
        grave = bool(EPIDEMIAS_GRAVES.search(titulo))
        lon, lat = paises.centro(a3)
        url = item.get("ItemDefaultUrl") or ""
        if item.get("UrlName"):
            url = "https://www.who.int/emergencies/disease-outbreak-news/item/" + item["UrlName"]
        elif url.startswith("/"):
            url = "https://www.who.int/emergencies/disease-outbreak-news" + url
        eventos.append({
            "id": "oms-" + normalizar(titulo).replace(" ", "-")[:60], "tipo": "epidemia",
            "titulo": f"Brote: {enfermedad.strip()}", "lugar": lugar.strip(), "pais": a3,
            "lat": lat, "lon": lon, "fecha": iso(cuando), "peso": 8 if grave else 3,
            "nivel": "ambar" if grave else "verde", "fuente": "OMS", "familia": "sanitaria", "url": url or None,
        })
    return {"eventos": eventos}


def reliefweb(paises):
    """Crisis humanitarias abiertas en ReliefWeb (OCHA). Necesita RELIEFWEB_APPNAME aprobado."""
    if not RELIEFWEB_APPNAME:
        return {"eventos": [], "desactivada": True}
    datos = descargar(RELIEFWEB_URL)
    if datos is None:
        return None
    exigir(isinstance(datos.get("data"), list), "no trae una lista en 'data'")
    eventos = []
    for d in datos["data"]:
        c = d.get("fields") or {}
        estado = c.get("status")
        for pais in c.get("country") or []:
            a3 = (pais.get("iso3") or "").upper()
            if a3 not in paises.centros:
                continue
            lon, lat = paises.centro(a3)
            eventos.append({
                "id": f"reliefweb-{d.get('id')}-{a3}", "tipo": "crisis",
                "titulo": c.get("name") or "Crisis humanitaria", "lugar": (c.get("primary_type") or {}).get("name", ""),
                "pais": a3, "lat": lat, "lon": lon,
                "fecha": iso(fecha((c.get("date") or {}).get("created")) or AHORA),
                "peso": 6 if estado == "alert" else 0, "nivel": "ambar" if estado == "alert" else "verde",
                "estado": estado, "fuente": "ReliefWeb", "familia": "humanitaria", "url": c.get("url"),
            })
    return {"eventos": eventos}


# ----------------------------------------------------------------- alertas

CLAVES_PUNTOS = ("conflicto", "protestas", "desastres", "internet", "avisos", "epidemias", "humanitaria")
PARTE_DE = {"internet": "internet", "aviso": "avisos", "epidemia": "epidemias", "crisis": "humanitaria"}


def puntuar(eventos, gdelt_paises):
    """Puntuación de cada país con lo ocurrido en las últimas 48 h (30 días para epidemias)."""
    comp = {}

    def base(a3):
        return comp.setdefault(a3, {"eventos": 0, "rango": 0, "familias": set(), "crisis_abierta": False})

    for e in eventos:
        if not e.get("pais") or e["tipo"] in ("conflicto", "protesta"):
            continue
        if e["tipo"] == "crisis":
            # Una crisis humanitaria abierta cuenta mientras siga abierta, aunque sea antigua
            base(e["pais"])["crisis_abierta"] = True
        elif not reciente(e, VENTANA_EPIDEMIAS if e["tipo"] == "epidemia" else VENTANA_PUNTUACION):
            continue
        c = base(e["pais"])
        c["eventos"] += 1
        c["rango"] = max(c["rango"], RANGO[e["nivel"]])
        clave = PARTE_DE.get(e["tipo"], "desastres")
        c[clave] = c.get(clave, 0) + e["peso"]
        if e["peso"] > 0 or e["nivel"] != "verde":
            c["familias"].add(e.get("familia", "oficial"))

    for a3, g in (gdelt_paises or {}).items():
        if not (g["conflicto"] or g["protesta"]):
            continue
        c = base(a3)
        # Proporción de lo que se cuenta del país que es violencia política: corrige que de EE. UU.
        # o Rusia siempre se hable mucho. Hasta 20 hechos, el volumen pesa menos.
        cuota = g["conflicto"] / max(g["total"], 20)
        c["conflicto"] = 3 * math.log2(1 + g["conflicto"]) * min(1.0, cuota / 0.08)
        cuota_p = g["protesta"] / max(g["total"], 20)
        c["protestas"] = 1.5 * math.log2(1 + g["protesta"]) * min(1.0, cuota_p / 0.08)
        c["cuota_violencia"] = round(cuota, 3)
        c["hechos_violentos"] = g["conflicto"]
        c["protestas_n"] = g["protesta"]
        if c["conflicto"] >= 3 or c["protestas"] >= 3:
            c["familias"].add("prensa")

    resultado = {}
    for a3, c in comp.items():
        partes = {k: round(c.get(k, 0), 1) for k in CLAVES_PUNTOS}
        resultado[a3] = {**partes, "puntuacion": round(sum(partes.values()), 1), "eventos": c["eventos"],
                         "rango_evento": c["rango"], "familias": sorted(c["familias"]),
                         "crisis_abierta": c["crisis_abierta"], "cuota_violencia": c.get("cuota_violencia", 0),
                         "hechos_violentos": c.get("hechos_violentos", 0), "protestas_n": c.get("protestas_n", 0)}
    return resultado


def dias_subiendo(serie):
    """Cuántos días seguidos, terminando hoy, ha subido la puntuación."""
    n = 0
    for i in range(len(serie) - 1, 0, -1):
        if serie[i] > serie[i - 1] + 0.5:
            n += 1
        else:
            break
    return n


def confianza(familias):
    """Cuánto fiarse: coinciden varias familias de fuente o hay una fuente no periodística."""
    if len(familias) >= 2:
        return "alta"
    if familias and familias != ["prensa"]:
        return "media"
    return "baja"


def calcular_alertas(puntos, historial, avisos=None):
    previos = sorted(d for d in historial if d < HOY)[-DIAS_HISTORIAL:]
    calibrando = len(previos) < DIAS_CALIBRADO
    avisos = avisos or {}
    paises = {}
    candidatos = set(puntos) | {a for d in previos for a in historial[d]} | {a for a, n in avisos.items() if n >= 4}
    for a3 in candidatos:
        p = puntos.get(a3, {})
        actual = p.get("puntuacion", 0)
        serie = [historial[d].get(a3, 0) for d in previos]
        media = statistics.fmean(serie) if serie else 0
        desv = statistics.pstdev(serie) if len(serie) > 1 else 0
        # z: cuántas desviaciones por encima de lo normal está hoy (con suelo para no exagerar el ruido)
        z = (actual - media) / max(desv, 2, 0.25 * media) if serie else 0
        subiendo = dias_subiendo(serie + [actual])
        rango_evento = p.get("rango_evento", 0)
        aviso = avisos.get(a3)
        motivos = []

        # 1. Gravedad aguda: lo que pasa ahora
        rango = 0
        if actual >= 40:
            rango, _ = 2, motivos.append("Actividad muy alta")
        elif actual >= 25:
            rango, _ = 1, motivos.append("Actividad alta")
        if rango_evento:
            rango = max(rango, rango_evento)
            motivos.append("Alerta oficial roja" if rango_evento == 2 else "Alerta oficial naranja")

        # 2. Escalada: empeora respecto a lo que es normal para el país
        escalada = False
        if not calibrando and z >= 3 and actual >= 18:
            rango, escalada = 2, True
            motivos.append("Muy por encima de lo habitual")
        elif not calibrando and z >= 1.5 and actual >= 10:
            rango, escalada = max(rango, 1), True
            motivos.append("Por encima de lo habitual")
        if subiendo >= 3 and actual >= 10:
            rango, escalada = max(rango, 1), True
            motivos.append(f"{subiendo} días seguidos subiendo")

        # 3. Gravedad estructural: crisis prolongadas, aunque hoy no empeoren
        if not calibrando and media >= 30:
            rango = max(rango, 2)
            motivos.append("Crisis prolongada")
        elif not calibrando and media >= 18:
            rango = max(rango, 1)
            motivos.append("Crisis prolongada")
        if aviso == 4:
            rango = max(rango, 1)
            motivos.append("EE. UU. desaconseja viajar")
        if p.get("crisis_abierta"):
            rango = max(rango, 1)
            motivos.append("Crisis humanitaria abierta")

        if rango == 0 and actual <= 0:
            continue
        nivel = {0: "verde", 1: "ambar", 2: "rojo"}[rango]
        tendencia = ("sube" if z >= 1 or subiendo >= 3 else "baja" if z <= -1 else "estable") if serie else "sin datos"
        resto = {k: v for k, v in p.items() if k not in ("puntuacion", "rango_evento")}
        paises[a3] = {"nivel": nivel, "escalada": escalada, "motivos": list(dict.fromkeys(motivos)),
                      "confianza": confianza(p.get("familias", []) + (["oficial"] if aviso == 4 else [])),
                      "puntuacion": actual, "media": round(media, 1), "z": round(z, 2), "tendencia": tendencia,
                      "dias_subiendo": subiendo, "ayer": serie[-1] if serie else None,
                      "serie": [round(x, 1) for x in serie + [actual]], **resto}
        if aviso:
            paises[a3]["aviso_viaje"] = aviso
    return {"actualizado": iso(AHORA), "calibrando": calibrando, "dias_historial": len(previos), "paises": paises}


def calcular_pasos(conteo):
    """Riesgo en los pasos marítimos según los hechos violentos a menos de 350 km en 24 h."""
    resultado = []
    for p in PASOS:
        n = (conteo or {}).get(p["id"], 0)
        nivel = "rojo" if n >= 25 else "ambar" if n >= 6 else "verde"
        resultado.append({**p, "hechos": n, "nivel": nivel})
    return resultado


def parte(alertas, previas):
    """Qué ha cambiado desde ayer: países que suben o bajan de nivel y los que más empeoran."""
    ahora = alertas["paises"]
    # Los niveles de referencia son los del último cálculo de ayer
    if previas.get("dia") == HOY:
        referencia = previas.get("niveles_ayer", {})
    else:
        referencia = {a: p["nivel"] for a, p in previas.get("paises", {}).items()}
    suben = sorted((a for a, p in ahora.items() if RANGO[p["nivel"]] > RANGO.get(referencia.get(a, "verde"), 0)),
                   key=lambda a: (-RANGO[ahora[a]["nivel"]], -ahora[a]["puntuacion"]))
    bajan = sorted(a for a, n in referencia.items() if RANGO[n] > RANGO[ahora.get(a, {}).get("nivel", "verde")])
    empeoran = sorted((a for a, p in ahora.items() if p["escalada"]), key=lambda a: -ahora[a]["z"])
    return {"suben": suben[:10], "bajan": bajan[:10], "empeoran": empeoran[:8]}, referencia


# --------------------------------------------------------------------- main

FUENTES = [("USGS", usgs), ("GDACS", gdacs), ("NASA EONET", eonet), ("GDELT", gdelt),
           ("Titulares", titulares), ("IODA", ioda), ("Avisos de viaje EE. UU.", avisos_viaje),
           ("OMS", oms), ("ReliefWeb", reliefweb)]


def main():
    SALIDA.mkdir(parents=True, exist_ok=True)
    anterior = leer("eventos.json", {"eventos": [], "titulares": [], "fuentes": {}})
    alertas_previas = leer("alertas.json", {})
    paises = Paises()

    eventos, estado, extra = [], {}, {}
    for nombre, funcion in FUENTES:
        log(f"Descargando {nombre}…")
        error = None
        try:
            resultado = funcion(paises)
            if resultado is None:
                error = "no responde"
        except FormatoInesperado as e:
            resultado, error = None, f"formato inesperado: {e}"
        except Exception as e:  # noqa: BLE001  cualquier cambio raro en una fuente no debe tumbar las demás
            resultado, error = None, f"error al leer los datos: {type(e).__name__}: {e}"
        if resultado and resultado.get("desactivada"):
            continue
        previo = (anterior.get("fuentes") or {}).get(nombre, {})
        if error:
            log(f"  {nombre}: {error}")
            # Se conservan los últimos datos buenos de la fuente
            resultado = {"eventos": [e for e in anterior["eventos"] if e.get("fuente") == nombre]}
            if nombre == "Titulares":
                resultado = {"titulares": anterior.get("titulares", [])}
        cuantos = len(resultado.get("eventos", resultado.get("titulares", [])))
        estado[nombre] = {"ok": not error, "error": error, "eventos": cuantos,
                          "fallos_seguidos": (previo.get("fallos_seguidos", 0) + 1) if error else 0,
                          "ultimo_ok": iso(AHORA) if not error else previo.get("ultimo_ok")}
        eventos.extend(resultado.get("eventos", []))
        extra.update({k: v for k, v in resultado.items() if k != "eventos"})

    eventos = [e for e in eventos if reciente(e, VENTANA_EPIDEMIAS if e["tipo"] in ("epidemia", "crisis") else VENTANA_MAPA)
               or e["tipo"] == "crisis"]
    eventos.sort(key=lambda e: e["fecha"], reverse=True)

    # Si GDELT falla, sin sus agregados la puntuación de conflicto caería a cero: se reutilizan los últimos
    gdelt_paises = extra.get("paises") or anterior.get("gdelt_paises") or {}
    gdelt_pasos = extra.get("pasos") or anterior.get("gdelt_pasos") or {}
    puntos = puntuar(eventos, gdelt_paises)
    historial = leer("historial.json", {})
    dia = historial.setdefault(HOY, {})
    for a3, p in puntos.items():
        dia[a3] = max(dia.get(a3, 0), p["puntuacion"])
    historial = {d: historial[d] for d in sorted(historial)[-(DIAS_HISTORIAL + 1):]}

    avisos = extra.get("avisos") or leer("avisos.json", {}).get("niveles") or {}
    alertas = calcular_alertas(puntos, historial, avisos)
    alertas["pasos"] = calcular_pasos(gdelt_pasos)
    alertas["parte"], referencia = parte(alertas, alertas_previas)
    alertas["dia"], alertas["niveles_ayer"] = HOY, referencia

    escribir("eventos.json", {"actualizado": iso(AHORA), "fuentes": estado, "eventos": eventos,
                              "titulares": extra.get("titulares", []),
                              "gdelt_paises": gdelt_paises, "gdelt_pasos": gdelt_pasos})
    escribir("alertas.json", alertas)
    escribir("historial.json", historial)
    log("Listo:", {k: ("ok" if v["ok"] else v["error"]) + f" ({v['eventos']})" for k, v in estado.items()})
    from collections import Counter
    log("Niveles:", dict(Counter(p["nivel"] for p in alertas["paises"].values())))
    log("Rojo:", sorted(a for a, p in alertas["paises"].items() if p["nivel"] == "rojo"))
    log("Ámbar:", sorted(a for a, p in alertas["paises"].items() if p["nivel"] == "ambar"))
    log("Pasos:", {p["id"]: p["hechos"] for p in alertas["pasos"]})
    if not any(v["ok"] for v in estado.values()):
        sys.exit("Ninguna fuente respondió")


if __name__ == "__main__":
    main()
