"""Pruebas de los datos de satélite de la NASA: luces nocturnas y lluvias.

Las que crean ficheros HDF5 de ejemplo necesitan h5py y numpy; si no están, se saltan."""

import importlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

try:
    import h5py
    import numpy as np
except ImportError:  # pragma: no cover
    h5py = np = None


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.salida = Path(self.dir) / "data"
        self.salida.mkdir()
        os.environ["ATALAYA_SALIDA"] = str(self.salida)
        os.environ["EARTHDATA_TOKEN"] = "token-de-prueba"

    def tearDown(self):
        shutil.rmtree(self.dir)
        os.environ.pop("EARTHDATA_TOKEN", None)

    def escribir(self, nombre, datos):
        (self.salida / nombre).write_text(json.dumps(datos), "utf-8")

    def leer(self, nombre):
        return json.loads((self.salida / nombre).read_text("utf-8"))


class TestLectoresEnActualizar(Base):
    def setUp(self):
        super().setUp()
        import actualizar
        self.act = importlib.reload(actualizar)

    def test_luces_sin_fichero(self):
        self.assertTrue(self.act.luces(None)["desactivada"])

    def test_luces_al_dia_y_caducadas(self):
        self.escribir("luces.json", {"actualizado": self.act.iso(self.act.AHORA), "eventos": [{"id": "x"}],
                                     "paises": {"SDN": 0.3}, "lugares": {}})
        r = self.act.luces(None)
        self.assertEqual(r["luces"], {"SDN": 0.3})
        self.escribir("luces.json", {"actualizado": self.act.iso(self.act.AHORA - timedelta(days=5)), "eventos": []})
        self.assertIsNone(self.act.luces(None))  # el paso lleva días sin funcionar

    def test_lluvias(self):
        self.escribir("lluvias.json", {"actualizado": self.act.iso(self.act.AHORA), "eventos": [],
                                       "paises": {"PAK": {"mm": 300, "km2": 900}}})
        self.assertEqual(self.act.lluvias(None)["lluvias"]["PAK"]["mm"], 300)


def baldosa_h5(ruta, campos, centro=(15.55, 32.53)):
    """Baldosa de Black Marble de juguete: 100×100 píxeles alrededor de Jartum."""
    lat = centro[0] + (50 - np.arange(100)) / 240
    lon = centro[1] + (np.arange(100) - 50) / 240
    with h5py.File(ruta, "w") as h:
        g = h.create_group("HDFEOS/GRIDS/VIIRS_Grid_DNB_2d/Data Fields")
        g["lat"], g["lon"] = lat, lon
        for nombre, valor in campos.items():
            g[nombre] = np.full((100, 100), valor, dtype="float32" if isinstance(valor, float) else "uint8")


@unittest.skipUnless(h5py, "necesita h5py y numpy")
class TestLuces(Base):
    def preparar(self, luz):
        import luces
        self.luces = importlib.reload(luces)
        self.escribir("alertas.json", {"paises": {"SDN": {"conflicto": 20}}})
        self.escribir("eventos.json", {"eventos": [{"tipo": "conflicto", "pais": "SDN", "lugar": "Khartoum, Khartoum, Sudan",
                                                    "lat": 15.55, "lon": 32.53, "hechos": 30}]})
        self.diario = Path(self.dir) / "diario.h5"
        self.mensual = Path(self.dir) / "mensual.h5"
        baldosa_h5(self.diario, {"DNB_BRDF-Corrected_NTL": luz, "Mandatory_Quality_Flag": 0, "Snow_Flag": 0})
        baldosa_h5(self.mensual, {"AllAngle_Composite_Snow_Free": 40.0, "AllAngle_Composite_Snow_Free_Quality": 0})
        lista = {f"h{i:02d}v{j:02d}": "url" for i in range(36) for j in range(18)}
        b = self.luces.baldosa(15.55, 32.53)
        self.assertEqual(b, "h21v07")

        def pedir(url, destino=None):
            fuente = self.mensual if "mensual" in url else self.diario
            shutil.copy(fuente, destino)
            return destino

        def ficheros(producto, dia):
            return {k: ("mensual" if producto == self.luces.MENSUAL else "diario") for k in lista}
        return mock.patch.multiple(self.luces, pedir=pedir, ficheros_del_dia=ficheros, TOKEN="t", SALIDA=self.salida)

    def test_apagon_sostenido(self):
        with self.preparar(10.0):
            self.luces.principal()                         # primer día: 25 % de lo normal
            estado = self.leer("luces_estado.json")
            # segundo día (otra fecha), sigue a oscuras
            dia = self.leer("luces.json")["dia"]
            historial = self.leer("luces_historial.json")
            k = next(iter(historial))
            anterior = (self.luces.date.fromisoformat(dia) - timedelta(days=1)).isoformat()
            historial[k][anterior] = 11.0
            self.escribir("luces_historial.json", historial)
            self.escribir("luces_estado.json", {"dia": estado["dia"]})
            self.luces.principal()
        r = self.leer("luces.json")
        self.assertEqual(r["paises"], {"SDN": 0.25})
        self.assertEqual(r["eventos"][0]["tipo"], "apagon")
        self.assertIn("Khartoum", r["eventos"][0]["titulo"])
        self.assertEqual(r["eventos"][0]["peso"], 3)

    def test_una_noche_no_basta(self):
        with self.preparar(10.0):
            self.luces.principal()
        self.assertEqual(self.leer("luces.json")["eventos"], [])  # una sola observación

    def test_luz_normal(self):
        with self.preparar(38.0):
            self.luces.principal()
        r = self.leer("luces.json")
        self.assertEqual(r["eventos"], [])
        self.assertAlmostEqual(next(iter(r["lugares"].values()))["razon"], 0.95)


@unittest.skipUnless(h5py, "necesita h5py y numpy")
class TestLluvias(Base):
    def test_lluvia_extrema_en_tierra(self):
        import lluvias
        lluvias = importlib.reload(lluvias)
        lon = np.arange(-179.95, 180, 0.1, dtype="float32")
        lat = np.arange(-89.95, 90, 0.1)
        ruta = Path(self.dir) / "imerg.nc4"
        lluvia = np.zeros((1, lon.size, lat.size), dtype="float32")
        # 4×4 celdas con 180 mm en Pakistán (Sindh) y una en el mar
        i0, j0 = int((68.5 + 180) * 10), int((26.5 + 90) * 10)
        lluvia[0, i0:i0 + 4, j0:j0 + 4] = 180
        lluvia[0, int((65 + 180) * 10), int((15 + 90) * 10)] = 400
        with h5py.File(ruta, "w") as h:
            h["precipitation"], h["lon"], h["lat"] = lluvia, lon, lat
        hoy = lluvias.act.AHORA.date().isoformat()

        def pedir(url, destino=None):
            shutil.copy(ruta, destino)
            return destino
        with mock.patch.multiple(lluvias, pedir=pedir, ficheros=lambda mes: {hoy: "url"}, TOKEN="t"), \
             mock.patch.object(lluvias.act, "SALIDA", self.salida):
            lluvias.principal()
        r = self.leer("lluvias.json")
        self.assertEqual(list(r["paises"]), ["PAK"])
        self.assertEqual(r["paises"]["PAK"]["mm"], 180)
        self.assertEqual(r["eventos"][0]["tipo"], "lluvia")


if __name__ == "__main__":
    unittest.main()
