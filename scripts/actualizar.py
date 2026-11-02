#!/usr/bin/env python3
"""Descarga los datos de las fuentes públicas, los normaliza y calcula el nivel
de alerta de cada país. Solo usa la biblioteca estándar de Python.

Lee de data/ (fijos, en main):
  paises.json, mundo.geojson
Escribe en $ATALAYA_SALIDA (por defecto data/; en la Action, la rama `datos`):
  eventos.json    eventos geolocalizados, titulares y estado de cada fuente
  alertas.json    nivel de alerta por país
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
VENTANA_PUNTUACION = timedelta(hours=48)   # qué cuenta para el nivel de hoy
VENTANA_MAPA = timedelta(days=7)           # qué se pinta en el mapa
DIAS_HISTORIAL = 30
DIAS_CALIBRADO = 7                         # días de historial antes de fiarse de la anomalía
FALLOS_PARA_AVISAR = 6                     # ejecuciones seguidas (3 h) antes de abrir un issue

USGS_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_week.geojson"
GDACS_URL = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH?" + urllib.parse.urlencode({
    "eventlist": "TC;FL;VO;DR;WF;TS", "alertlevel": "Green;Orange;Red",
    "fromDate": (AHORA - VENTANA_MAPA).strftime("%Y-%m-%d"), "toDate": AHORA.strftime("%Y-%m-%d")}, safe=";")
EONET_URL = "https://eonet.gsfc.nasa.gov/api/v3/events?status=open&days=7"
GDELT_ULTIMO_URL = "http://data.gdeltproject.org/gdeltv2/lastupdate.txt"
GDELT_FICHERO_URL = "http://data.gdeltproject.org/gdeltv2/{}.export.CSV.zip"
GDELT_FICHEROS = 96                        # 24 h de ficheros de 15 minutos
GDELT_DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc?" + urllib.parse.urlencode({
    "query": '(airstrike OR shelling OR missile OR bombing OR clashes OR "armed conflict" OR coup) sourcelang:spanish',
    "mode": "artlist", "format": "json", "maxrecords": "60", "timespan": "24h", "sort": "hybridrel"})
IODA_URL = "https://api.ioda.inetintel.cc.gatech.edu/v2/outages/summary?" + urllib.parse.urlencode({
    "from": int((AHORA - timedelta(hours=24)).timestamp()), "until": int(AHORA.timestamp()), "entityType": "country"})
AVISOS_URL = "https://travel.state.gov/_res/rss/TAsTWs.xml"


class FormatoInesperado(Exception):
    """La fuente respondió, pero no con la forma que esperamos."""


# ---------------------------------------------------------------- utilidades

def log(*a):
    print(*a, file=sys.stderr, flush=True)


def descargar(url, como="json", intentos=3, espera=6):
    """Devuelve el contenido o None si la fuente no responde tras varios intentos."""
    req = urllib.request.Request(url, headers={"User-Agent": "atalaya/1.0 (+https://github.com/serbenda/atalaya)"})
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
                "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            return datetime.strptime(t, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    try:
        return parsedate_to_datetime(t).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


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
        partes = [normalizar(x) for x in re.split(r"[,;]| - ", texto)]
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
        partes = [normalizar(x) for x in re.split(r"[,;]| - ", nombre or "")]
        for x in partes:
            if x in TERRITORIOS:
                return TERRITORIOS[x]
        return self.punto(lon, lat) or self.nombre(nombre)


# ------------------------------------------------------------------ fuentes
# Cada fuente devuelve un dict con "eventos" (y opcionalmente "paises" con datos agregados),
# None si no responde, o lanza FormatoInesperado si responde con otra forma.

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
            "fuente": "USGS", "url": p.get("url"),
        })
    return {"eventos": eventos}


GDACS_TIPOS = {"TC": "Ciclón tropical", "FL": "Inundación", "VO": "Erupción volcánica",
               "DR": "Sequía", "WF": "Incendio forestal", "TS": "Tsunami"}


def gdacs(paises):
    datos = descargar(GDACS_URL)
    if datos is None:
        return None
    if datos == {}:  # GDACS responde vacío cuando no hay eventos
        return {"eventos": []}
    exigir(isinstance(datos.get("features"), list), "no trae 'features'")
    eventos, vistos = [], set()
    for f in datos["features"]:
        p = f.get("properties", {})
        tipo = p.get("eventtype")
        geo = f.get("geometry") or {}
        if tipo not in GDACS_TIPOS or geo.get("type") != "Point":
            continue
        clave = f"gdacs-{tipo}-{p.get('eventid')}"
        if clave in vistos:  # un ciclón aparece una vez por episodio: nos quedamos con el último
            continue
        vistos.add(clave)
        lon, lat = geo["coordinates"][:2]
        alerta = (p.get("alertlevel") or "Green").lower()
        peso = {"green": 1, "orange": 6, "red": 15}.get(alerta, 1)
        url = p.get("url") or {}
        eventos.append({
            "id": clave, "tipo": "desastre",
            "titulo": GDACS_TIPOS[tipo] + (f" {p['name'].split()[-1].title()}" if p.get("name") and tipo == "TC" else ""),
            "lugar": p.get("country") or p.get("name") or "",
            "pais": (p.get("iso3") or "").upper()[:3] or paises.asignar(p.get("country"), lon, lat),
            "lat": round(lat, 3), "lon": round(lon, 3),
            "fecha": iso(fecha(p.get("todate")) or fecha(p.get("fromdate")) or AHORA),
            "peso": peso, "nivel": {"green": "verde", "orange": "ambar", "red": "rojo"}.get(alerta, "verde"),
            "fuente": "GDACS", "url": url.get("report") if isinstance(url, dict) else None,
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
            "peso": info[1], "nivel": "verde", "fuente": "NASA EONET",
            "url": ((e.get("sources") or [{}])[0]).get("url") or e.get("link"),
        })
    return {"eventos": eventos}


# Columnas del fichero de eventos de GDELT 2.0 (61 columnas separadas por tabuladores)
G_FECHA, G_RAIZ, G_ARTICULOS = 59, 28, 33
G_GEO_TIPO, G_GEO_NOMBRE, G_GEO_LAT, G_GEO_LON, G_URL = 51, 52, 56, 57, 60
# Códigos CAMEO raíz: 14 protestas; 18 agresiones, 19 combates, 20 violencia masiva
GDELT_VIOLENCIA = {"18", "19", "20"}
GDELT_PROTESTA = {"14"}


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
    """Agrega los eventos de GDELT de las últimas 24 h por lugar y por país."""
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
    for f in filas:
        if len(f) < 61 or not f[G_GEO_LAT] or not f[G_GEO_LON]:
            continue
        try:
            lat, lon = float(f[G_GEO_LAT]), float(f[G_GEO_LON])
            articulos = int(f[G_ARTICULOS] or 1)
        except ValueError:
            continue
        pais = paises.asignar(f[G_GEO_NOMBRE], lon, lat)
        if not pais:
            continue
        raiz = f[G_RAIZ]
        tipo = "conflicto" if raiz in GDELT_VIOLENCIA else "protesta" if raiz in GDELT_PROTESTA else None
        agg = por_pais.setdefault(pais, {"total": 0, "conflicto": 0, "protesta": 0})
        agg["total"] += 1
        if not tipo:
            continue
        agg[tipo] += 1
        # El tipo 1 es "solo el país": son puntos en el centro del país, poco útiles en el mapa
        if f[G_GEO_TIPO] == "1":
            continue
        clave = (tipo, f[G_GEO_NOMBRE], round(lat, 1), round(lon, 1))
        l = lugares.setdefault(clave, {"hechos": 0, "menciones": 0, "urls": [], "fecha": "", "pais": pais,
                                       "lat": lat, "lon": lon})
        l["hechos"] += 1
        l["menciones"] += articulos
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
            "peso": 0, "nivel": "verde", "fuente": "GDELT", "url": l["urls"][0] if l["urls"] else None,
            "enlaces": l["urls"],
        })
    return {"eventos": eventos, "paises": por_pais}


def gdelt_titulares(paises=None):
    # La API DOC limita mucho a las IP compartidas de GitHub (429): más intentos y más espaciados
    datos = descargar(GDELT_DOC_URL, intentos=4, espera=15)
    if datos is None:
        return None
    if datos == {}:
        return {"titulares": []}
    exigir(isinstance(datos.get("articles", []), list), "no trae 'articles'")
    vistos, titulares = set(), []
    for a in datos.get("articles", []):
        clave = normalizar(a.get("title"))[:70]
        if not clave or clave in vistos:
            continue
        vistos.add(clave)
        titulares.append({"titulo": a.get("title", "").strip(), "url": a.get("url"),
                          "medio": a.get("domain"), "fecha": iso(fecha(a.get("seendate")) or AHORA)})
    return {"titulares": titulares[:40]}


def ioda(paises):
    """Cortes de internet detectados por IODA (Georgia Tech) en las últimas 24 h."""
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
        if puntuacion <= 0:
            continue
        # La puntuación de IODA crece en órdenes de magnitud: se usa su logaritmo
        peso = round(min(15.0, 2.5 * math.log10(1 + puntuacion)), 1)
        lon, lat = paises.centros[a3]
        eventos.append({
            "id": f"ioda-{a3}", "tipo": "internet", "titulo": "Corte de internet",
            "lugar": entidad.get("name") or a3, "pais": a3, "lat": lat, "lon": lon,
            "fecha": iso(AHORA), "peso": peso, "nivel": nivel_por_peso(peso),
            "cortes": item.get("event_cnt"), "fuente": "IODA",
            "url": f"https://ioda.inetintel.cc.gatech.edu/country/{entidad.get('code')}",
        })
    return {"eventos": eventos}


AVISO_NIVELES = {1: "precauciones normales", 2: "más precaución", 3: "reconsiderar el viaje", 4: "no viajar"}


def avisos_viaje(paises):
    """Avisos de viaje del Departamento de Estado de EE. UU. Lo que cuenta es que suban de nivel."""
    texto = descargar(AVISOS_URL, como="texto")
    if texto is None:
        return None
    try:
        raiz = ET.fromstring(texto)
    except ET.ParseError as e:
        raise FormatoInesperado(f"el RSS no es XML válido: {e}") from e
    items = raiz.findall(".//item")
    exigir(items, "el RSS no tiene elementos")
    previos = leer("avisos.json", {"niveles": {}, "cambios": []})
    niveles, cambios = {}, [c for c in previos.get("cambios", []) if (fecha(c["fecha"]) or AHORA) >= AHORA - VENTANA_MAPA]
    for it in items:
        titulo = (it.findtext("title") or "").strip()
        m = re.match(r"(.+?)\s+-\s+Level\s+(\d)", titulo)
        if not m:
            continue
        a3 = paises.nombre(m.group(1))
        if not a3:
            continue
        nivel = int(m.group(2))
        niveles[a3] = max(nivel, niveles.get(a3, 0))
        anterior = previos.get("niveles", {}).get(a3)
        if anterior and nivel != anterior and not any(c["pais"] == a3 and c["a"] == nivel for c in cambios):
            cambios.append({"pais": a3, "de": anterior, "a": nivel, "url": it.findtext("link"),
                            "fecha": iso(fecha(it.findtext("pubDate")) or AHORA)})
    escribir("avisos.json", {"actualizado": iso(AHORA), "niveles": niveles, "cambios": cambios})
    eventos = []
    for c in cambios:
        sube = c["a"] > c["de"]
        lon, lat = paises.centros.get(c["pais"], (0, 0))
        peso = 4 * (c["a"] - c["de"]) if sube else 0
        eventos.append({
            "id": f"aviso-{c['pais']}-{c['a']}", "tipo": "aviso",
            "titulo": f"EE. UU. {'sube' if sube else 'baja'} su aviso de viaje a nivel {c['a']} ({AVISO_NIVELES[c['a']]})",
            "lugar": "", "pais": c["pais"], "lat": lat, "lon": lon, "fecha": c["fecha"], "peso": peso,
            "nivel": "ambar" if sube and c["a"] >= 3 else "verde", "fuente": "Avisos de viaje EE. UU.", "url": c["url"],
        })
    return {"eventos": eventos, "avisos": niveles}


# ----------------------------------------------------------------- alertas

def puntuar(eventos, gdelt_paises):
    """Puntuación de cada país con lo ocurrido en las últimas 48 h."""
    limite = AHORA - VENTANA_PUNTUACION
    comp = {}

    def base(a3):
        return comp.setdefault(a3, {"desastres": 0.0, "internet": 0.0, "avisos": 0.0, "eventos": 0, "rango": 0})

    for e in eventos:
        if not e.get("pais") or e["tipo"] in ("conflicto", "protesta") or (fecha(e["fecha"]) or AHORA) < limite:
            continue
        c = base(e["pais"])
        c["eventos"] += 1
        c["rango"] = max(c["rango"], RANGO[e["nivel"]])
        clave = {"internet": "internet", "aviso": "avisos"}.get(e["tipo"], "desastres")
        c[clave] += e["peso"]

    for a3, g in (gdelt_paises or {}).items():
        if not (g["conflicto"] or g["protesta"]):
            continue
        c = base(a3)
        # Proporción de lo que se cuenta del país que es violencia: corrige que de EE. UU. o
        # Rusia siempre se hable mucho. Hasta 20 eventos, el volumen pesa menos.
        cuota = g["conflicto"] / max(g["total"], 20)
        c["conflicto"] = 3 * math.log2(1 + g["conflicto"]) * min(1.0, cuota / 0.15)
        cuota_p = g["protesta"] / max(g["total"], 20)
        c["protestas"] = 1.5 * math.log2(1 + g["protesta"]) * min(1.0, cuota_p / 0.1)
        c["cuota_violencia"] = round(cuota, 3)
        c["hechos_violentos"] = g["conflicto"]
        c["protestas_n"] = g["protesta"]

    resultado = {}
    for a3, c in comp.items():
        partes = {k: round(c.get(k, 0), 1) for k in ("desastres", "conflicto", "protestas", "internet", "avisos")}
        resultado[a3] = {**partes, "puntuacion": round(sum(partes.values()), 1), "eventos": c["eventos"],
                         "rango_evento": c["rango"], "cuota_violencia": c.get("cuota_violencia", 0),
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


def calcular_alertas(puntos, historial, avisos=None):
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
        subiendo = dias_subiendo(serie + [actual])
        # Un evento oficial en ámbar o rojo (GDACS, USGS, IODA) fija el nivel mínimo del país
        rango_evento = puntos.get(a3, {}).get("rango_evento", 0)
        if actual >= 35 or rango_evento == 2 or (not calibrando and z >= 3 and actual >= 15):
            nivel = "rojo"
        elif (actual >= 18 or rango_evento == 1 or (not calibrando and z >= 1.5 and actual >= 8)
              or (subiendo >= 3 and actual >= 8)):
            nivel = "ambar"
        elif actual > 0:
            nivel = "verde"
        else:
            continue
        tendencia = "sube" if z >= 1 or subiendo >= 3 else "baja" if z <= -1 else "estable"
        p = {k: v for k, v in puntos.get(a3, {}).items() if k not in ("puntuacion", "rango_evento")}
        paises[a3] = {"nivel": nivel, "puntuacion": actual, "media": round(media, 1), "z": round(z, 2),
                      "tendencia": tendencia if serie else "sin datos", "dias_subiendo": subiendo,
                      "ayer": serie[-1] if serie else None, "serie": serie + [actual], **p}
        if avisos and a3 in avisos:
            paises[a3]["aviso_viaje"] = avisos[a3]
    return {"actualizado": iso(AHORA), "calibrando": calibrando, "dias_historial": len(previos), "paises": paises}


# --------------------------------------------------------------------- main

FUENTES = [("USGS", usgs), ("GDACS", gdacs), ("NASA EONET", eonet), ("GDELT", gdelt),
           ("GDELT titulares", gdelt_titulares), ("IODA", ioda), ("Avisos de viaje EE. UU.", avisos_viaje)]


def main():
    SALIDA.mkdir(parents=True, exist_ok=True)
    anterior = leer("eventos.json", {"eventos": [], "titulares": [], "fuentes": {}})
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
        previo = (anterior.get("fuentes") or {}).get(nombre, {})
        if error:
            log(f"  {nombre}: {error}")
            # Se conservan los últimos datos buenos de la fuente
            resultado = {"eventos": [e for e in anterior["eventos"] if e.get("fuente") == nombre]}
            if nombre == "GDELT titulares":
                resultado = {"titulares": anterior.get("titulares", [])}
        estado[nombre] = {"ok": not error, "error": error, "eventos": len(resultado.get("eventos", resultado.get("titulares", []))),
                          "fallos_seguidos": (previo.get("fallos_seguidos", 0) + 1) if error else 0,
                          "ultimo_ok": iso(AHORA) if not error else previo.get("ultimo_ok")}
        eventos.extend(resultado.get("eventos", []))
        extra.update({k: v for k, v in resultado.items() if k != "eventos"})

    limite = AHORA - VENTANA_MAPA
    eventos = [e for e in eventos if (fecha(e["fecha"]) or AHORA) >= limite]
    eventos.sort(key=lambda e: e["fecha"], reverse=True)

    # Si GDELT falla, sin sus agregados por país la puntuación de conflicto caería a cero:
    # se reutilizan los de la última vez
    gdelt_paises = extra.get("paises") or anterior.get("gdelt_paises") or {}
    puntos = puntuar(eventos, gdelt_paises)
    historial = leer("historial.json", {})
    hoy = AHORA.strftime("%Y-%m-%d")
    dia = historial.setdefault(hoy, {})
    for a3, p in puntos.items():
        dia[a3] = max(dia.get(a3, 0), p["puntuacion"])
    historial = {d: historial[d] for d in sorted(historial)[-(DIAS_HISTORIAL + 1):]}

    escribir("eventos.json", {"actualizado": iso(AHORA), "fuentes": estado, "eventos": eventos,
                              "titulares": extra.get("titulares", []), "gdelt_paises": gdelt_paises})
    escribir("alertas.json", calcular_alertas(puntos, historial, extra.get("avisos") or leer("avisos.json", {}).get("niveles")))
    escribir("historial.json", historial)
    log("Listo:", {k: ("ok" if v["ok"] else v["error"]) + f" ({v['eventos']})" for k, v in estado.items()})
    if not any(v["ok"] for v in estado.values()):
        sys.exit("Ninguna fuente respondió")


if __name__ == "__main__":
    main()
