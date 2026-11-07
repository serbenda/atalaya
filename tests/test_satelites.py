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


def baldosa_h5(ruta, luz, nubes=0, centro=(15.55, 32.53)):
    """Baldosa VJ146A1 de juguete: 100×100 píxeles alrededor de Jartum."""
    lat = centro[0] + (50 - np.arange(100)) / 240
    lon = centro[1] + (np.arange(100) - 50) / 240
    campos = {"DNB_At_Sensor_Radiance": (luz, "float32"), "QF_Cloud_Mask": (nubes, "uint16"), "QF_DNB": (0, "uint8"),
              "Sensor_Zenith": (1500, "int16"), "Moon_Illumination_Fraction": (1000, "uint16"),
              "Lunar_Zenith": (12000, "int16")}
    with h5py.File(ruta, "w") as h:
        g = h.create_group("HDFEOS/GRIDS/VIIRS_Grid_DNB_2d/Data Fields")
        g["lat"], g["lon"] = lat, lon
        for nombre, (valor, tipo) in campos.items():
            g[nombre] = np.full((100, 100), valor, dtype=tipo)


@unittest.skipUnless(h5py, "necesita h5py y numpy")
class TestLuces(Base):
    def preparar(self, luz, nubes=0, noches_previas=None):
        import luces
        self.luces = importlib.reload(luces)
        self.escribir("alertas.json", {"paises": {"SDN": {"conflicto": 20, "nivel": "rojo"}}})
        self.escribir("eventos.json", {"eventos": [{"tipo": "conflicto", "pais": "SDN", "lugar": "Khartoum, Khartoum, Sudan",
                                                    "lat": 15.55, "lon": 32.53, "hechos": 30}]})
        self.assertEqual(self.luces.baldosa(15.55, 32.53), "h21v07")
        self.ruta = Path(self.dir) / "diario.h5"
        baldosa_h5(self.ruta, luz, nubes)
        hoy = self.luces.AHORA.date() - timedelta(days=1)
        ide = "sdn-khartoum"
        if noches_previas:
            self.escribir("luces_historial.json", {ide: {(hoy - timedelta(days=d)).isoformat(): v
                                                         for d, v in noches_previas.items()}})
            # los días previos ya se leyeron: no hace falta rellenar
            self.escribir("luces_estado.json", {"dias": [(hoy - timedelta(days=d)).isoformat() for d in range(1, 31)]})
        lista = {f"h{i:02d}v{j:02d}": "url" for i in range(36) for j in range(18)}

        def pedir(url, destino=None):
            shutil.copy(self.ruta, destino)
            return destino
        return mock.patch.multiple(self.luces, pedir=pedir, ficheros_del_dia=lambda p, d: lista, TOKEN="t",
                                   SALIDA=self.salida)

    def test_apagon_sostenido(self):
        normales = {d: 40.0 for d in range(3, 12)}
        normales[2] = 11.0                                   # la noche anterior ya estaba a oscuras
        with self.preparar(10.0, noches_previas=normales):
            self.luces.principal()
        r = self.leer("luces.json")
        self.assertEqual(r["paises"], {"SDN": 0.25})
        self.assertEqual(r["eventos"][0]["tipo"], "apagon")
        self.assertIn("Khartoum", r["eventos"][0]["titulo"])
        self.assertEqual(r["eventos"][0]["peso"], 3)

    def test_una_noche_no_basta(self):
        with self.preparar(10.0, noches_previas={d: 40.0 for d in range(2, 12)}):
            self.luces.principal()
        self.assertEqual(self.leer("luces.json")["eventos"], [])

    def test_luz_normal_y_nubes(self):
        with self.preparar(38.0, noches_previas={d: 40.0 for d in range(2, 12)}):
            self.luces.principal()
        r = self.leer("luces.json")
        self.assertEqual(r["eventos"], [])
        self.assertAlmostEqual(r["lugares"]["sdn-khartoum"]["razon"], 0.95)
        # con nubes (bits 6-7 = 11) la noche no cuenta
        with self.preparar(1.0, nubes=0b11000000, noches_previas={d: 40.0 for d in range(2, 12)}):
            self.luces.principal()
        self.assertAlmostEqual(self.leer("luces.json")["lugares"]["sdn-khartoum"]["razon"], 1.0)

    def test_rellena_el_pasado(self):
        with self.preparar(40.0):
            self.luces.principal()
        self.assertEqual(len(self.leer("luces_estado.json")["dias"]), 1 + self.luces.RELLENO_POR_EJECUCION)


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
