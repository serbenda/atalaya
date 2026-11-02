"""Sondeo temporal: comprueba qué devuelven las fuentes candidatas."""
import re, urllib.request, ssl
from datetime import date, timedelta
hoy = date.today(); hace7 = hoy - timedelta(days=7)
URLS = [
  "https://www.exteriores.gob.es/es/ServiciosAlCiudadano/Paginas/Recomendaciones-de-viaje.aspx",
  "https://www.exteriores.gob.es/es/ServiciosAlCiudadano/SiViajasAlExtranjero/Paginas/RecomendacionesDeViaje.aspx",
  f"https://api.ooni.io/api/v1/aggregation?test_name=whatsapp&since={hace7}&until={hoy}&axis_x=probe_cc",
  "https://emergency.copernicus.eu/mapping/activations-rapid/feed",
  "https://emergency.copernicus.eu/mapping/georss-feeds-aggregated",
  "https://mapping.emergency.copernicus.eu/activations/api/activations/?limit=3",
  "https://rapidmapping.emergency.copernicus.eu/backend/dashboard-api/public-activations/?limit=3",
  "https://www.seismicportal.eu/fdsnws/event/1/query?format=json&limit=2&minmag=4",
  "http://www.ign.es/ign/RssTools/sismologia.xml",
  "https://www.realinstitutoelcano.org/feed/",
  "https://www.realinstitutoelcano.org/analisis/feed/",
  "https://www.ieee.es/",
  "https://www.cidob.org/feed",
  "https://www.cidob.org/rss.xml",
  "https://efe.com/feed/",
  "https://efe.com/mundo/feed/",
  "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/internacional/portada",
  "https://www.rtve.es/noticias/internacional/",
  "https://api2.rtve.es/rss/temas_internacional.xml",
  "https://api.cloudflare.com/client/v4/radar/annotations/outages?dateRange=1d&format=json",
]
for u in URLS:
    print("=" * 100); print(u)
    try:
        req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 (compatible; atalaya/1.0)"})
        with urllib.request.urlopen(req, timeout=40) as r:
            b = r.read(); print("OK", r.status, r.headers.get("content-type"), len(b))
    except urllib.error.HTTPError as e:
        b = e.read(); print("HTTP", e.code)
    except Exception as e:
        print("ERROR", e); continue
    t = b.decode("utf-8", "replace")
    print(re.sub(r"\s+", " ", t[:700]))
    enlaces = sorted(set(re.findall(r'href="([^"]*(?:rss|feed|ecomendacion|Recomendacion|\.xml)[^"]*)"', t)))[:25]
    for e in enlaces: print("  link:", e)
    if "exteriores" in u:
        for m in re.findall(r'href="([^"]*(?:trc=|Detalle|ficha|Fichas)[^"]*)"', t)[:15]: print("  pais:", m)
        print("  muestra:", re.sub(r"\s+"," ", t[len(t)//2:len(t)//2+1500]))
