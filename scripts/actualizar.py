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
  historico.json  puntuación y nivel de cada país, día a día, sin límite
  archivo/        foto de cada día para consultarla después
"""

import csv
import html
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import inteligencia  # noqa: E402

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
    "q": ('(bombardeo OR misiles OR "ataque con drones" OR "ofensiva militar" OR "golpe de Estado" OR '
          '"alto el fuego" OR evacuación OR terremoto OR huracán OR brote) -fútbol -baloncesto -liga -partido when:1d'),
    "hl": "es", "gl": "ES", "ceid": "ES:es"})
IODA_URL = "https://api.ioda.inetintel.cc.gatech.edu/v2/outages/summary?" + urllib.parse.urlencode({
    "from": int((AHORA - timedelta(hours=24)).timestamp()), "until": int(AHORA.timestamp()), "entityType": "country"})
AVISOS_URL = "https://travel.state.gov/_res/rss/TAsTWs.xml"
EXTERIORES_BASE = "https://www.exteriores.gob.es"
EXTERIORES_INDICE = EXTERIORES_BASE + "/es/ServiciosAlCiudadano/Paginas/Recomendaciones-de-viaje.aspx"
EXTERIORES_CADA = timedelta(hours=12)       # 197 fichas: se consultan dos veces al día como mucho
OONI_URL = "https://api.ooni.io/api/v1/aggregation?test_name={app}&since={desde}&until={hasta}&axis_x=probe_cc"
OONI_APPS = {"whatsapp": "WhatsApp", "telegram": "Telegram", "signal": "Signal", "facebook_messenger": "Messenger"}
COPERNICUS_URL = "https://mapping.emergency.copernicus.eu/activations/api/activations/?limit=40"
EMSC_URL = "https://www.seismicportal.eu/fdsnws/event/1/query?" + urllib.parse.urlencode({
    "format": "json", "minmag": "4", "limit": "300", "start": (AHORA - timedelta(days=7)).strftime("%Y-%m-%d"),
    "minlat": "24", "maxlat": "50", "minlon": "-25", "maxlon": "45"})
IGN_URL = "http://www.ign.es/ign/RssTools/sismologia.xml"
ELPAIS_URL = "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/internacional/portada"


def google_noticias(consulta):
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": consulta, "hl": "es", "gl": "ES", "ceid": "ES:es"})


TITULARES_MAS = [google_noticias("site:efe.com (ataque OR guerra OR ofensiva OR conflicto OR crisis OR golpe) when:1d"),
                 google_noticias("site:rtve.es (ataque OR guerra OR ofensiva OR conflicto OR crisis OR golpe) when:1d")]
ANALISIS_URLS = {"Real Instituto Elcano": google_noticias("site:realinstitutoelcano.org when:60d"),
                 "IEEE": google_noticias("site:ieee.es when:90d"),
                 "CIDOB": google_noticias("site:cidob.org when:90d")}
CLOUDFLARE_TOKEN = os.environ.get("CLOUDFLARE_TOKEN", "").strip()
CLOUDFLARE_URL = "https://api.cloudflare.com/client/v4/radar/annotations/outages?dateRange=1d&format=json&limit=100"
UCDP_TOKEN = os.environ.get("UCDP_TOKEN", "").strip()
UCDP_VERSION = os.environ.get("UCDP_VERSION", "").strip() or "26.0.9"
UCDP_URL = f"https://ucdpapi.pcr.uu.se/api/gedevents/{UCDP_VERSION}?pagesize=1000&StartDate=" + \
    (AHORA - timedelta(days=90)).strftime("%Y-%m-%d")
OMS_URL = "https://www.who.int/api/news/diseaseoutbreaknews?" + urllib.parse.urlencode(
    {"$orderby": "PublicationDateAndTime desc", "$top": "30"})
RELIEFWEB_APPNAME = os.environ.get("RELIEFWEB_APPNAME", "").strip()
RELIEFWEB_URL = "https://api.reliefweb.int/v2/disasters?" + urllib.parse.urlencode([
    ("appname", RELIEFWEB_APPNAME), ("limit", "200"), ("preset", "latest"),
    ("filter[field]", "status"), ("filter[value][]", "alert"), ("filter[value][]", "current"),
    ("fields[include][]", "name"), ("fields[include][]", "status"), ("fields[include][]", "country.iso3"),
    ("fields[include][]", "primary_type.name"), ("fields[include][]", "date.created"), ("fields[include][]", "url")])

# Pasos marítimos por los que pasa buena parte de la energía y el comercio que llega a Europa.
# "zona": puntos (lon, lat) y radio en km que cubren el paso sin meter ciudades cercanas ajenas
# a la ruta (por ejemplo, Gaza o El Cairo quedan fuera de Suez).
PASOS = [
    {"id": "ormuz", "nombre": "Estrecho de Ormuz", "lon": 56.4, "lat": 26.6, "radio": 220,
     "zona": [(56.4, 26.6)], "porque": "Salida del petróleo y el gas del golfo Pérsico"},
    {"id": "bab", "nombre": "Bab el-Mandeb y mar Rojo sur", "lon": 43.4, "lat": 12.6, "radio": 250,
     "zona": [(43.4, 12.6), (42.0, 15.5)], "porque": "Entrada al mar Rojo y al canal de Suez desde Asia"},
    {"id": "suez", "nombre": "Canal de Suez", "lon": 32.35, "lat": 30.6, "radio": 90,
     "zona": [(32.3, 31.2), (32.35, 30.6), (32.55, 29.95)], "porque": "Ruta más corta entre Asia y Europa"},
    {"id": "bosforo", "nombre": "Bósforo", "lon": 29.05, "lat": 41.1, "radio": 80,
     "zona": [(29.05, 41.1), (26.4, 40.2)], "porque": "Salida del mar Negro: cereal, petróleo y gas"},
    {"id": "gibraltar", "nombre": "Estrecho de Gibraltar", "lon": -5.6, "lat": 35.95, "radio": 120,
     "zona": [(-5.6, 35.95)], "porque": "Entrada al Mediterráneo, junto a España"},
    {"id": "malaca", "nombre": "Estrecho de Malaca", "lon": 100.4, "lat": 3.0, "radio": 250,
     "zona": [(98.5, 5.0), (100.4, 3.0), (103.8, 1.25)], "porque": "Principal ruta entre el Índico y el Pacífico"},
    {"id": "taiwan", "nombre": "Estrecho de Taiwán", "lon": 119.5, "lat": 24.0, "radio": 200,
     "zona": [(119.5, 24.0)], "porque": "Ruta de los semiconductores y del comercio de Asia oriental"},
    {"id": "panama", "nombre": "Canal de Panamá", "lon": -79.7, "lat": 9.1, "radio": 100,
     "zona": [(-79.7, 9.1)], "porque": "Paso entre el Atlántico y el Pacífico"},
]


class FormatoInesperado(Exception):
    """La fuente respondió, pero no con la forma que esperamos."""


# ---------------------------------------------------------------- utilidades

def log(*a):
    print(*a, file=sys.stderr, flush=True)


def descargar(url, como="json", intentos=3, espera=6, cabeceras=None):
    """Devuelve el contenido o None si la fuente no responde tras varios intentos."""
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; atalaya/1.0; +https://github.com/serbenda/atalaya)", **(cabeceras or {})})
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
        self.por_nombre, self.por_a2, self.por_nombre_es = {}, {}, {}
        for p in lista:
            for n in p["nombres"]:
                self.por_nombre[normalizar(n)] = p["a3"]
            for n in p.get("nombres_es", []):
                if len(normalizar(n)) >= 4:
                    self.por_nombre_es[normalizar(n)] = p["a3"]
                    self.por_nombre.setdefault(normalizar(n), p["a3"])
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

    def a2_de(self, a3):
        return next((a2 for a2, x in self.por_a2.items() if x == a3), a3)

    def en_texto(self, texto):
        """Países que se nombran en un texto en español ("ataque en Sudán y Chad")."""
        if not hasattr(self, "_patron_es"):
            nombres = sorted(self.por_nombre_es, key=len, reverse=True)
            self._patron_es = re.compile(r"\b(" + "|".join(re.escape(n) for n in nombres) + r")\b")
        encontrados = []
        for m in self._patron_es.finditer(normalizar(texto)):
            a3 = self.por_nombre_es[m.group(1)]
            if a3 not in encontrados:
                encontrados.append(a3)
        return encontrados

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
        alerta = (it.get("alertlevel") or "Green").lower()
        # Incendios y sequías en verde son casi diarios y llenan el mapa sin aportar
        if tipo in ("WF", "DR") and alerta == "green":
            continue
        clave = f"gdacs-{tipo}-{it.get('eventid')}"
        if clave in vistos:
            continue
        vistos.add(clave)
        try:
            lat, lon = float(it.get("lat")), float(it.get("long"))
        except (TypeError, ValueError):
            continue
        peso = {"green": 1, "orange": 6, "red": 15}.get(alerta, 1)
        nombre = it.get("eventname") or ""
        iso3 = (it.get("iso3") or "").upper()[:3]
        pais = iso3 if len(iso3) == 3 else paises.asignar(it.get("country"), lon, lat)
        if tipo == "DR":
            # Las sequías abarcan muchos países a la vez y avanzan despacio: se muestran en el mapa
            # pero no se atribuyen a un país ni fijan su nivel
            pais, peso = None, 0
        eventos.append({
            "id": clave, "tipo": "desastre",
            "titulo": GDACS_TIPOS[tipo] + (f" {nombre.title()}" if nombre and tipo == "TC" else ""),
            "lugar": it.get("country") or "", "pais": pais,
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
G_A1_NOMBRE, G_A2_NOMBRE, G_CODIGO = 6, 16, 26
G_A1_PAIS, G_A1_GRUPO, G_A1_TIPOS = 7, 8, (12, 13, 14)
G_A2_PAIS, G_A2_GRUPO, G_A2_TIPOS = 17, 18, (22, 23, 24)
G_RAIZ_EVENTO, G_BASE, G_RAIZ, G_FUENTES, G_ARTICULOS = 25, 27, 28, 32, 33
G_GEO_TIPO, G_GEO_NOMBRE, G_GEO_LAT, G_GEO_LON, G_FECHA, G_URL = 51, 52, 56, 57, 59, 60
# Códigos CAMEO raíz: 14 protestas; 18 agresiones, 19 combates, 20 violencia masiva
GDELT_VIOLENCIA = {"18", "19", "20"}
GDELT_PROTESTA = {"14"}
# Tipos de actor que hacen que la violencia sea política y no delincuencia común:
# ejército, rebeldes, insurgentes, separatistas, fuerzas armadas no estatales, gobierno,
# inteligencia y oposición. La policía (COP) no entra: en la prensa casi siempre es crónica de sucesos.
ACTORES_POLITICOS = {"MIL", "REB", "INS", "SEP", "UAF", "GOV", "SPY", "OPP"}
# Señales de desescalada (CAMEO): 086 permitir ayuda humanitaria, 087 desescalada militar
# (incluye 0871, declarar un alto el fuego). "Negociar" (046) no entra: aparece a diario en todas partes.
GDELT_DESESCALADA = {"086", "087"}
# Medios de propiedad o control estatal en países sin prensa libre. Sus noticias cuentan la mitad:
# no se descartan (a veces son la única fuente), pero no pueden encender un país por sí solas.
MEDIOS_ESTATALES = ("rt.com", "sputniknews", "sputnikglobe", "tass.ru", "tass.com", "ria.ru", "xinhuanet",
                    "news.cn", "globaltimes.cn", "cgtn.com", "chinadaily.com.cn", "presstv", "irna.ir",
                    "tasnimnews", "farsnews", "mehrnews", "kcna", "rodong.rep.kp", "telesurtv", "granma.cu",
                    "sana.sy", "belta.by", "almanar.com.lb")
PESO_ESTATAL = 0.5


def dominio(url):
    try:
        return urllib.parse.urlsplit(url).hostname or ""
    except ValueError:
        return ""


def es_estatal(url):
    d = dominio(url)
    return any(m in d for m in MEDIOS_ESTATALES)


def region_de(nombre_geo):
    """Primera división administrativa: 'Al Fashir, Northern Darfur, Sudan' -> 'Northern Darfur';
    'Darfur, Sudan' -> 'Darfur'. Las zonas genéricas ('Israel (general)') no cuentan."""
    partes = [x.strip() for x in (nombre_geo or "").split(",") if x.strip()]
    region = partes[1] if len(partes) >= 3 else partes[0] if len(partes) == 2 else None
    return None if not region or "(general)" in region else region


def es_politico(f):
    """Violencia política: con actores armados o estatales, grupos conocidos o entre dos países.
    Deja fuera la violencia entre civiles de un mismo país sin más contexto (delincuencia común)."""
    tipos = {f[i] for i in G_A1_TIPOS + G_A2_TIPOS}
    if tipos & ACTORES_POLITICOS or f[G_A1_GRUPO] or f[G_A2_GRUPO]:
        return True
    return bool(f[G_A1_PAIS] and f[G_A2_PAIS] and f[G_A1_PAIS] != f[G_A2_PAIS])


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
    # La misma noticia genera a menudo varios "hechos": se cuenta una vez por noticia (URL)
    vistas = set()
    regiones, parejas = {}, {}
    # Aceleración: hechos de las últimas 12 h frente a las 12 h anteriores (tendencia desde el primer día)
    mas_reciente = max((f[G_FECHA] for f in filas if len(f) >= 61 and f[G_FECHA].isdigit()), default="")
    corte = (fecha(mas_reciente) - timedelta(hours=12)).strftime("%Y%m%d%H%M%S") if mas_reciente else ""
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
                if abs(lat - p["lat"]) < 6 and any(distancia_km(lon, lat, x, y) <= p["radio"] for x, y in p["zona"]):
                    pasos[p["id"]] += 1
        if not pais:
            continue
        agg = por_pais.setdefault(pais, {"total": 0, "conflicto": 0, "protesta": 0, "interestatal": 0,
                                         "militar": 0, "disturbios": 0, "desescalada": 0, "estatal": 0})
        url = f[G_URL]
        if url:
            clave_url = (pais, tipo or ("desescalada" if f[G_BASE] in GDELT_DESESCALADA else ""), url)
            if clave_url in vistas:
                continue
            vistas.add(clave_url)
        peso = PESO_ESTATAL if url and es_estatal(url) else 1
        agg["total"] += peso
        if not tipo:
            if f[G_RAIZ_EVENTO] == "1" and f[G_BASE] in GDELT_DESESCALADA and es_politico(f):
                agg["desescalada"] += peso
            continue
        agg[tipo] += peso
        if peso < 1:
            agg["estatal"] += 1
        mitad = "_12h" if f[G_FECHA] >= corte else "_12h_antes"
        agg[tipo + mitad] = agg.get(tipo + mitad, 0) + peso
        if tipo == "conflicto":
            if f[G_A1_PAIS] and f[G_A2_PAIS] and f[G_A1_PAIS] != f[G_A2_PAIS]:
                agg["interestatal"] += peso
            if {f[i] for i in G_A1_TIPOS + G_A2_TIPOS} & {"MIL", "REB", "INS", "UAF"}:
                agg["militar"] += peso
            reg = region_de(f[G_GEO_NOMBRE]) if f[G_GEO_TIPO] != "1" else None
            if reg:
                r = regiones.setdefault(pais, {})
                r[reg] = r.get(reg, 0) + peso
            a1, a2 = f[G_A1_NOMBRE].strip(), f[G_A2_NOMBRE].strip()
            if a1 and a2 and a1 != a2:
                par = parejas.setdefault(pais, {})
                par[(a1, a2)] = par.get((a1, a2), 0) + peso
        elif f[G_BASE] == "145":  # protesta violenta o disturbios
            agg["disturbios"] += peso
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

    for pais, agg in por_pais.items():
        for k, v in list(agg.items()):
            if isinstance(v, float):
                agg[k] = round(v, 1)
        # Dónde se concentra la violencia y quién contra quién (con al menos 5 hechos)
        if agg["conflicto"] >= 5:
            total_reg = sum(regiones.get(pais, {}).values())
            if total_reg:
                agg["regiones"] = [[r, round(n / total_reg, 2)] for r, n in
                                   sorted(regiones[pais].items(), key=lambda x: -x[1])[:3] if n / total_reg >= 0.1]
            agg["actores"] = [[a, b, round(n, 1)] for (a, b), n in
                              sorted(parejas.get(pais, {}).items(), key=lambda x: -x[1])[:3] if n >= 3]

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
    """Titulares en español sobre crisis de las últimas 24 h: Google Noticias, EFE, RTVE y El País."""
    textos = [descargar(u, como="texto", intentos=2) for u in [TITULARES_URL, *TITULARES_MAS, ELPAIS_URL]]
    if not any(textos):
        return None
    items = []
    for t, origen in zip(textos, ["Google Noticias", "EFE", "RTVE", "El País"]):
        if t:
            for it in xml_items(t, origen):
                it.setdefault("source", "EL PAÍS" if origen == "El País" else "")
                items.append(it)
    vistos, lista = set(), []
    for it in items:
        titulo = it.get("title", "")
        medio = it.get("source", "")
        # Google añade " - Medio" al final del titular
        if medio and titulo.endswith(" - " + medio):
            titulo = titulo[: -len(medio) - 3]
        clave = normalizar(titulo)[:70]
        # Fuera aniversarios y efemérides ("el bombardeo de 1937")
        if any(int(a) < AHORA.year - 1 for a in re.findall(r"\b(1[89]\d\d|20\d\d)\b", titulo)):
            continue
        if not clave or clave in vistos:
            continue
        vistos.add(clave)
        cuando = fecha(it.get("pubDate")) or AHORA
        # Fuera portadas de sección, directos y notas de prensa
        if (cuando < AHORA - timedelta(hours=36) or len(titulo.split()) < 5 or "comunica" in normalizar(medio)
                or "en directo" in normalizar(titulo)):
            continue
        lista.append({"titulo": titulo.strip(), "url": it.get("link"), "medio": medio, "fecha": iso(cuando),
                      "paises": paises.en_texto(titulo) if paises else []})
    lista.sort(key=lambda t: t["fecha"], reverse=True)
    return {"titulares": lista[:60]}


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


MESES = {m: i for i, m in enumerate(["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
                                      "septiembre", "octubre", "noviembre", "diciembre"], 1)}
EXTERIORES_NIVELES = {1: "sin restricciones especiales", 2: "precaución o zonas desaconsejadas",
                      3: "se desaconseja viajar salvo necesidad", 4: "se desaconseja viajar bajo cualquier circunstancia"}


ZONAS = re.compile(r"\b(zona|zonas|region|regiones|frontera|fronteras|fronteriza|fronterizas|provincia|provincias|"
                   r"departamento|departamentos|estados de|estado de|norte de|sur de|este de|oeste de|areas)\b")


def exteriores_nivel(notas):
    """Nivel de la recomendación a partir de las notas importantes de la ficha, frase a frase.
    4: no viajar bajo ninguna circunstancia; 3: no viajar salvo necesidad; 2: zonas desaconsejadas o
    precaución extrema; 1: sin restricciones especiales."""
    nivel = 1
    for frase in re.split(r"(?<=[.;:])\s+", normalizar_frases(notas)):
        f = normalizar(frase)
        if "abandonen el pais" in f or re.search(r"(recomienda|insta|aconseja)[^.]{0,40}abandonar el pais", f):
            nivel = max(nivel, 4)
            continue
        # Solo cuentan las frases sobre viajar al país ("se desaconseja participar en manifestaciones" no)
        contra = re.search(r"desaconsejan? (totalmente |absolutamente |completamente )?(el |todo |cualquier |los |realizar )?(viaje|viajes|viajar)"
                           r"|no viajar(?! de noche)|aplazar (el |su )?viaje|evitar (todo|cualquier) viaje", f)
        if not contra:
            if re.search(r"extremar (la|las) precaucion|maxima precaucion", f):
                nivel = max(nivel, 2)
            continue
        parcial = ZONAS.search(f) and not re.search(r"todo el (pais|territorio)", f)
        if parcial:
            nivel = max(nivel, 2)
        elif re.search(r"(cualquier|ninguna) circunstancia", f):
            nivel = max(nivel, 4)
        elif re.search(r"\b(salvo|excepto)\b", f):
            nivel = max(nivel, 3)
        elif re.search(r"(totalmente|absolutamente|completamente) (el |todo |cualquier )?viaj", f):
            nivel = max(nivel, 4)
        else:
            nivel = max(nivel, 3)
    return nivel


def normalizar_frases(texto):
    # Las fichas a veces separan letras con espacios ("S E DESACONSEJA"); se juntan las mayúsculas sueltas
    return re.sub(r"\b([A-ZÁÉÍÓÚÑ]) (?=[A-ZÁÉÍÓÚÑ]{2,})", r"\1", texto or "")


def exteriores_ficha(url):
    html_ficha = descargar(url, como="texto", intentos=2, espera=3)
    if not html_ficha:
        return None
    texto = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html_ficha, flags=re.S)
    texto = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", texto)))
    m = re.search(r"ltima actualizaci[oó]n el (\d{1,2}) de (\w+) de (\d{4})", texto)
    actualizacion = None
    if m and m.group(2).lower() in MESES:
        actualizacion = f"{m.group(3)}-{MESES[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
    i = texto.find("Notas importantes")
    notas = texto[i + 17:i + 900].strip() if i >= 0 else ""
    # Corta en la primera sección siguiente de la ficha
    notas = re.split(r" (Documentaci[oó]n y visados|Seguridad|Sanidad|Teléfonos de emergencia) ", notas)[0][:600]
    return {"actualizacion": actualizacion, "notas": notas, "nivel": exteriores_nivel(notas)}


def exteriores(paises):
    """Recomendaciones de viaje del Ministerio de Asuntos Exteriores de España (sin API: se lee la web)."""
    previo = leer("exteriores.json", {"paises": {}, "cambios": []})
    if previo.get("actualizado") and (fecha(previo["actualizado"]) or AHORA) > AHORA - EXTERIORES_CADA:
        datos_paises, cambios = previo["paises"], previo.get("cambios", [])
    else:
        indice = descargar(EXTERIORES_INDICE, como="texto")
        if indice is None:
            return None
        enlaces = sorted(set(re.findall(r'Detalle-recomendaciones-de-viaje\.aspx\?trc=([^"&\s>]+)', indice)))
        exigir(len(enlaces) > 100, f"el índice solo tiene {len(enlaces)} países")
        objetivos = []
        for trc in enlaces:
            nombre = urllib.parse.unquote_plus(trc).strip()
            a3 = paises.nombre(nombre)
            if a3:
                objetivos.append((a3, EXTERIORES_BASE + "/es/ServiciosAlCiudadano/Paginas/Detalle-recomendaciones-de-viaje.aspx?trc=" + trc))
        with ThreadPoolExecutor(max_workers=6) as hilos:
            fichas = list(hilos.map(lambda o: exteriores_ficha(o[1]), objetivos))
        exigir(sum(1 for f in fichas if f) >= len(objetivos) // 2, "no se han podido leer la mitad de las fichas")
        datos_paises = {}
        cambios = [c for c in previo.get("cambios", []) if reciente(c, VENTANA_MAPA)]
        for (a3, url), ficha in zip(objetivos, fichas):
            if not ficha:
                if a3 in previo["paises"]:
                    datos_paises[a3] = previo["paises"][a3]
                continue
            ficha["url"] = url
            datos_paises[a3] = ficha
            antes = previo["paises"].get(a3)
            if antes and ficha["actualizacion"] and ficha["actualizacion"] != antes.get("actualizacion"):
                cambios.append({"pais": a3, "de": antes.get("nivel"), "a": ficha["nivel"], "url": url,
                                "notas": ficha["notas"][:300], "fecha": iso(AHORA)})
        escribir("exteriores.json", {"actualizado": iso(AHORA), "paises": datos_paises, "cambios": cambios})
    eventos = []
    for c in cambios:
        sube = (c["a"] or 0) > (c["de"] or 0)
        lon, lat = paises.centro(c["pais"])
        titulo = (f"Exteriores eleva su recomendación: {EXTERIORES_NIVELES[c['a']]}" if sube
                  else "Exteriores actualiza sus recomendaciones de viaje")
        eventos.append({
            "id": f"exteriores-{c['pais']}-{c['fecha'][:10]}", "tipo": "aviso", "titulo": titulo,
            "lugar": c.get("notas", "")[:160], "pais": c["pais"], "lat": lat, "lon": lon, "fecha": c["fecha"],
            "peso": 5 * ((c["a"] or 0) - (c["de"] or 0)) if sube else 1,
            "nivel": "ambar" if sube and c["a"] >= 3 else "verde", "fuente": "Exteriores (España)",
            "familia": "oficial", "url": c["url"],
        })
    resumen = {a3: {"nivel": f["nivel"], "texto": EXTERIORES_NIVELES[f["nivel"]], "actualizacion": f.get("actualizacion"),
                    "notas": f.get("notas", "")[:400], "url": f.get("url")} for a3, f in datos_paises.items()}
    return {"eventos": eventos, "exteriores": resumen}


def ooni(paises):
    """Bloqueos de aplicaciones de mensajería medidos por OONI: un bloqueo nuevo suele anunciar algo."""
    hoy, hace2, hace14 = AHORA.date(), (AHORA - timedelta(days=2)).date(), (AHORA - timedelta(days=14)).date()
    tasas = {}
    for app in OONI_APPS:
        for ventana, desde, hasta in (("ahora", hace2, hoy + timedelta(days=1)), ("antes", hace14, hace2)):
            datos = descargar(OONI_URL.format(app=app, desde=desde, hasta=hasta), intentos=2)
            if datos is None:
                return None
            exigir(isinstance(datos.get("result"), list), "no trae 'result'")
            for fila in datos["result"]:
                n = fila.get("measurement_count") or 0
                if n >= 10:
                    tasas.setdefault((fila.get("probe_cc"), app), {})[ventana] = (fila.get("anomaly_count", 0) / n, n)
    eventos = []
    por_pais = {}
    for (cc, app), t in tasas.items():
        a3 = paises.por_a2.get(cc or "")
        if not a3 or "ahora" not in t:
            continue
        ahora, antes = t["ahora"][0], t.get("antes", (0, 0))[0]
        if ahora >= 0.5 and antes < 0.25:
            por_pais.setdefault(a3, {"nuevo": [], "cronico": []})["nuevo"].append(OONI_APPS[app])
        elif ahora >= 0.5:
            por_pais.setdefault(a3, {"nuevo": [], "cronico": []})["cronico"].append(OONI_APPS[app])
    for a3, b in por_pais.items():
        nuevo = bool(b["nuevo"])
        # Un bloqueo habitual de una sola aplicación suele ser ruido de medida: solo cuentan dos o más
        if not nuevo and len(b["cronico"]) < 2:
            continue
        lon, lat = paises.centro(a3)
        apps = b["nuevo"] or b["cronico"]
        eventos.append({
            "id": f"ooni-{a3}", "tipo": "censura",
            "titulo": ("Nuevo bloqueo de " if nuevo else "Bloqueo habitual de ") +
                      (", ".join(apps[:-1]) + " y " + apps[-1] if len(apps) > 1 else apps[0]),
            "lugar": "", "pais": a3, "lat": lat, "lon": lon, "fecha": iso(AHORA),
            "peso": 6 if nuevo else 0, "nivel": "ambar" if nuevo else "verde", "fuente": "OONI", "familia": "tecnica",
            "url": f"https://explorer.ooni.org/country/{paises.a2_de(a3)}",
        })
    return {"eventos": eventos}


COPERNICUS_TIPOS = {"flood": "inundación", "fire": "incendio", "wildfire": "incendio", "storm": "tormenta",
                    "earthquake": "terremoto", "volcano": "volcán", "landslide": "deslizamiento",
                    "humanitarian": "crisis humanitaria", "industrial": "accidente industrial"}


def copernicus(paises):
    """Activaciones de cartografía de emergencia de Copernicus (UE): solo se piden en desastres graves."""
    datos = descargar(COPERNICUS_URL)
    if datos is None:
        return None
    exigir(isinstance(datos.get("results"), list), "no trae 'results'")
    eventos = []
    for a in datos["results"]:
        cuando = fecha(a.get("activationTime"))
        if not cuando or cuando < AHORA - timedelta(days=10):
            continue
        m = re.search(r"POINT \(([-\d.]+) ([-\d.]+)\)", a.get("centroid") or "")
        if not m:
            continue
        lon, lat = float(m.group(1)), float(m.group(2))
        pais_nombre = ((a.get("countries") or [{}])[0]).get("short_name")
        categoria = (a.get("category") or {}).get("slug", "")
        eventos.append({
            "id": "copernicus-" + a.get("code", ""), "tipo": "desastre",
            "titulo": "La UE activa Copernicus: " + COPERNICUS_TIPOS.get(categoria, (a.get("category") or {}).get("name", "emergencia")),
            "lugar": a.get("name", ""), "pais": paises.asignar(pais_nombre, lon, lat), "lat": round(lat, 3),
            "lon": round(lon, 3), "fecha": iso(cuando), "peso": 5, "nivel": "ambar", "fuente": "Copernicus EMS",
            "familia": "oficial", "url": f"https://mapping.emergency.copernicus.eu/activations/{a.get('code', '')}/",
        })
    return {"eventos": eventos}


def emsc(paises):
    """Terremotos del centro sismológico europeo (EMSC) en Europa, el Mediterráneo y Oriente Medio."""
    datos = descargar(EMSC_URL)
    if datos is None:
        return None
    exigir(isinstance(datos.get("features"), list), "no trae 'features'")
    eventos = []
    for f in datos["features"]:
        p = f.get("properties", {})
        try:
            lat, lon, mag = float(p["lat"]), float(p["lon"]), float(p["mag"])
        except (KeyError, TypeError, ValueError):
            continue
        peso = max(mag - 4, 0) ** 2
        eventos.append({
            "id": "emsc-" + str(p.get("unid") or f.get("id")), "tipo": "terremoto",
            "titulo": f"Terremoto de magnitud {mag:.1f}", "lugar": (p.get("flynn_region") or "").title(),
            "pais": paises.asignar(p.get("flynn_region"), lon, lat), "lat": round(lat, 3), "lon": round(lon, 3),
            "fecha": iso(fecha(p.get("time")) or AHORA), "peso": round(peso, 2), "nivel": nivel_por_peso(peso),
            "magnitud": mag, "fuente": "EMSC", "familia": "oficial",
            "url": f"https://www.seismicportal.eu/eventdetails.html?unid={p.get('unid')}",
        })
    return {"eventos": eventos}


def ign(paises):
    """Terremotos del Instituto Geográfico Nacional: España y su entorno, los últimos 10 días."""
    texto = descargar(IGN_URL, como="texto")
    if texto is None:
        return None
    items = xml_items(texto, "IGN")
    eventos = []
    for it in items:
        m = re.search(r"magnitud ([\d.,]+) en (.+?) en la fecha", it.get("description", ""))
        try:
            lat, lon = float(it.get("lat")), float(it.get("long"))
            mag = float(m.group(1).replace(",", ".")) if m else None
        except (TypeError, ValueError):
            continue
        if mag is None or mag < 2.5:
            continue
        lugar = m.group(2).strip().title()
        peso = max(mag - 4, 0) ** 2
        eventos.append({
            "id": "ign-" + normalizar(it.get("link") or it.get("title", ""))[-40:].replace(" ", "-"), "tipo": "terremoto",
            "titulo": f"Terremoto de magnitud {mag:.1f}", "lugar": lugar, "pais": paises.asignar(lugar, lon, lat),
            "lat": round(lat, 3), "lon": round(lon, 3),
            "fecha": iso(fecha(it.get("pubDate")) or AHORA), "peso": round(peso, 2), "nivel": nivel_por_peso(peso),
            "magnitud": mag, "fuente": "IGN", "familia": "oficial", "url": it.get("link"),
        })
    return {"eventos": eventos}


def analisis(paises):
    """Últimos análisis de Elcano, IEEE y CIDOB, con los países que tratan."""
    lista = []
    for centro, url in ANALISIS_URLS.items():
        texto = descargar(url, como="texto", intentos=2)
        if not texto:
            continue
        for it in xml_items(texto, centro):
            titulo = it.get("title", "")
            medio = it.get("source", "")
            if medio and titulo.endswith(" - " + medio):
                titulo = titulo[: -len(medio) - 3]
            quienes = paises.en_texto(titulo)
            if quienes and not normalizar(titulo).startswith(("novedades", "boletin", "agenda")):
                lista.append({"titulo": titulo.strip(), "url": it.get("link"), "centro": centro,
                              "fecha": iso(fecha(it.get("pubDate")) or AHORA), "paises": quienes})
    if not lista:
        return None
    lista.sort(key=lambda a: a["fecha"], reverse=True)
    return {"analisis": lista[:150]}


def cloudflare(paises):
    """Cortes de internet de Cloudflare Radar, con su causa (por ejemplo, ordenados por un gobierno)."""
    if not CLOUDFLARE_TOKEN:
        return {"eventos": [], "desactivada": True}
    datos = descargar(CLOUDFLARE_URL, cabeceras={"Authorization": f"Bearer {CLOUDFLARE_TOKEN}"})
    if datos is None:
        return None
    anotaciones = (datos.get("result") or {}).get("annotations")
    exigir(isinstance(anotaciones, list), "no trae 'result.annotations'")
    eventos = []
    for a in anotaciones:
        causa = ((a.get("outage") or {}).get("outageCause") or "").upper()
        alcance = ((a.get("outage") or {}).get("outageType") or "").upper()
        for cc in a.get("locations") or []:
            a3 = paises.por_a2.get(cc.upper())
            if not a3:
                continue
            gobierno = "GOVERNMENT" in causa
            peso = 12 if gobierno and alcance == "NATIONWIDE" else 8 if gobierno else 3 if alcance == "NATIONWIDE" else 0
            if not peso:
                continue
            lon, lat = paises.centro(a3)
            eventos.append({
                "id": f"cloudflare-{a3}-{a.get('id')}", "tipo": "internet",
                "titulo": "Corte de internet ordenado por el gobierno" if gobierno else "Corte de internet en todo el país",
                "lugar": a.get("description") or "", "pais": a3, "lat": lat, "lon": lon,
                "fecha": iso(fecha(a.get("startDate")) or AHORA), "peso": peso, "nivel": "rojo" if peso >= 12 else "ambar",
                "fuente": "Cloudflare Radar", "familia": "tecnica", "url": f"https://radar.cloudflare.com/{cc.lower()}",
            })
    return {"eventos": eventos}


def ucdp(paises):
    """Muertes en conflictos verificadas por la Universidad de Uppsala (versión mensual, últimos 90 días)."""
    if not UCDP_TOKEN:
        return {"eventos": [], "desactivada": True}
    muertes, url, paginas = {}, UCDP_URL, 0
    while url and paginas < 15:
        datos = descargar(url, cabeceras={"x-ucdp-access-token": UCDP_TOKEN})
        if datos is None:
            return None
        exigir(isinstance(datos.get("Result"), list), "no trae 'Result'")
        for e in datos["Result"]:
            try:
                lat, lon = float(e["latitude"]), float(e["longitude"])
            except (KeyError, TypeError, ValueError):
                continue
            a3 = paises.asignar(e.get("country"), lon, lat)
            if a3:
                muertes[a3] = muertes.get(a3, 0) + int(e.get("best") or 0)
        url, paginas = datos.get("NextPageUrl") or None, paginas + 1
    return {"eventos": [], "ucdp": muertes}


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

# Proporción de violencia a partir de la cual cuenta todo el volumen. Calibrado con datos
# reales: en un país en guerra abierta ronda el 3-7 %; en uno en paz, por debajo del 1 %.
CUOTA_PLENA = 0.05
CLAVES_PUNTOS = ("conflicto", "protestas", "desastres", "internet", "censura", "avisos", "epidemias", "humanitaria",
                 "economia")
PARTE_DE = {"internet": "internet", "censura": "censura", "aviso": "avisos", "epidemia": "epidemias", "crisis": "humanitaria",
            "economia": "economia"}


def aceleracion(g):
    """Cómo cambia la violencia y la protesta entre las 12 h anteriores y las últimas 12 h.
    Devuelve el cociente (1 = igual, 2 = el doble) solo si hay volumen suficiente para fiarse."""
    ahora = g.get("conflicto_12h", 0) + g.get("protesta_12h", 0)
    antes = g.get("conflicto_12h_antes", 0) + g.get("protesta_12h_antes", 0)
    if ahora + antes < 8:
        return None
    return round((ahora + 1) / (antes + 1), 2)


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
        if clave == "desastres":
            c["rango_desastre"] = max(c.get("rango_desastre", 0), RANGO[e["nivel"]])
        if e["peso"] > 0 or e["nivel"] != "verde":
            c["familias"].add(e.get("familia", "oficial"))

    for a3, g in (gdelt_paises or {}).items():
        if not (g["conflicto"] or g["protesta"]):
            continue
        c = base(a3)
        # Proporción de lo que se cuenta del país que es violencia política: corrige que de EE. UU.
        # o Rusia siempre se hable mucho. Hasta 20 hechos, el volumen pesa menos.
        cuota = g["conflicto"] / max(g["total"], 20)
        c["conflicto"] = 3 * math.log2(1 + g["conflicto"]) * min(1.0, cuota / CUOTA_PLENA)
        cuota_p = g["protesta"] / max(g["total"], 20)
        c["protestas"] = 1.5 * math.log2(1 + g["protesta"]) * min(1.0, cuota_p / CUOTA_PLENA)
        c["cuota_violencia"] = round(cuota, 3)
        c["aceleracion"] = aceleracion(g)
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
                         "hechos_violentos": c.get("hechos_violentos", 0), "protestas_n": c.get("protestas_n", 0),
                         "rango_desastre": c.get("rango_desastre", 0), "aceleracion": c.get("aceleracion"),
                         "cuota_protestas": round(c.get("protestas_n", 0) / max((gdelt_paises or {}).get(a3, {}).get("total", 0), 20), 3)}
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
        # El aviso de EE. UU. también refleja su política exterior: solo refuerza lo que ya muestran
        # los datos propios, no colorea un país por sí solo
        if aviso == 4 and actual >= 3:
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
    """Riesgo en los pasos marítimos según los hechos violentos en su zona en las últimas 24 h."""
    resultado = []
    for p in PASOS:
        n = (conteo or {}).get(p["id"], 0)
        nivel = "rojo" if n >= 25 else "ambar" if n >= 6 else "verde"
        resultado.append({**{k: v for k, v in p.items() if k != "zona"}, "hechos": n, "nivel": nivel})
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


# ---------------------------------------------------------------- histórico
# El histórico no se recorta nunca:
#   historico.json          por día y país: [puntuación, nivel (0-2), empeora (0/1)]
#   archivo/AAAA-MM-DD.json la foto del día: niveles, parte, pasos y los eventos más relevantes
#   archivo/indice.json     los días disponibles
# Cada ejecución sobrescribe la foto de hoy, así que se queda la última del día.

EVENTOS_ARCHIVO = 300


def relevancia(e):
    """Orden para quedarse con los eventos que importan en la foto del día."""
    if e["tipo"] in ("conflicto", "protesta"):
        return e.get("menciones", 0) / 10
    return 100 * RANGO.get(e["nivel"], 0) + e.get("peso", 0) + 5


def archivar(alertas, eventos, titulares):
    dir_archivo = SALIDA / "archivo"
    dir_archivo.mkdir(exist_ok=True)

    historico = leer("historico.json", {})
    riesgo = {"bajo": 0, "medio": 1, "alto": 2}
    historico[HOY] = {a3: [p["puntuacion"], RANGO[p["nivel"]], int(p["escalada"]),
                           riesgo.get(p.get("pronostico", {}).get("riesgo"), 0)]
                      for a3, p in alertas["paises"].items()}
    escribir("historico.json", dict(sorted(historico.items())))

    campos_pais = ("nivel", "escalada", "motivos", "confianza", "puntuacion", "media", "tendencia", "escenarios",
                   "pronostico", "region", "espana", "exteriores",
                   "dias_subiendo", "aviso_viaje", "conflicto", "protestas", "desastres", "epidemias",
                   "internet", "avisos", "humanitaria", "cuota_violencia", "hechos_violentos", "protestas_n",
                   "censura", "economia", "analisis", "elecciones", "divisa_caida", "desescalada")
    campos_evento = ("id", "tipo", "titulo", "lugar", "pais", "lat", "lon", "fecha", "nivel", "peso",
                     "magnitud", "menciones", "hechos", "fuente", "url", "estado")
    del_dia = [e for e in eventos if reciente(e, VENTANA_PUNTUACION) or e["tipo"] in ("epidemia", "crisis")]
    del_dia.sort(key=relevancia, reverse=True)
    foto = {
        "fecha": HOY, "actualizado": alertas["actualizado"],
        "paises": {a3: {k: p[k] for k in campos_pais if k in p} for a3, p in alertas["paises"].items()},
        "parte": alertas.get("parte", {}), "pasos": alertas.get("pasos", []), "informe": alertas.get("informe", {}),
        "simulacion": alertas.get("simulacion", {}),
        "eventos": [{k: e[k] for k in campos_evento if k in e} for e in del_dia[:EVENTOS_ARCHIVO]],
        "titulares": titulares[:20],
    }
    (dir_archivo / f"{HOY}.json").write_text(json.dumps(foto, ensure_ascii=False, separators=(",", ":")), "utf-8")
    dias = sorted(f.stem for f in dir_archivo.glob("????-??-??.json"))
    (dir_archivo / "indice.json").write_text(json.dumps({"dias": dias}), "utf-8")


# ---------------------------------------------------------- economía y calendario
# Una moneda que se hunde en pocos días suele adelantarse a protestas, crisis de gobierno o
# escasez. Se guarda una foto diaria de los tipos de cambio frente al dólar.
DIVISAS_URL = "https://open.er-api.com/v6/latest/USD"
CAIDA_DIVISA = 0.08        # depreciación en 7 días a partir de la cual se avisa
CAIDA_DIVISA_GRAVE = 0.15
# Monedas y países que las usan (sin el dólar, el euro y monedas fijadas a ellos sin margen)
DIVISAS = {
    "AFN": ["AFG"], "ALL": ["ALB"], "AMD": ["ARM"], "AOA": ["AGO"], "ARS": ["ARG"], "AZN": ["AZE"],
    "BAM": ["BIH"], "BDT": ["BGD"], "BIF": ["BDI"], "BOB": ["BOL"], "BRL": ["BRA"], "BWP": ["BWA"],
    "BYN": ["BLR"], "CDF": ["COD"], "CLP": ["CHL"], "CNY": ["CHN"], "COP": ["COL"], "CRC": ["CRI"],
    "CUP": ["CUB"], "CZK": ["CZE"], "DOP": ["DOM"], "DZD": ["DZA"], "EGP": ["EGY"], "ETB": ["ETH"],
    "GEL": ["GEO"], "GHS": ["GHA"], "GMD": ["GMB"], "GNF": ["GIN"], "GTQ": ["GTM"], "HNL": ["HND"],
    "HTG": ["HTI"], "HUF": ["HUN"], "IDR": ["IDN"], "ILS": ["ISR", "PSE"], "INR": ["IND"], "IQD": ["IRQ"],
    "IRR": ["IRN"], "JMD": ["JAM"], "KES": ["KEN"], "KGS": ["KGZ"], "KHR": ["KHM"], "KRW": ["KOR"],
    "KZT": ["KAZ"], "LAK": ["LAO"], "LBP": ["LBN"], "LKR": ["LKA"], "LRD": ["LBR"], "LSL": ["LSO"],
    "LYD": ["LBY"], "MAD": ["MAR"], "MDL": ["MDA"], "MGA": ["MDG"], "MKD": ["MKD"], "MMK": ["MMR"],
    "MNT": ["MNG"], "MRU": ["MRT"], "MWK": ["MWI"], "MXN": ["MEX"], "MYR": ["MYS"], "MZN": ["MOZ"],
    "NAD": ["NAM"], "NGN": ["NGA"], "NIO": ["NIC"], "NPR": ["NPL"], "PEN": ["PER"], "PGK": ["PNG"],
    "PHP": ["PHL"], "PKR": ["PAK"], "PLN": ["POL"], "PYG": ["PRY"], "RON": ["ROU"], "RSD": ["SRB"],
    "RUB": ["RUS"], "RWF": ["RWA"], "SDG": ["SDN"], "SLE": ["SLE"], "SOS": ["SOM"], "SRD": ["SUR"],
    "SSP": ["SSD"], "SYP": ["SYR"], "SZL": ["SWZ"], "THB": ["THA"], "TJS": ["TJK"], "TMT": ["TKM"],
    "TND": ["TUN"], "TRY": ["TUR"], "TZS": ["TZA"], "UAH": ["UKR"], "UGX": ["UGA"], "UYU": ["URY"],
    "UZS": ["UZB"], "VES": ["VEN"], "VND": ["VNM"], "XAF": ["CMR", "CAF", "TCD", "COG", "GNQ", "GAB"],
    "XOF": ["BEN", "BFA", "CIV", "GNB", "MLI", "NER", "SEN", "TGO"], "YER": ["YEM"], "ZAR": ["ZAF"],
    "ZMW": ["ZMB"], "ZWG": ["ZWE"], "KPW": ["PRK"], "ERN": ["ERI"], "DJF": ["DJI"], "TWD": ["TWN"],
}


def divisas(paises):
    """Monedas que se deprecian con fuerza frente al dólar en los últimos 7 días."""
    datos = descargar(DIVISAS_URL)
    if datos is None:
        return None
    exigir(datos.get("result") == "success" and isinstance(datos.get("rates"), dict), "respuesta sin tipos de cambio")
    tipos = datos["rates"]
    historial = leer("divisas_historial.json", {})
    historial[HOY] = {m: tipos[m] for m in DIVISAS if m in tipos}
    historial = {d: historial[d] for d in sorted(historial)[-30:]}
    escribir("divisas_historial.json", historial)
    hace7 = (AHORA - timedelta(days=7)).strftime("%Y-%m-%d")
    previos = [d for d in sorted(historial) if d <= hace7]
    eventos, caidas = [], {}
    if not previos:
        return {"eventos": [], "divisas": {}}
    antes = historial[previos[-1]]
    for moneda, usan in DIVISAS.items():
        if moneda not in tipos or not antes.get(moneda):
            continue
        # Más unidades por dólar = la moneda vale menos
        caida = 1 - antes[moneda] / tipos[moneda]
        if caida < CAIDA_DIVISA:
            continue
        for a3 in usan:
            caidas[a3] = round(caida, 3)
            lon, lat = paises.centro(a3)
            eventos.append({
                "id": f"divisa-{moneda}-{a3}-{HOY}", "tipo": "economia",
                "titulo": f"El {moneda} pierde un {round(caida * 100)} % frente al dólar en 7 días",
                "lugar": "", "pais": a3,
                "lat": round(lat, 3), "lon": round(lon, 3), "fecha": iso(AHORA),
                # No es una alerta oficial: el nivel del evento se queda en verde y solo suma puntos
                "peso": 3 if caida >= CAIDA_DIVISA_GRAVE else 1.5, "nivel": "verde",
                "fuente": "Tipos de cambio", "familia": "tecnica", "url": "https://www.exchangerate-api.com/",
            })
    return {"eventos": eventos, "divisas": caidas}


# Elecciones y referendos en los próximos 45 días (Wikidata). Son fechas de riesgo: protestas,
# cortes de internet y crisis de gobierno se concentran alrededor de ellas.
WIKIDATA_URL = "https://query.wikidata.org/sparql"
DIAS_ELECCIONES = 45


def elecciones(paises):
    desde = AHORA.strftime("%Y-%m-%dT00:00:00Z")
    hasta = (AHORA + timedelta(days=DIAS_ELECCIONES)).strftime("%Y-%m-%dT00:00:00Z")
    consulta = f"""SELECT ?e ?eLabel ?fecha ?iso WHERE {{
      VALUES ?tipo {{ wd:Q40231 wd:Q152450 wd:Q858439 wd:Q1076105 wd:Q43109 }}
      ?e wdt:P31/wdt:P279? ?tipo .
      ?e wdt:P585 ?fecha . ?e wdt:P17 ?pais . ?pais wdt:P298 ?iso .
      FILTER(?fecha >= "{desde}"^^xsd:dateTime && ?fecha < "{hasta}"^^xsd:dateTime)
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "es,en". }}
    }} LIMIT 400"""
    datos = descargar(WIKIDATA_URL + "?format=json&query=" + urllib.parse.quote(consulta), intentos=2,
                      cabeceras={"Accept": "application/sparql-results+json"})
    if datos is None:
        return None
    filas = (datos.get("results") or {}).get("bindings")
    exigir(isinstance(filas, list), "respuesta SPARQL sin resultados")
    validos = {p["a3"] for p in json.loads((FIJOS / "paises.json").read_text("utf-8"))}
    lista, vistos = [], set()
    for f in filas:
        a3 = f.get("iso", {}).get("value")
        nombre = f.get("eLabel", {}).get("value", "")
        dia = f.get("fecha", {}).get("value", "")[:10]
        if a3 not in validos or not dia or re.fullmatch(r"Q\d+", nombre) or (a3, nombre) in vistos:
            continue
        vistos.add((a3, nombre))
        lista.append({"pais": a3, "fecha": dia, "nombre": nombre, "url": f.get("e", {}).get("value")})
    lista.sort(key=lambda x: x["fecha"])
    # Como mucho 3 por país (en algunos hay muchas elecciones locales el mismo día)
    por_pais = {}
    lista = [x for x in lista if por_pais.setdefault(x["pais"], []).append(x) or len(por_pais[x["pais"]]) <= 3]
    return {"elecciones": lista}


# --------------------------------------------------------------------- main

FUENTES = [("USGS", usgs), ("EMSC", emsc), ("IGN", ign), ("GDACS", gdacs), ("Copernicus EMS", copernicus),
           ("NASA EONET", eonet), ("GDELT", gdelt), ("Titulares", titulares), ("Análisis", analisis),
           ("IODA", ioda), ("Cloudflare Radar", cloudflare), ("OONI", ooni), ("Exteriores (España)", exteriores),
           ("Avisos de viaje EE. UU.", avisos_viaje), ("OMS", oms), ("ReliefWeb", reliefweb), ("UCDP", ucdp),
           ("Tipos de cambio", divisas), ("Elecciones (Wikidata)", elecciones)]
# Fuentes que no aportan eventos sino otros datos: si fallan, se conservan esos datos
DATOS_DE_FUENTE = {"Titulares": "titulares", "Análisis": "analisis", "Elecciones (Wikidata)": "elecciones"}


def sin_duplicados_sismicos(eventos):
    """El mismo terremoto puede llegar de USGS, EMSC e IGN: se queda el de la fuente preferida."""
    orden = {"USGS": 0, "EMSC": 1, "IGN": 2}
    sismos = sorted((e for e in eventos if e["tipo"] == "terremoto"), key=lambda e: orden.get(e["fuente"], 3))
    elegidos = []
    for e in sismos:
        t = fecha(e["fecha"]) or AHORA
        if not any(abs(((fecha(x["fecha"]) or AHORA) - t).total_seconds()) < 120
                   and distancia_km(e["lon"], e["lat"], x["lon"], x["lat"]) < 100 for x in elegidos):
            elegidos.append(e)
    return [e for e in eventos if e["tipo"] != "terremoto"] + elegidos


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
            if nombre in DATOS_DE_FUENTE:
                resultado = {DATOS_DE_FUENTE[nombre]: anterior.get(DATOS_DE_FUENTE[nombre], [])}
        cuantos = len(resultado.get("eventos", resultado.get(DATOS_DE_FUENTE.get(nombre, ""), [])))
        estado[nombre] = {"ok": not error, "error": error, "eventos": cuantos,
                          "fallos_seguidos": (previo.get("fallos_seguidos", 0) + 1) if error else 0,
                          "ultimo_ok": iso(AHORA) if not error else previo.get("ultimo_ok")}
        eventos.extend(resultado.get("eventos", []))
        extra.update({k: v for k, v in resultado.items() if k != "eventos"})

    eventos = [e for e in eventos if reciente(e, VENTANA_EPIDEMIAS if e["tipo"] in ("epidemia", "crisis") else VENTANA_MAPA)
               or e["tipo"] == "crisis"]
    eventos = sin_duplicados_sismicos(eventos)
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

    # Capa de análisis: escenarios, pronóstico, contagio regional e interés para España
    ctx = {"gdelt": gdelt_paises, "pasos": {p["id"]: p["nivel"] for p in alertas["pasos"]},
           "vecinos": inteligencia.calcular_vecinos(paises),
           "golpe_en_prensa": {a for t in extra.get("titulares", []) if re.search(r"golpe de estado|golpista|asonada", normalizar(t["titulo"]))
                               for a in t.get("paises", [])},
           "tregua_en_prensa": {a for t in extra.get("titulares", [])
                                if re.search(r"alto el fuego|tregua|negociacion(es)? de paz|acuerdo de paz|cese de hostilidades|desescalada",
                                             normalizar(t["titulo"]))
                                for a in t.get("paises", [])},
           "ucdp": extra.get("ucdp") or anterior.get("ucdp") or {},
           "divisas": extra.get("divisas", anterior.get("divisas") or {}),
           "elecciones": {},
           "reconstruidos": leer("retroceso.json", {}).get("dias", []),
           "exteriores": extra.get("exteriores") or leer("exteriores.json", {}).get("paises") and
           {a: {"nivel": f["nivel"], "texto": EXTERIORES_NIVELES[f["nivel"]], "actualizacion": f.get("actualizacion"),
                "notas": f.get("notas", "")[:400], "url": f.get("url")} for a, f in leer("exteriores.json", {}).get("paises", {}).items()} or {}}
    for a3, f in ctx["exteriores"].items():
        p = alertas["paises"].get(a3)
        # La recomendación de España pesa como la de EE. UU.: refuerza, no colorea sola
        if p and f["nivel"] >= 4 and p["puntuacion"] >= 3 and p["nivel"] == "verde":
            p["nivel"] = "ambar"
            p["motivos"].append("Exteriores desaconseja viajar")
        elif p and f["nivel"] >= 4:
            p["motivos"].append("Exteriores desaconseja viajar")
    for a3, n in ctx["ucdp"].items():
        p = alertas["paises"].get(a3)
        if p and n >= 25:
            p["motivos"].append(f"{n} muertes verificadas en 90 días (UCDP)")
            if n >= 1000:
                p["nivel"] = "rojo"
            elif n >= 100 and p["nivel"] == "verde":
                p["nivel"] = "ambar"
            if "academica" not in p.get("familias", []):
                p["familias"] = p.get("familias", []) + ["academica"]
                p["confianza"] = confianza(p["familias"])
    for x in extra.get("elecciones", []):
        ctx["elecciones"].setdefault(x["pais"], []).append(x)
    intereses = json.loads((FIJOS / "intereses_espana.json").read_text("utf-8"))
    inteligencia.enriquecer(alertas, ctx, intereses, leer("historico.json", {}))

    escribir("eventos.json", {"actualizado": iso(AHORA), "fuentes": estado, "eventos": eventos,
                              "titulares": extra.get("titulares", []), "analisis": extra.get("analisis", []),
                              "ucdp": ctx["ucdp"], "divisas": ctx["divisas"],
                              "elecciones": extra.get("elecciones", []),
                              "gdelt_paises": gdelt_paises, "gdelt_pasos": gdelt_pasos})
    escribir("alertas.json", alertas)
    escribir("historial.json", historial)
    archivar(alertas, eventos, extra.get("titulares", []))
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
