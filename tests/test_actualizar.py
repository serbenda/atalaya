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

spec = importlib.util.spec_from_file_location("actualizar", RAIZ / "scripts" / "actualizar.py")
act = importlib.util.module_from_spec(spec)
sys.modules["actualizar"] = act
spec.loader.exec_module(act)

AHORA = act.AHORA
MS = int(AHORA.timestamp() * 1000)


def fila_gdelt(raiz, nombre, lat, lon, articulos=5, tipo="4", url="https://medio/x"):
    f = [""] * 61
    f[act.G_RAIZ] = raiz
    f[act.G_ARTICULOS] = str(articulos)
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
    + [fila_gdelt("19", "Washington, District of Columbia, United States", 38.9, -77.03) for _ in range(10)]
    + [fila_gdelt("04", "Washington, District of Columbia, United States", 38.9, -77.03) for _ in range(400)]
    + [fila_gdelt("14", "Nairobi, Nairobi Area, Kenya", -1.28, 36.82) for _ in range(12)]
    + [fila_gdelt("04", "Nairobi, Nairobi Area, Kenya", -1.28, 36.82) for _ in range(20)]
    + [fila_gdelt("18", "Gaza, Israel (general), Israel", 31.5, 34.47) for _ in range(15)]
)

RESPUESTAS = {
    "earthquake.usgs.gov": {"features": [
        {"id": "a", "properties": {"mag": 6.8, "place": "120 km SSW of Kokopo, Papua New Guinea", "time": MS,
                                   "url": "u", "alert": "orange"}, "geometry": {"coordinates": [151.9, -5.2, 30]}},
        {"id": "b", "properties": {"mag": 4.6, "place": "Fiji region", "time": MS, "url": "u", "alert": None},
         "geometry": {"coordinates": [-178.2, -18.1, 500]}}]},
    "gdacs.org": {"features": [
        {"geometry": {"type": "Point", "coordinates": [125.0, 14.0]},
         "properties": {"eventtype": "TC", "eventid": 1, "name": "Tropical Cyclone KALMAEGI-25", "alertlevel": "Red",
                        "country": "Philippines", "iso3": "PHL", "todate": AHORA.strftime("%Y-%m-%dT%H:%M:%S"),
                        "url": {"report": "r"}}},
        {"geometry": {"type": "Point", "coordinates": [125.0, 14.0]},
         "properties": {"eventtype": "TC", "eventid": 1, "alertlevel": "Orange", "iso3": "PHL"}},
        {"geometry": {"type": "Polygon", "coordinates": []}, "properties": {"eventtype": "TC", "eventid": 1}}]},
    "eonet.gsfc.nasa.gov": {"events": [
        {"id": "E1", "title": "Etna", "categories": [{"id": "volcanoes"}], "sources": [],
         "geometry": [{"date": act.iso(AHORA), "type": "Point", "coordinates": [15.0, 37.75]}]}]},
    "lastupdate.txt": "1 a http://data.gdeltproject.org/gdeltv2/20261102081500.export.CSV.zip\n",
    "export.CSV.zip": zip_gdelt(FILAS_GDELT),
    "api/v2/doc": {"articles": [
        {"title": "Ataque en Járkov", "url": "https://m/1", "domain": "elpais.com", "seendate": "20261102T080000Z"},
        {"title": "Ataque en Járkov", "url": "https://m/2", "domain": "abc.es", "seendate": "20261102T080000Z"}]},
    "ioda": {"data": [
        {"entity": {"code": "IR", "name": "Iran", "type": "country"}, "scores": {"overall": 250000}, "event_cnt": 3},
        {"entity": {"code": "ES", "name": "Spain"}, "scores": {"overall": 0}}]},
    "travel.state.gov": """<?xml version="1.0"?><rss><channel>
        <item><title>Lebanon - Level 4: Do Not Travel</title><link>https://t/lb</link>
              <pubDate>Mon, 02 Nov 2026 08:00:00 GMT</pubDate></item>
        <item><title>Spain - Level 2: Exercise Increased Caution</title><link>https://t/es</link></item>
        <item><title>Travel Advisory Updates</title></item></channel></rss>""",
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
        self.parche = mock.patch.object(act, "descargar", side_effect=falsa_descarga)
        self.parche.start()
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

    def test_gdacs_sin_duplicados_ni_poligonos(self):
        ev = act.gdacs(self.paises)["eventos"]
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["titulo"], "Ciclón tropical Kalmaegi-25")
        self.assertEqual(ev[0]["nivel"], "rojo")

    def test_gdacs_vacio(self):
        RESPUESTAS["gdacs.org"], antes = {}, RESPUESTAS["gdacs.org"]
        try:
            self.assertEqual(act.gdacs(self.paises), {"eventos": []})
        finally:
            RESPUESTAS["gdacs.org"] = antes

    def test_gdelt_agrega_por_lugar_y_pais(self):
        r = act.gdelt(self.paises)
        ucr = r["paises"]["UKR"]
        self.assertEqual(ucr["conflicto"], 40)
        self.assertEqual(ucr["total"], 100)
        jarkov = next(e for e in r["eventos"] if "Kharkiv" in e["lugar"])
        self.assertEqual(jarkov["hechos"], 40)
        self.assertEqual(len(jarkov["enlaces"]), 3)
        self.assertTrue(any(e["tipo"] == "protesta" and e["pais"] == "KEN" for e in r["eventos"]))

    def test_gdelt_formato_cambiado(self):
        with self.assertRaises(act.FormatoInesperado):
            act.gdelt(self.paises, filas=[["a", "b", "c"]])

    def test_ioda(self):
        ev = act.ioda(self.paises)["eventos"]
        self.assertEqual([e["pais"] for e in ev], ["IRN"])
        self.assertEqual(ev[0]["tipo"], "internet")

    def test_ioda_formato_cambiado(self):
        RESPUESTAS["ioda"], antes = {"otra": "cosa"}, RESPUESTAS["ioda"]
        try:
            with self.assertRaises(act.FormatoInesperado):
                act.ioda(self.paises)
        finally:
            RESPUESTAS["ioda"] = antes

    def test_avisos_detecta_subidas(self):
        act.escribir("avisos.json", {"niveles": {"LBN": 3, "ESP": 2}, "cambios": []})
        r = act.avisos_viaje(self.paises)
        self.assertEqual(r["avisos"], {"LBN": 4, "ESP": 2})
        self.assertEqual(len(r["eventos"]), 1)
        self.assertEqual(r["eventos"][0]["pais"], "LBN")
        self.assertGreater(r["eventos"][0]["peso"], 0)

    def test_avisos_primera_vez_sin_cambios(self):
        self.assertEqual(act.avisos_viaje(self.paises)["eventos"], [])


class TestAlertas(Base):
    def test_sesgo_de_cobertura(self):
        """Mucha cobertura de EE. UU. no debe pesar como un país en guerra."""
        g = act.gdelt(self.paises)["paises"]
        p = act.puntuar([], g)
        self.assertGreater(p["UKR"]["conflicto"], 3 * p["USA"]["conflicto"])

    def test_evento_oficial_fija_el_nivel(self):
        ev = act.gdacs(self.paises)["eventos"]
        a = act.calcular_alertas(act.puntuar(ev, {}), {})
        self.assertEqual(a["paises"]["PHL"]["nivel"], "rojo")
        self.assertTrue(a["calibrando"])

    def test_anomalia_frente_a_su_media(self):
        hist = {(AHORA - timedelta(days=i)).strftime("%Y-%m-%d"): {"SDN": 3, "UKR": 25} for i in range(1, 11)}
        puntos = {"SDN": {"puntuacion": 20, "rango_evento": 0}, "UKR": {"puntuacion": 25, "rango_evento": 0}}
        a = act.calcular_alertas(puntos, hist)["paises"]
        self.assertEqual(a["SDN"]["nivel"], "rojo")      # muy por encima de lo suyo
        self.assertEqual(a["UKR"]["nivel"], "ambar")     # alto pero habitual
        self.assertEqual(a["UKR"]["tendencia"], "estable")

    def test_varios_dias_subiendo(self):
        self.assertEqual(act.dias_subiendo([1, 1, 2, 4, 7, 10]), 4)
        self.assertEqual(act.dias_subiendo([5, 4]), 0)
        hist = {(AHORA - timedelta(days=i)).strftime("%Y-%m-%d"): {"MLI": v}
                for i, v in zip(range(10, 0, -1), [1, 1, 1, 1, 1, 1, 1, 3, 5, 7])}
        a = act.calcular_alertas({"MLI": {"puntuacion": 9, "rango_evento": 0}}, hist)["paises"]["MLI"]
        self.assertGreaterEqual(a["dias_subiendo"], 3)
        self.assertEqual(a["nivel"], "ambar")


class TestEjecucionCompleta(Base):
    def test_main_y_fuente_caida(self):
        act.main()
        e = json.loads((Path(TMP) / "eventos.json").read_text())
        self.assertTrue(all(f["ok"] for f in e["fuentes"].values()), e["fuentes"])
        a = json.loads((Path(TMP) / "alertas.json").read_text())
        self.assertIn("PHL", a["paises"])

        # Segunda ejecución con USGS caído: se conservan sus datos y se cuenta el fallo
        RESPUESTAS["earthquake.usgs.gov"], antes = None, RESPUESTAS["earthquake.usgs.gov"]
        try:
            act.main()
        finally:
            RESPUESTAS["earthquake.usgs.gov"] = antes
        e = json.loads((Path(TMP) / "eventos.json").read_text())
        self.assertFalse(e["fuentes"]["USGS"]["ok"])
        self.assertEqual(e["fuentes"]["USGS"]["fallos_seguidos"], 1)
        self.assertTrue(any(x["fuente"] == "USGS" for x in e["eventos"]))


if __name__ == "__main__":
    unittest.main()
