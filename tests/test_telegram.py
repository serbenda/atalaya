"""Pruebas de los avisos por Telegram y del feed RSS (sin red: el envío se simula)."""

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent


def cargar(salida, token="t", chat="c"):
    os.environ["ATALAYA_SALIDA"] = str(salida)
    os.environ["TELEGRAM_TOKEN"] = token
    os.environ["TELEGRAM_CHAT"] = chat
    spec = importlib.util.spec_from_file_location("telegram_atalaya", RAIZ / "scripts" / "telegram.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def alertas(nivel="verde", escalada=False, paso="verde"):
    return {"paises": {"SDN": {"nivel": nivel, "escalada": escalada, "confianza": "media",
                               "motivos": ["Combates en Darfur"], "pronostico": {"texto": "Probable que siga"}}},
            "pasos": [{"id": "ormuz", "nombre": "Estrecho de Ormuz", "nivel": paso,
                       "porque": "Hechos violentos cerca", "hechos": 7}],
            "informe": {"conclusion": {"pais": "SDN", "texto": "Riesgo alto"}, "juicios": [], "espana": []}}


class TestTelegram(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.salida = Path(self.dir.name)
        self.enviados = []

    def tearDown(self):
        self.dir.cleanup()
        for v in ("ATALAYA_SALIDA", "TELEGRAM_TOKEN", "TELEGRAM_CHAT"):
            os.environ.pop(v, None)

    def escribir(self, nombre, datos):
        (self.salida / nombre).write_text(json.dumps(datos), "utf-8")

    def ejecutar(self, mod):
        with mock.patch.object(mod, "enviar", side_effect=lambda t: self.enviados.append(t) or True), \
             mock.patch.object(mod, "HORA_RESUMEN_UTC", 99):
            mod.main()

    def test_primera_vez_no_avisa(self):
        self.escribir("alertas.json", alertas("rojo"))
        self.escribir("eventos.json", {"eventos": []})
        self.ejecutar(cargar(self.salida))
        self.assertEqual(self.enviados, [])
        estado = json.loads((self.salida / "telegram.json").read_text())
        self.assertEqual(estado["niveles"]["SDN"], "rojo")

    def test_subida_de_nivel_y_sin_repetir(self):
        self.escribir("telegram.json", {"niveles": {"SDN": "verde"}, "enviados": {}})
        self.escribir("alertas.json", alertas("rojo"))
        self.escribir("eventos.json", {"eventos": []})
        mod = cargar(self.salida)
        self.ejecutar(mod)
        self.assertEqual(len(self.enviados), 1)
        self.assertIn("pasa a alerta", self.enviados[0])
        self.assertIn("(confianza media)", self.enviados[0])
        self.assertIn("sin validez oficial", self.enviados[0])
        self.ejecutar(mod)  # misma situación: nada nuevo
        self.assertEqual(len(self.enviados), 1)

    def test_paso_maritimo_y_rss(self):
        self.escribir("telegram.json", {"niveles": {"SDN": "ambar"}, "pasos": {"ormuz": "ambar"}, "enviados": {}})
        self.escribir("alertas.json", alertas("ambar", paso="rojo"))
        self.escribir("eventos.json", {"eventos": []})
        self.ejecutar(cargar(self.salida))
        self.assertTrue(any("Ormuz" in t for t in self.enviados))
        rss = (self.salida / "avisos.xml").read_text("utf-8")
        self.assertIn("<rss", rss)
        self.assertIn("Estrecho de Ormuz", rss)
        self.assertIn("sin validez oficial", rss)

    def test_sin_bot_solo_rss(self):
        self.escribir("telegram.json", {"niveles": {"SDN": "verde"}, "enviados": {}})
        self.escribir("alertas.json", alertas("rojo"))
        self.escribir("eventos.json", {"eventos": []})
        self.ejecutar(cargar(self.salida, token="", chat=""))
        self.assertEqual(self.enviados, [])
        self.assertIn("pasa a alerta", (self.salida / "avisos.xml").read_text("utf-8"))

    def test_espera_por_pais(self):
        mod = cargar(self.salida)
        reciente = mod.AHORA.strftime("%Y-%m-%dT%H:%M:%SZ")
        avisos = [("escalada-SDN", "SDN", "x", False), ("nivel-SDN-rojo", "SDN", "y", True)]
        quedan = mod.filtrar(avisos, {"ultimo_pais": {"SDN": reciente}})
        self.assertEqual([a[0] for a in quedan], ["nivel-SDN-rojo"])


if __name__ == "__main__":
    unittest.main()
