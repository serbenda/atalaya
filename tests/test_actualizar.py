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


def fila_gdelt(raiz, nombre, lat, lon, articulos=5, tipo="4", url="https://medio/x", actor="MIL", principal="1"):
    f = [""] * 61
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
    # Mención de pasada (no es el hecho principal de la noticia): no debe contar
    + [fila_gdelt("19", "Lima, Lima, Peru", -12.05, -77.04, principal="0") for _ in range(30)]
    # Cerca del estrecho de Ormuz y de Bab el-Mandeb
    + [fila_gdelt("19", "Bandar Abbas, Hormozgan, Iran", 27.18, 56.27) for _ in range(8)]
    + [fila_gdelt("18", "Al Hudaydah, Yemen", 14.8, 42.95) for _ in range(30)]
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
        <item><title>Nuevo ataque en Járkov - EL PAÍS</title><link>https://m/1</link><pubDate>{RFC822}</pubDate>
              <source url="https://elpais.com">EL PAÍS</source></item>
        <item><title>Nuevo ataque en Járkov - ABC</title><link>https://m/2</link><pubDate>{RFC822}</pubDate>
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


def falsa_descarga(url, como="json", **_):
    for clave, valor in RESPUESTAS.items():
        if clave in url:
            if isinstance(valor, (dict, list)):
                return json.loads(json.dumps(valor))
            return valor
    return None


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paises = act.Paises()

    def setUp(self):
        for f in Path(TMP).glob("*.json"):
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
        self.assertEqual(r["paises"]["UKR"]["conflicto"], 40)
        self.assertEqual(r["paises"]["USA"]["conflicto"], 10)  # los 30 de delincuencia no cuentan
        self.assertEqual(r["paises"]["PER"]["conflicto"], 0)   # menciones de pasada
        jarkov = next(e for e in r["eventos"] if "Kharkiv" in e["lugar"])
        self.assertEqual((jarkov["hechos"], len(jarkov["enlaces"])), (40, 3))
        self.assertTrue(any(e["tipo"] == "protesta" and e["pais"] == "KEN" for e in r["eventos"]))

    def test_gdelt_pasos_maritimos(self):
        pasos = act.gdelt(self.paises)["pasos"]
        self.assertEqual(pasos["ormuz"], 8)
        self.assertEqual(pasos["bab"], 30)
        niveles = {p["id"]: p["nivel"] for p in act.calcular_pasos(pasos)}
        self.assertEqual((niveles["bab"], niveles["ormuz"], niveles["gibraltar"]), ("rojo", "ambar", "verde"))

    def test_gdelt_formato_cambiado(self):
        with self.assertRaises(act.FormatoInesperado):
            act.gdelt(self.paises, filas=[["a", "b", "c"]])

    def test_titulares(self):
        t = act.titulares()["titulares"]
        self.assertEqual(len(t), 1)
        self.assertEqual((t[0]["titulo"], t[0]["medio"]), ("Nuevo ataque en Járkov", "EL PAÍS"))

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


class TestAlertas(Base):
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

    def test_aviso_nivel_4_marca_crisis_desde_el_primer_dia(self):
        a = act.calcular_alertas({}, {}, {"SDN": 4, "ESP": 2})["paises"]
        self.assertEqual(a["SDN"]["nivel"], "ambar")
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

        # Segunda ejecución con USGS caído: se conservan sus datos y se cuenta el fallo
        with mock.patch.dict(RESPUESTAS, {"earthquake.usgs.gov": None}):
            act.main()
        e = json.loads((Path(TMP) / "eventos.json").read_text())
        self.assertFalse(e["fuentes"]["USGS"]["ok"])
        self.assertEqual(e["fuentes"]["USGS"]["fallos_seguidos"], 1)
        self.assertTrue(any(x["fuente"] == "USGS" for x in e["eventos"]))


if __name__ == "__main__":
    unittest.main()
