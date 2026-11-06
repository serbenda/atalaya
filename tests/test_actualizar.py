"""Pruebas del script de actualización con respuestas de ejemplo de cada fuente.

Si una fuente cambia de formato, estas pruebas no lo detectan (usan ejemplos fijos),
pero la Action sí: marca la fuente con "formato inesperado" y abre un issue.
Lo que aseguran es que el procesado y el cálculo de alertas hacen lo que deben.
"""

import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.parse
import zipfile
from datetime import timedelta
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
TMP = tempfile.mkdtemp()
os.environ["ATALAYA_SALIDA"] = TMP
os.environ.pop("RELIEFWEB_APPNAME", None)

spec = importlib.util.spec_from_file_location("actualizar", RAIZ / "scripts" / "actualizar.py")
act = importlib.util.module_from_spec(spec)
sys.modules["actualizar"] = act
spec.loader.exec_module(act)

AHORA = act.AHORA
MS = int(AHORA.timestamp() * 1000)
RFC822 = AHORA.strftime("%a, %d %b %Y %H:%M:%S GMT")


_NUM_URL = iter(range(10 ** 6))


def fila_gdelt(raiz, nombre, lat, lon, articulos=5, tipo="4", url=None, actor="MIL", principal="1",
               paises=("", ""), base=None, actores=("", "")):
    f = [""] * 61
    url = url or f"https://medio/{next(_NUM_URL)}"
    f[act.G_BASE] = base or raiz + "0"
    f[act.G_A1_NOMBRE], f[act.G_A2_NOMBRE] = actores
    f[act.G_A1_PAIS], f[act.G_A2_PAIS] = paises
    f[act.G_RAIZ] = raiz
    f[act.G_RAIZ_EVENTO] = principal
    f[act.G_A1_TIPOS[0]] = actor
    f[act.G_ARTICULOS] = str(articulos)
    f[act.G_FUENTES] = "2"
    f[act.G_GEO_TIPO] = tipo
    f[act.G_GEO_NOMBRE] = nombre
    f[act.G_GEO_LAT] = str(lat)
    f[act.G_GEO_LON] = str(lon)
    f[act.G_FECHA] = AHORA.strftime("%Y%m%d%H%M%S")
    f[act.G_URL] = url
    return f


def zip_gdelt(filas):
    texto = "\n".join("\t".join(f) for f in filas)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("x.export.CSV", texto)
    return buf.getvalue()


FILAS_GDELT = (
    [fila_gdelt("19", "Kharkiv, Kharkivs'ka Oblast', Ukraine", 49.99, 36.23, url=f"https://m/{i}") for i in range(40)]
    + [fila_gdelt("04", "Kyiv, Kyyiv, Misto, Ukraine", 50.45, 30.52) for _ in range(60)]
    # Delincuencia común en EE. UU.: violencia sin actores políticos, no debe contar
    + [fila_gdelt("19", "New York, United States", 40.71, -74.0, actor="CRM") for _ in range(30)]
    + [fila_gdelt("19", "Washington, District of Columbia, United States", 38.9, -77.03) for _ in range(10)]
    + [fila_gdelt("04", "Washington, District of Columbia, United States", 38.9, -77.03) for _ in range(400)]
    + [fila_gdelt("14", "Nairobi, Nairobi Area, Kenya", -1.28, 36.82, actor="") for _ in range(12)]
    + [fila_gdelt("04", "Nairobi, Nairobi Area, Kenya", -1.28, 36.82) for _ in range(20)]
    + [fila_gdelt("18", "Gaza, Israel (general), Israel", 31.5, 34.47) for _ in range(15)]
    # Ataque de un país a otro sin tipo de actor: sí es violencia política
    + [fila_gdelt("19", "Odesa, Odes'ka Oblast', Ukraine", 46.48, 30.73, actor="", paises=("RUS", "UKR")) for _ in range(5)]
    # Mención de pasada (no es el hecho principal de la noticia): no debe contar
    + [fila_gdelt("19", "Lima, Lima, Peru", -12.05, -77.04, principal="0") for _ in range(30)]
    # Cerca del estrecho de Ormuz y de Bab el-Mandeb
    + [fila_gdelt("19", "Bandar Abbas, Hormozgan, Iran", 27.18, 56.27) for _ in range(8)]
    + [fila_gdelt("18", "Al Hudaydah, Yemen", 14.8, 42.95) for _ in range(30)]
    # Gaza está a 200 km de Suez, pero no es la ruta del canal
    + [fila_gdelt("19", "Gaza City, Gaza Strip", 31.5, 34.45) for _ in range(20)]
)

GDACS_RSS = f"""<?xml version="1.0"?>
<rss xmlns:gdacs="http://www.gdacs.org" xmlns:geo="http://www.w3.org/2003/01/geo/wgs84_pos#"><channel>
  <item><title>Red alert for tropical cyclone KALMAEGI-25</title><link>https://g/1</link>
    <gdacs:eventtype>TC</gdacs:eventtype><gdacs:eventid>1</gdacs:eventid><gdacs:eventname>KALMAEGI-25</gdacs:eventname>
    <gdacs:alertlevel>Red</gdacs:alertlevel><gdacs:iso3>PHL</gdacs:iso3><gdacs:country>Philippines</gdacs:country>
    <gdacs:todate>{RFC822}</gdacs:todate><geo:Point><geo:lat>14.0</geo:lat><geo:long>125.0</geo:long></geo:Point></item>
  <item><title>Orange (dup)</title><gdacs:eventtype>TC</gdacs:eventtype><gdacs:eventid>1</gdacs:eventid>
    <geo:Point><geo:lat>14.0</geo:lat><geo:long>125.0</geo:long></geo:Point></item>
  <item><title>Earthquake</title><gdacs:eventtype>EQ</gdacs:eventtype><gdacs:eventid>9</gdacs:eventid>
    <geo:Point><geo:lat>1</geo:lat><geo:long>1</geo:long></geo:Point></item>
</channel></rss>"""

RESPUESTAS = {
    "earthquake.usgs.gov": {"features": [
        {"id": "a", "properties": {"mag": 6.8, "place": "120 km SSW of Kokopo, Papua New Guinea", "time": MS,
                                   "url": "u", "alert": "orange"}, "geometry": {"coordinates": [151.9, -5.2, 30]}},
        {"id": "b", "properties": {"mag": 4.6, "place": "Fiji region", "time": MS, "url": "u", "alert": None},
         "geometry": {"coordinates": [-178.2, -18.1, 500]}}]},
    "gdacs.org": GDACS_RSS,
    "eonet.gsfc.nasa.gov": {"events": [
        {"id": "E1", "title": "Etna", "categories": [{"id": "volcanoes"}], "sources": [],
         "geometry": [{"date": act.iso(AHORA), "type": "Point", "coordinates": [15.0, 37.75]}]}]},
    "lastupdate.txt": "1 a http://data.gdeltproject.org/gdeltv2/20261102081500.export.CSV.zip\n",
    "export.CSV.zip": zip_gdelt(FILAS_GDELT),
    "news.google.com": f"""<?xml version="1.0"?><rss><channel>
        <item><title>Nuevo ataque ruso con drones en Járkov - EL PAÍS</title><link>https://m/1</link><pubDate>{RFC822}</pubDate>
              <source url="https://elpais.com">EL PAÍS</source></item>
        <item><title>2 de noviembre de 1937: el bombardeo de Lleida - La Vanguardia</title><link>https://m/3</link>
              <pubDate>{RFC822}</pubDate><source url="https://lavanguardia.com">La Vanguardia</source></item>
        <item><title>Nuevo ataque ruso con drones en Járkov - ABC</title><link>https://m/2</link><pubDate>{RFC822}</pubDate>
              <source url="https://abc.es">ABC</source></item></channel></rss>""",
    "ioda": {"data": [
        {"entity": {"code": "IR", "name": "Iran", "type": "country"}, "scores": {"overall": 5e7}, "event_cnt": 3},
        {"entity": {"code": "FI", "name": "Finland"}, "scores": {"overall": 40000}, "event_cnt": 1},
        {"entity": {"code": "ES", "name": "Spain"}, "scores": {"overall": 0}}]},
    "travel.state.gov": """<?xml version="1.0"?><rss><channel>
        <item><title>Lebanon - Level 4: Do Not Travel</title><link>https://t/lb</link>
              <pubDate>Mon, 02 Nov 2026 08:00:00 GMT</pubDate></item>
        <item><title>Sudan - Level 4: Do Not Travel</title><link>https://t/sd</link></item>
        <item><title>Spain - Level 2: Exercise Increased Caution</title><link>https://t/es</link></item>
        <item><title>Travel Advisory Updates</title></item></channel></rss>""",
    "who.int": {"value": [
        {"Title": "Marburg virus disease - Ethiopia", "PublicationDateAndTime": act.iso(AHORA - timedelta(days=3)),
         "UrlName": "2026-DON999"},
        {"Title": "Avian Influenza A(H9N2) - China", "PublicationDateAndTime": act.iso(AHORA - timedelta(days=5)),
         "UrlName": "2026-DON998"},
        {"Title": "Cholera - Global situation", "PublicationDateAndTime": act.iso(AHORA)},
        {"Title": "Dengue - Brazil", "PublicationDateAndTime": act.iso(AHORA - timedelta(days=90))}]},
}


def _ooni(url):
    # Bloqueo nuevo de WhatsApp en Etiopía: alto ahora, normal antes. Irán: bloqueo habitual.
    ahora = "since=" + (AHORA - timedelta(days=2)).strftime("%Y-%m-%d") in url
    filas = []
    if "whatsapp" in url:
        filas.append({"probe_cc": "ET", "measurement_count": 40, "anomaly_count": 30 if ahora else 1})
        filas.append({"probe_cc": "IR", "measurement_count": 50, "anomaly_count": 45})
    if "telegram" in url:
        filas.append({"probe_cc": "IR", "measurement_count": 50, "anomaly_count": 44})
    filas.append({"probe_cc": "ES", "measurement_count": 100, "anomaly_count": 1})
    return {"result": filas}


NOMBRES_ES = [n for p in json.loads((RAIZ / "data" / "paises.json").read_text()) for n in p.get("nombres_es", [])[:1]]
EXTERIORES_INDICE = "".join(f'<a href="/es/ServiciosAlCiudadano/Paginas/Detalle-recomendaciones-de-viaje.aspx?trc={urllib.parse.quote_plus(n)}">x</a>'
                            for n in NOMBRES_ES)
FICHA = ("<html><body><p>Recomendaciones vigentes a 2 de noviembre de 2026 Última actualización el {fecha} "
         "Notas importantes {notas} Documentación y visados Pasaporte en vigor.</p></body></html>")

RESPUESTAS.update({
    "seismicportal.eu": {"features": [
        # El mismo terremoto que USGS no debe duplicarse; este otro, en Grecia, sí entra
        {"id": "x", "properties": {"unid": "E1", "lat": 38.0, "lon": 23.7, "mag": 4.2, "flynn_region": "GREECE",
                                   "time": act.iso(AHORA)}}]},
    "ign.es": f"""<?xml version="1.0"?><rss xmlns:geo="http://www.w3.org/2003/01/geo/wgs84_pos#"><channel>
        <item><title>-Info.terremoto</title><link>https://ign/1</link><pubDate>{RFC822}</pubDate>
          <description>Se ha producido un terremoto de magnitud 3.1 en GOLFO DE CÁDIZ en la fecha ...</description>
          <geo:lat>36.3</geo:lat><geo:long>-7.9</geo:long></item>
        <item><title>-Info.terremoto</title><link>https://ign/2</link><pubDate>{RFC822}</pubDate>
          <description>Se ha producido un terremoto de magnitud 1.2 en GRANADA en la fecha ...</description>
          <geo:lat>37.1</geo:lat><geo:long>-3.6</geo:long></item></channel></rss>""",
    "mapping.emergency.copernicus.eu": {"results": [
        {"code": "EMSR999", "countries": [{"short_name": "Spain"}], "category": {"slug": "flood", "name": "Flood"},
         "name": "Flood in Valencia, Spain", "centroid": "POINT (-0.4 39.4)", "activationTime": act.iso(AHORA)},
        {"code": "EMSR100", "countries": [{"short_name": "Italy"}], "category": {"slug": "fire"},
         "name": "Viejo", "centroid": "POINT (12 42)", "activationTime": "2024-01-01T00:00:00"}]},
    "api.ooni.io": _ooni,
    "Recomendaciones-de-viaje.aspx": EXTERIORES_INDICE,
    "Detalle-recomendaciones-de-viaje.aspx?trc=Sud%C3%A1n": FICHA.format(fecha="28 de febrero de 2025", notas="SE DESACONSEJA EL VIAJE A SUDÁN BAJO CUALQUIER CIRCUNSTANCIA, SI LO HACE SERÁ POR SU CUENTA Y RIESGO."),
    "Detalle-recomendaciones-de-viaje.aspx": FICHA.format(fecha="1 de enero de 2026", notas="Se recomienda viajar con normalidad."),
    "realinstitutoelcano": f"""<?xml version="1.0"?><rss><channel>
        <item><title>La guerra en Sudán y el Sahel - Real Instituto Elcano</title><link>https://elcano/1</link>
          <pubDate>{RFC822}</pubDate><source url="https://www.realinstitutoelcano.org">Real Instituto Elcano</source></item>
        <item><title>Informe anual - Real Instituto Elcano</title><link>https://elcano/2</link><pubDate>{RFC822}</pubDate>
          <source url="https://www.realinstitutoelcano.org">Real Instituto Elcano</source></item></channel></rss>""",
    "open.er-api.com": {"result": "success", "rates": {"NGN": 1500, "EUR": 0.9}},
    "query.wikidata.org": {"results": {"bindings": [
        {"e": {"value": "http://www.wikidata.org/entity/Q1"}, "eLabel": {"value": "Elecciones generales de Filipinas"},
         "fecha": {"value": (AHORA + timedelta(days=12)).strftime("%Y-%m-%dT00:00:00Z")}, "iso": {"value": "PHL"}}]}},
})


def falsa_descarga(url, como="json", **_):
    claves = [c for c in RESPUESTAS if c in url]
    if not claves:
        return None
    valor = RESPUESTAS[max(claves, key=len)]  # la clave más específica
    if callable(valor):
        valor = valor(url)
    if isinstance(valor, (dict, list)):
        return json.loads(json.dumps(valor))
    return valor


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paises = act.Paises()

    def setUp(self):
        for f in Path(TMP).glob("**/*.json"):
            f.unlink()
        mock.patch.object(act, "descargar", side_effect=falsa_descarga).start()
        mock.patch.object(act.time, "sleep", lambda s: None).start()
        mock.patch.object(act, "GDELT_FICHEROS", 1).start()  # un solo fichero de ejemplo

    def tearDown(self):
        mock.patch.stopall()


class TestPaises(Base):
    def test_por_coordenadas(self):
        self.assertEqual(self.paises.punto(-3.7, 40.4), "ESP")
        self.assertEqual(self.paises.punto(2.35, 48.85), "FRA")

    def test_por_nombre(self):
        self.assertEqual(self.paises.nombre("45 km W of Ovalle, Chile"), "CHL")
        self.assertEqual(self.paises.nombre("Russia"), "RUS")

    def test_territorios_palestinos(self):
        self.assertEqual(self.paises.asignar("Gaza, Israel (general), Israel", 34.47, 31.5), "PSE")


class TestFuentes(Base):
    def test_usgs(self):
        ev = act.usgs(self.paises)["eventos"]
        self.assertEqual(ev[0]["pais"], "PNG")
        self.assertEqual(ev[0]["nivel"], "rojo")  # M6.8 con alerta naranja
        self.assertIsNone(ev[1]["pais"])          # en el mar

    def test_gdacs_rss(self):
        ev = act.gdacs(self.paises)["eventos"]
        self.assertEqual(len(ev), 1)  # sin duplicados ni terremotos
        self.assertEqual(ev[0]["titulo"], "Ciclón tropical Kalmaegi-25")
        self.assertEqual((ev[0]["pais"], ev[0]["nivel"]), ("PHL", "rojo"))
        self.assertTrue(act.reciente(ev[0], act.VENTANA_PUNTUACION))

    def test_gdelt_solo_violencia_politica_y_hechos_principales(self):
        r = act.gdelt(self.paises)
        self.assertEqual(r["paises"]["UKR"]["conflicto"], 45)
        self.assertEqual(r["paises"]["USA"]["conflicto"], 10)  # los 30 de delincuencia no cuentan
        self.assertEqual(r["paises"]["PER"]["conflicto"], 0)   # menciones de pasada
        jarkov = next(e for e in r["eventos"] if "Kharkiv" in e["lugar"])
        self.assertEqual((jarkov["hechos"], len(jarkov["enlaces"])), (40, 3))
        self.assertTrue(any(e["tipo"] == "protesta" and e["pais"] == "KEN" for e in r["eventos"]))

    def test_gdelt_pasos_maritimos(self):
        pasos = act.gdelt(self.paises)["pasos"]
        self.assertEqual(pasos["ormuz"], 8)
        self.assertEqual(pasos["bab"], 30)
        self.assertEqual(pasos["suez"], 0)
        niveles = {p["id"]: p["nivel"] for p in act.calcular_pasos(pasos)}
        self.assertEqual((niveles["bab"], niveles["ormuz"], niveles["gibraltar"]), ("rojo", "ambar", "verde"))

    def test_gdelt_formato_cambiado(self):
        with self.assertRaises(act.FormatoInesperado):
            act.gdelt(self.paises, filas=[["a", "b", "c"]])

    def test_titulares(self):
        t = act.titulares()["titulares"]
        self.assertEqual(len(t), 1)
        self.assertEqual((t[0]["titulo"], t[0]["medio"]), ("Nuevo ataque ruso con drones en Járkov", "EL PAÍS"))

    def test_ioda_ignora_cortes_pequenos(self):
        ev = act.ioda(self.paises)["eventos"]
        self.assertEqual([e["pais"] for e in ev], ["IRN"])

    def test_ioda_formato_cambiado(self):
        with mock.patch.dict(RESPUESTAS, {"ioda": {"otra": "cosa"}}):
            with self.assertRaises(act.FormatoInesperado):
                act.ioda(self.paises)

    def test_avisos_detecta_subidas(self):
        act.escribir("avisos.json", {"niveles": {"LBN": 3, "ESP": 2}, "cambios": []})
        r = act.avisos_viaje(self.paises)
        self.assertEqual(r["avisos"], {"LBN": 4, "SDN": 4, "ESP": 2})
        self.assertEqual([e["pais"] for e in r["eventos"]], ["LBN"])
        self.assertGreater(r["eventos"][0]["peso"], 0)

    def test_avisos_primera_vez_sin_cambios(self):
        self.assertEqual(act.avisos_viaje(self.paises)["eventos"], [])

    def test_oms(self):
        ev = act.oms(self.paises)["eventos"]
        self.assertEqual([(e["pais"], e["nivel"]) for e in ev], [("ETH", "ambar"), ("CHN", "verde")])
        self.assertTrue(ev[0]["url"].endswith("2026-DON999"))

    def test_reliefweb_desactivada_sin_appname(self):
        self.assertTrue(act.reliefweb(self.paises)["desactivada"])


class TestRetroceso(Base):
    def test_reconstruye_y_mide(self):
        sys.path.insert(0, str(RAIZ / "scripts"))
        import retroceso
        import inteligencia
        filas = FILAS_GDELT
        with mock.patch.object(act, "gdelt_filas", return_value=filas):
            hechos = retroceso.reconstruir(dias=3, muestras=4)
        self.assertEqual(len(hechos), 3)
        h = json.loads((Path(TMP) / "historico.json").read_text())
        self.assertIn("UKR", h[hechos[0]])
        self.assertEqual(act.HOY, act.AHORA.strftime("%Y-%m-%d"))  # se restauran las fechas
        self.assertFalse((Path(TMP) / "historial.json").exists())  # la línea base real no se toca

    def test_rendimiento(self):
        import inteligencia
        # 20 días, 3 países: el modelo dice "alto" en el que empeora y "bajo" en los demás
        historico = {}
        for i in range(20):
            d = f"2026-10-{i + 1:02d}"
            historico[d] = {"AAA": [10, i % 2, 0, 2], "BBB": [5, 0, 0, 0], "CCC": [5, 0, 0, 0]}
        r = inteligencia.rendimiento(historico)
        self.assertGreater(r["muestras"], 30)
        self.assertGreater(r["mejora_media"], 0)
        self.assertEqual(r["calibracion"][0]["riesgo"], "alto")


class TestIncendios(Base):
    def csv(self, n, lat=48.0, lon=37.8):
        filas = ["country_id,latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight"]
        filas += [f"UKR,{lat + i * 0.001},{lon},330,0.4,0.4,2026-11-06,0100,N,VIIRS,n,2.0NRT,290,5,N" for i in range(n)]
        filas += [f"UKR,{lat},{lon},300,0.4,0.4,2026-11-06,0100,N,VIIRS,l,2.0NRT,290,1,N" for _ in range(50)]  # baja confianza
        return "\n".join(filas) + "\n"

    def test_incendios_anomalos(self):
        previos = {(act.AHORA - timedelta(days=i)).strftime("%Y-%m-%d"): 20 for i in range(1, 11)}
        act.escribir("incendios_historial.json", {"UKR": previos})
        with mock.patch.object(act, "FIRMS_KEY", "clave"), mock.patch.object(act, "FIRMS_FIJOS", ("UKR",)), \
             mock.patch.object(act, "descargar", return_value=self.csv(80)):
            r = act.incendios(self.paises)
        self.assertEqual(r["incendios"], {"UKR": 4.0})
        self.assertEqual(r["eventos"][0]["tipo"], "incendios")
        self.assertEqual(r["eventos"][0]["peso"], 3)

    def test_sin_linea_base_no_avisa(self):
        with mock.patch.object(act, "FIRMS_KEY", "clave"), mock.patch.object(act, "FIRMS_FIJOS", ("UKR",)), \
             mock.patch.object(act, "descargar", return_value=self.csv(500)):
            r = act.incendios(self.paises)
        self.assertEqual(r["eventos"], [])

    def test_sin_clave(self):
        with mock.patch.object(act, "FIRMS_KEY", ""):
            self.assertTrue(act.incendios(self.paises)["desactivada"])


class TestSenalesTempranas(Base):
    def test_divisa_que_se_hunde(self):
        hace8 = (act.AHORA - timedelta(days=8)).strftime("%Y-%m-%d")
        act.escribir("divisas_historial.json", {hace8: {"NGN": 1000, "EUR": 0.9, "XOF": 600}})
        with mock.patch.object(act, "descargar", return_value={"result": "success",
                                                              "rates": {"NGN": 1250, "EUR": 0.9, "XOF": 610}}):
            r = act.divisas(self.paises)
        self.assertEqual(r["divisas"], {"NGA": 0.2})
        self.assertEqual(r["eventos"][0]["tipo"], "economia")
        self.assertEqual(r["eventos"][0]["nivel"], "verde")  # suma puntos, no es una alerta oficial

    def test_elecciones_wikidata(self):
        dia = (act.AHORA + timedelta(days=10)).strftime("%Y-%m-%dT00:00:00Z")
        filas = [{"e": {"value": "http://www.wikidata.org/entity/Q1"}, "eLabel": {"value": "Elecciones generales de Bolivia"},
                  "fecha": {"value": dia}, "iso": {"value": "BOL"}},
                 {"e": {"value": "x"}, "eLabel": {"value": "Q999"}, "fecha": {"value": dia}, "iso": {"value": "BOL"}}]
        with mock.patch.object(act, "descargar", return_value={"results": {"bindings": filas}}):
            r = act.elecciones(self.paises)
        self.assertEqual([x["pais"] for x in r["elecciones"]], ["BOL"])


class TestGdeltRigor(Base):
    def filas(self):
        f = act.G_URL
        filas = [fila_gdelt("19", "Al Fashir, Northern Darfur, Sudan", 13.6, 25.3, actores=("RSF", "SUDAN"))
                 for _ in range(12)]
        filas += [fila_gdelt("19", "Khartoum, Khartoum, Sudan", 15.5, 32.5, actores=("RSF", "SUDAN")) for _ in range(3)]
        # La misma noticia repetida no cuenta dos veces
        filas += [fila_gdelt("19", "Kassala, Kassala, Sudan", 15.4, 36.4, url="https://medio/repetida") for _ in range(10)]
        # Medio estatal: cuenta la mitad
        filas += [fila_gdelt("19", "Kassala, Kassala, Sudan", 15.4, 36.4, url=f"https://www.rt.com/a{i}") for i in range(4)]
        # Desescalada: alto el fuego
        filas += [fila_gdelt("08", "Jeddah, Makkah, Saudi Arabia", 21.5, 39.2, base="087", actor="GOV") for _ in range(2)]
        filas += [fila_gdelt("08", "Khartoum, Khartoum, Sudan", 15.5, 32.5, base="087", actor="GOV") for _ in range(6)]
        return filas

    def test_deduplicado_estatales_regiones_actores(self):
        g = act.gdelt(self.paises, self.filas())["paises"]["SDN"]
        self.assertEqual(g["conflicto"], 12 + 3 + 1 + 2)  # repetida = 1, rt.com = 4 × 0,5
        self.assertEqual(g["estatal"], 4)
        self.assertEqual(g["desescalada"], 6)
        self.assertEqual(g["regiones"][0][0], "Northern Darfur")
        self.assertEqual(g["actores"][0][:2], ["RSF", "SUDAN"])

    def test_analisis_y_desescalada(self):
        import inteligencia
        gd = act.gdelt(self.paises, self.filas())["paises"]
        ctx = {"gdelt": gd, "tregua_en_prensa": set(), "paises": {}}
        p = {"nivel": "ambar", "confianza": "baja"}
        self.assertTrue(inteligencia.desescalando("SDN", ctx))
        an = inteligencia.analisis("SDN", p, ctx, [{"id": "escalada", "nombre": "Escalada militar", "riesgo": "medio"}])
        self.assertIn("contra", an)
        self.assertTrue(any("prensa" in a for a in an["alternativas"]))
        self.assertTrue(an["desmentiria"])


class TestFuentesNuevas(Base):
    def test_exteriores(self):
        r = act.exteriores(self.paises)
        self.assertEqual(r["exteriores"]["SDN"]["nivel"], 4)
        self.assertEqual(r["exteriores"]["SDN"]["actualizacion"], "2025-02-28")
        self.assertEqual(r["exteriores"]["FRA"]["nivel"], 1)
        # Una segunda consulta antes de 12 h reutiliza lo guardado
        with mock.patch.dict(RESPUESTAS, {"Recomendaciones-de-viaje.aspx": None}):
            self.assertEqual(act.exteriores(self.paises)["exteriores"]["SDN"]["nivel"], 4)

    def test_exteriores_niveles(self):
        self.assertEqual(act.exteriores_nivel("Se desaconseja el viaje salvo por razones de extrema necesidad."), 3)
        self.assertEqual(act.exteriores_nivel("Se recomienda extremar la precaución en la frontera."), 2)
        self.assertEqual(act.exteriores_nivel("Se recomienda a los españoles que abandonen el país."), 4)
        # Casos reales de las fichas
        self.assertEqual(act.exteriores_nivel("SE DESACONSEJA EL VIAJE SALVO POR RAZONES QUE LO HAGAN NECESARIO. "
                                              "EN TODO CASO, SE DEBERÁN EVITAR DETERMINADAS ZONAS."), 3)
        self.assertEqual(act.exteriores_nivel("Se aconseja aplazar viaje hasta nuevo aviso. Para los ciudadanos que "
                                              "deseen abandonar el país, existen vuelos."), 3)
        self.assertEqual(act.exteriores_nivel("ANTE EL CONTEXTO DE CONFLICTO REGIONAL, SE DESACONSEJA COMPLETAMENTE VIAJAR A IRÁN."), 4)
        self.assertEqual(act.exteriores_nivel("Se desaconseja participar en actos o concentraciones políticas."), 1)
        self.assertEqual(act.exteriores_nivel("Se desaconseja viajar a las zonas fronterizas con Yemen."), 2)
        self.assertEqual(act.exteriores_nivel("S E DESACONSEJA EL VIAJE A MALI BAJO CUALQUIER CIRCUNSTANCIA."), 4)

    def test_ooni_bloqueo_nuevo_y_habitual(self):
        ev = {e["pais"]: e for e in act.ooni(self.paises)["eventos"]}
        self.assertEqual(ev["ETH"]["titulo"], "Nuevo bloqueo de WhatsApp")
        self.assertEqual((ev["ETH"]["nivel"], ev["IRN"]["peso"]), ("ambar", 0))
        self.assertNotIn("ESP", ev)

    def test_copernicus_solo_recientes(self):
        ev = act.copernicus(self.paises)["eventos"]
        self.assertEqual([(e["pais"], e["titulo"]) for e in ev], [("ESP", "La UE activa Copernicus: inundación")])

    def test_ign_y_duplicados_sismicos(self):
        ign = act.ign(self.paises)["eventos"]
        self.assertEqual(len(ign), 1)  # el de magnitud 1.2 no entra
        usgs = act.usgs(self.paises)["eventos"]
        copia = dict(usgs[0], id="emsc-copia", fuente="EMSC")
        sin = act.sin_duplicados_sismicos(usgs + [copia] + ign)
        self.assertEqual(sorted(e["fuente"] for e in sin), ["IGN", "USGS", "USGS"])

    def test_analisis_por_pais(self):
        a = act.analisis(self.paises)["analisis"]
        self.assertEqual(len(a), 1)
        self.assertEqual(a[0]["paises"], ["SDN"])
        self.assertEqual(a[0]["titulo"], "La guerra en Sudán y el Sahel")

    def test_paises_en_texto(self):
        self.assertEqual(self.paises.en_texto("Ataques en Malí y Burkina Faso; Estados Unidos responde"),
                         ["MLI", "BFA", "USA"])


class TestInteligencia(Base):
    def test_vecinos(self):
        v = act.inteligencia.calcular_vecinos(self.paises)
        self.assertIn("FRA", v["ESP"])
        self.assertIn("PRT", v["ESP"])
        self.assertNotIn("ITA", v["ESP"])

    def test_escenario_golpe(self):
        ctx = {"gdelt": {"NER": {"militar": 8}}, "pasos": {}, "vecinos": {}, "golpe_en_prensa": {"NER"},
               "ucdp": {}, "paises": {}}
        p = {"internet": 5, "censura": 6, "puntuacion": 15}
        escs, _ = act.inteligencia.escenarios("NER", p, ctx)
        golpe = next(e for e in escs if e["id"] == "golpe")
        self.assertEqual((golpe["riesgo"], golpe["estimativo"]), ("alto", "Probable"))
        self.assertEqual(act.inteligencia.pronostico(p, escs)["riesgo"], "alto")

    def test_pronostico_por_tendencia(self):
        p = {"serie": [2, 4, 6, 8, 10, 12, 14], "puntuacion": 14}
        pr = act.inteligencia.pronostico(p, [])
        self.assertEqual(pr["riesgo"], "alto")
        self.assertAlmostEqual(pr["pendiente"], 2.0)
        self.assertEqual(act.inteligencia.pronostico({"serie": [5, 5, 5], "puntuacion": 5}, [])["riesgo"], "bajo")

    def test_fiabilidad(self):
        h = {f"2026-10-{d:02d}": {"MLI": [5, 0, 0, 2 if d == 1 else 0], "CHL": [1, 0, 0, 2 if d == 1 else 0]}
             for d in range(1, 10)}
        h["2026-10-04"]["MLI"] = [20, 2, 1, 0]
        f = act.inteligencia.fiabilidad(h)
        self.assertEqual(f["alto"], {"aciertos": 1, "total": 2})


class TestSimulacion(Base):
    def setUp(self):
        super().setUp()
        sys.path.insert(0, str(RAIZ / "scripts"))
        import simulacion
        self.sim = simulacion

    def test_probabilidades_suman_100_y_suben_con_el_riesgo(self):
        esc = {"indicadores": [{"activo": True}, {"activo": True}, {"activo": False}]}
        alto, factores = self.sim.probabilidades({"pronostico": {"riesgo": "alto", "pendiente": 2}, "aceleracion": 2.5},
                                                 esc, ["TCD", "LBY"])
        bajo, _ = self.sim.probabilidades({"pronostico": {"riesgo": "bajo", "pendiente": -1}}, None, [])
        self.assertTrue(any("12 horas" in f for f in factores))
        self.assertEqual(sum(alto.values()), 100)
        self.assertEqual(sum(bajo.values()), 100)
        self.assertGreater(alto["escala"], bajo["escala"])
        self.assertGreater(bajo["contiene"], alto["contiene"])
        self.assertTrue(all(v % 5 == 0 for v in alto.values()))

    def test_simular_contagio_e_impacto_en_espana(self):
        alertas = {"paises": {
            "MLI": {"nivel": "rojo", "puntuacion": 30, "confianza": "alta", "motivos": ["X"],
                    "pronostico": {"riesgo": "alto", "pendiente": 1},
                    "escenarios": [{"id": "escalada", "nombre": "Escalada militar", "riesgo": "alto",
                                    "indicadores": [{"texto": "A", "activo": True}, {"texto": "B", "activo": False}]}]},
            "NER": {"nivel": "ambar", "puntuacion": 10, "pronostico": {"riesgo": "bajo"}},
            "DZA": {"nivel": "verde", "puntuacion": 1, "pronostico": {"riesgo": "bajo"}},
            "CHL": {"nivel": "verde", "puntuacion": 1, "pronostico": {"riesgo": "bajo"}}}}
        r = self.sim.simular(alertas, {"MLI": ["NER", "DZA"]}, {"MLI": "Sahel", "NER": "Sahel"}, {},
                             lambda a: ["Rutas migratorias hacia España"] if a == "MLI" else [], lambda a: [])
        self.assertIn("no tiene ninguna validez oficial", r["aviso"])
        caso = r["casos"][0]
        self.assertEqual(caso["pais"], "MLI")
        self.assertEqual([x["id"] for x in caso["ramas"]], ["escala", "igual", "contiene"])
        # Níger ya está en crisis (es otro caso simulado): no cuenta como contagio; Argelia sí
        self.assertEqual([v["pais"] for v in caso["contagio"]], ["DZA"])
        self.assertIn("Posible aumento de salidas por las rutas migratorias hacia España.", caso["espana"])
        self.assertEqual(caso["confirman"], ["B"])
        self.assertNotIn("CHL", [c["pais"] for c in r["casos"]])
        # Región: que al menos una de sus crisis escale es más probable que la media de sus crisis
        sahel = r["regiones"][0]
        self.assertEqual(sahel["region"], "Sahel")
        media = sum(c["ramas"][0]["probabilidad"] for c in r["casos"] if c["region"] == "Sahel") / 2
        self.assertGreaterEqual(sahel["probabilidad"], media)
        self.assertEqual(caso["ramas"][0]["intervalo"][1] - caso["ramas"][0]["intervalo"][0], 10)  # confianza alta: ±5

    def test_calibracion_con_el_acierto_real(self):
        pesos, calibrado = self.sim.pesos_calibrados({"alto": {"aciertos": 80, "total": 100}})
        self.assertTrue(calibrado)
        self.assertAlmostEqual(pesos["alto"], 0.6)  # mitad peso de partida (0,40), mitad lo observado (0,80)
        self.assertEqual(self.sim.pesos_calibrados({"alto": {"aciertos": 1, "total": 5}}), (self.sim.PESOS_RIESGO, False))

    def test_aceleracion(self):
        self.assertEqual(act.aceleracion({"conflicto_12h": 20, "conflicto_12h_antes": 9}), 2.1)
        self.assertIsNone(act.aceleracion({"conflicto_12h": 2, "conflicto_12h_antes": 1}))


class TestAlertas(Base):
    def test_gdacs_sequia_no_se_atribuye(self):
        rss = GDACS_RSS.replace("<gdacs:eventtype>TC</gdacs:eventtype><gdacs:eventid>1</gdacs:eventid><gdacs:eventname>",
                                "<gdacs:eventtype>DR</gdacs:eventtype><gdacs:eventid>1</gdacs:eventid><gdacs:eventname>")
        with mock.patch.dict(RESPUESTAS, {"gdacs.org": rss}):
            ev = act.gdacs(self.paises)["eventos"]
        self.assertEqual((ev[0]["pais"], ev[0]["peso"]), (None, 0))

    def test_sesgo_de_cobertura(self):
        """Mucha cobertura de EE. UU. no debe pesar como un país en guerra."""
        p = act.puntuar([], act.gdelt(self.paises)["paises"])
        self.assertGreater(p["UKR"]["conflicto"], 3 * p["USA"]["conflicto"])

    def test_evento_oficial_fija_el_nivel(self):
        a = act.calcular_alertas(act.puntuar(act.gdacs(self.paises)["eventos"], {}), {})
        self.assertEqual(a["paises"]["PHL"]["nivel"], "rojo")
        self.assertIn("Alerta oficial roja", a["paises"]["PHL"]["motivos"])
        self.assertTrue(a["calibrando"])

    def test_crisis_prolongada_no_sale_en_verde(self):
        """Un país en guerra larga sigue en alerta aunque hoy no empeore."""
        hist = {(AHORA - timedelta(days=i)).strftime("%Y-%m-%d"): {"SDN": 35, "UKR": 20} for i in range(1, 11)}
        puntos = {"SDN": {"puntuacion": 34}, "UKR": {"puntuacion": 20}}
        a = act.calcular_alertas(puntos, hist)["paises"]
        self.assertEqual((a["SDN"]["nivel"], a["SDN"]["escalada"]), ("rojo", False))
        self.assertEqual((a["UKR"]["nivel"], a["UKR"]["escalada"]), ("ambar", False))
        self.assertIn("Crisis prolongada", a["UKR"]["motivos"])

    def test_aviso_nivel_4_refuerza_pero_no_colorea_solo(self):
        a = act.calcular_alertas({"SDN": {"puntuacion": 5}, "RUS": {"puntuacion": 1}}, {}, {"SDN": 4, "RUS": 4, "ESP": 2})["paises"]
        self.assertEqual(a["SDN"]["nivel"], "ambar")
        self.assertEqual(a["RUS"]["nivel"], "verde")
        self.assertNotIn("ESP", a)

    def test_escalada_frente_a_su_media(self):
        hist = {(AHORA - timedelta(days=i)).strftime("%Y-%m-%d"): {"MLI": 3} for i in range(1, 11)}
        a = act.calcular_alertas({"MLI": {"puntuacion": 22}}, hist)["paises"]["MLI"]
        self.assertEqual((a["nivel"], a["escalada"]), ("rojo", True))

    def test_varios_dias_subiendo(self):
        self.assertEqual(act.dias_subiendo([1, 1, 2, 4, 7, 10]), 4)
        self.assertEqual(act.dias_subiendo([5, 4]), 0)
        hist = {(AHORA - timedelta(days=i)).strftime("%Y-%m-%d"): {"MLI": v}
                for i, v in zip(range(10, 0, -1), [1, 1, 1, 1, 1, 1, 1, 4, 7, 9])}
        a = act.calcular_alertas({"MLI": {"puntuacion": 11}}, hist)["paises"]["MLI"]
        self.assertGreaterEqual(a["dias_subiendo"], 3)
        self.assertEqual((a["nivel"], a["escalada"]), ("ambar", True))

    def test_confianza(self):
        self.assertEqual(act.confianza(["prensa"]), "baja")
        self.assertEqual(act.confianza(["tecnica"]), "media")
        self.assertEqual(act.confianza(["oficial", "prensa"]), "alta")

    def test_parte_compara_con_ayer(self):
        ayer = {"dia": "2000-01-01", "paises": {"ETH": {"nivel": "verde"}, "CHL": {"nivel": "ambar"}}}
        hoy = {"paises": {"ETH": {"nivel": "rojo", "escalada": True, "z": 4, "puntuacion": 30}}}
        p, ref = act.parte(hoy, ayer)
        self.assertEqual((p["suben"], p["bajan"], p["empeoran"]), (["ETH"], ["CHL"], ["ETH"]))
        # Una segunda ejecución el mismo día sigue comparando con ayer
        hoy2 = {**hoy, "dia": act.HOY, "niveles_ayer": ref}
        self.assertEqual(act.parte(hoy, hoy2)[0]["suben"], ["ETH"])


class TestEjecucionCompleta(Base):
    def test_main_y_fuente_caida(self):
        act.main()
        e = json.loads((Path(TMP) / "eventos.json").read_text())
        self.assertTrue(all(f["ok"] for f in e["fuentes"].values()), e["fuentes"])
        self.assertNotIn("ReliefWeb", e["fuentes"])  # sin appname no se intenta
        a = json.loads((Path(TMP) / "alertas.json").read_text())
        self.assertEqual(a["paises"]["PHL"]["nivel"], "rojo")
        self.assertEqual(len(a["pasos"]), len(act.PASOS))
        self.assertIn("ETH", a["paises"])  # brote de Marburgo
        self.assertIn("informe", a)
        self.assertIn("pronostico", a["paises"]["PHL"])
        self.assertEqual(a["informe"]["fechas"][0]["pais"], "PHL")
        self.assertTrue(a["paises"]["PHL"]["elecciones"])
        ext = json.loads((Path(TMP) / "exteriores.json").read_text())
        self.assertEqual(ext["paises"]["SDN"]["nivel"], 4)
        self.assertIn("vigilar", a["informe"])
        self.assertIn("simulacion", a)
        self.assertIn("validez oficial", a["simulacion"]["aviso"])

        # Histórico: foto del día, índice y serie por país
        foto = json.loads((Path(TMP) / "archivo" / f"{act.HOY}.json").read_text())
        self.assertEqual(foto["paises"]["PHL"]["nivel"], "rojo")
        self.assertLessEqual(len(foto["eventos"]), act.EVENTOS_ARCHIVO)
        self.assertEqual(foto["eventos"][0]["nivel"], "rojo")  # lo más relevante primero
        indice = json.loads((Path(TMP) / "archivo" / "indice.json").read_text())
        self.assertEqual(indice["dias"], [act.HOY])
        historico = json.loads((Path(TMP) / "historico.json").read_text())
        self.assertEqual(historico[act.HOY]["PHL"][1], 2)

        # Segunda ejecución con USGS caído: se conservan sus datos y se cuenta el fallo
        with mock.patch.dict(RESPUESTAS, {"earthquake.usgs.gov": None}):
            act.main()
        e = json.loads((Path(TMP) / "eventos.json").read_text())
        self.assertFalse(e["fuentes"]["USGS"]["ok"])
        self.assertEqual(e["fuentes"]["USGS"]["fallos_seguidos"], 1)
        self.assertTrue(any(x["fuente"] == "USGS" for x in e["eventos"]))


if __name__ == "__main__":
    unittest.main()
