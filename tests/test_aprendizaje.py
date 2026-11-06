"""Pruebas del pronóstico aprendido."""

import random
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import aprendizaje  # noqa: E402


def historico_sintetico(senal_util=True, dias=40, paises=40, semilla=1):
    """Países cuyo nivel sube unos días después de que se encienda una señal (si es útil)."""
    rnd = random.Random(semilla)
    inicio = date(2026, 9, 1)
    fechas = [(inicio + timedelta(days=i)).isoformat() for i in range(dias)]
    h = {d: {} for d in fechas}
    for k in range(paises):
        a3 = f"P{k:02d}"
        nivel = 0
        aviso = {}
        for i, d in enumerate(fechas):
            senal = rnd.random() < 0.15
            if senal:
                aviso[i] = True
            if senal_util and aviso.get(i - 3) and nivel < 2:
                nivel += 1
            elif rnd.random() < 0.08:
                nivel = max(0, nivel - 1)
            x = [0.0] * len(aprendizaje.RASGOS)
            x[aprendizaje.RASGOS.index("aceleracion")] = 1.0 if senal else 0.0
            x[aprendizaje.RASGOS.index("nivel")] = nivel / 2
            x[aprendizaje.RASGOS.index("puntuacion")] = rnd.random()
            h[d][a3] = [10, nivel, 0, 0, None, x]
    return h


class TestAprendizaje(unittest.TestCase):
    def test_aprende_una_senal_util(self):
        r = aprendizaje.entrenar(historico_sintetico(True), hoy="2026-10-15")
        self.assertTrue(r["activo"], r.get("motivo"))
        self.assertGreater(r["validacion"]["mejora"], 0)
        pesos = {x["rasgo"]: x["peso"] for x in r["importancia"]}
        self.assertGreater(pesos["aceleracion"], 0.3)  # la señal útil empuja hacia "empeora"
        self.assertLess(abs(pesos["puntuacion"]), abs(pesos["aceleracion"]))  # el ruido pesa menos

    def test_no_se_usa_si_no_mejora(self):
        r = aprendizaje.entrenar(historico_sintetico(False, semilla=7), hoy="2026-10-15")
        self.assertFalse(r["activo"])
        self.assertIn("motivo", r)

    def test_pocos_datos(self):
        r = aprendizaje.entrenar(historico_sintetico(True, dias=8), hoy="2026-10-15")
        self.assertFalse(r["activo"])

    def test_empeorar_no_cuenta_seguir_empeorando(self):
        h = {"d1": {"X": [5, 1, 1, 0]}, "d2": {"X": [5, 1, 1, 0]}}
        self.assertFalse(aprendizaje.empeoro(h, "X", h["d1"]["X"], ["d2"]))
        h["d2"]["X"] = [9, 2, 1, 0]
        self.assertTrue(aprendizaje.empeoro(h, "X", h["d1"]["X"], ["d2"]))

    def test_rasgos(self):
        x = aprendizaje.rasgos({"nivel": "rojo", "puntuacion": 20, "escalada": True, "z": 2, "serie": [1, 2, 3, 4],
                                "aceleracion": 2, "media": 5}, {"conflicto": 10, "interestatal": 5, "protesta": 10}, 2)
        self.assertEqual(len(x), len(aprendizaje.RASGOS))
        self.assertEqual(x[aprendizaje.RASGOS.index("nivel")], 1.0)
        self.assertEqual(x[aprendizaje.RASGOS.index("entre_paises")], 0.5)


if __name__ == "__main__":
    unittest.main()
