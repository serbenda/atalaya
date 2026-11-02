#!/usr/bin/env python3
"""Reconstrucción del pasado para medir el modelo (backtesting).

Rellena los días que faltan en historico.json reprocesando los ficheros históricos de GDELT
con las mismas reglas que usa atalaya cada 30 minutos: puntuación, niveles, escenarios y
pronóstico a 7 días. Así se puede medir el acierto del modelo desde el primer día, sin esperar
semanas de histórico propio.

Límites, para leer los resultados con cuidado:
  - Solo usa GDELT (conflictos y protestas). Terremotos, desastres, epidemias, cortes de
    internet y avisos de viaje no tienen un archivo histórico abierto y fácil de reprocesar.
  - Por coste, toma una muestra de ficheros de cada día (por defecto 12 de 96, uno cada 2 horas)
    y escala los recuentos.
  - Los días reconstruidos no entran en historial.json, que es la línea base de "lo habitual"
    de cada país: así no se mezcla una puntuación parcial con la completa.

Uso: python scripts/retroceso.py [días] [ficheros_por_día]
"""

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import actualizar as act  # noqa: E402
import inteligencia  # noqa: E402

CAMPOS_ESCALABLES = ("total", "conflicto", "protesta", "interestatal", "militar", "disturbios", "desescalada")


def marcas_del_dia(dia, muestras):
    paso = max(1, 96 // muestras)
    return [f"{dia.replace('-', '')}{(i * 15) // 60:02d}{(i * 15) % 60:02d}00" for i in range(0, 96, paso)]


def gdelt_del_dia(paises, dia, muestras):
    marcas = marcas_del_dia(dia, muestras)
    with ThreadPoolExecutor(max_workers=8) as hilos:
        bloques = list(hilos.map(act.gdelt_filas, marcas))
    buenos = [b for b in bloques if b]
    if len(buenos) < len(marcas) // 2:
        return None
    r = act.gdelt(paises, [f for b in buenos for f in b])
    factor = 96 / len(buenos)
    for g in r["paises"].values():
        for k in list(g):
            if k in CAMPOS_ESCALABLES or k.endswith("_12h") or k.endswith("_12h_antes"):
                g[k] = round(g[k] * factor, 1)
    return r["paises"]


def reconstruir(dias=30, muestras=12, hoy=None):
    hoy = hoy or act.HOY
    historico = act.leer("historico.json", {})
    registro = act.leer("retroceso.json", {"dias": []})
    paises = act.Paises()
    vecinos = inteligencia.calcular_vecinos(paises)
    base = {}  # línea base propia de la reconstrucción (solo GDELT)
    hecho = []
    original_hoy, original_ahora = act.HOY, act.AHORA
    try:
        inicio = datetime.strptime(hoy, "%Y-%m-%d") - timedelta(days=dias)
        for i in range(dias):
            dia = (inicio + timedelta(days=i)).strftime("%Y-%m-%d")
            act.HOY = dia
            act.AHORA = datetime.strptime(dia, "%Y-%m-%d").replace(hour=23, minute=59, tzinfo=timezone.utc)
            act.log(f"Reconstruyendo {dia}…")
            gd = gdelt_del_dia(paises, dia, muestras)
            if gd is None:
                act.log(f"  {dia}: faltan ficheros de GDELT, se salta")
                continue
            puntos = act.puntuar([], gd)
            base[dia] = {a3: p["puntuacion"] for a3, p in puntos.items()}
            if dia in historico and dia not in registro["dias"]:
                continue  # día real, ya medido con todas las fuentes: no se toca
            alertas = act.calcular_alertas(puntos, {d: base[d] for d in sorted(base) if d < dia})
            ctx = {"gdelt": gd, "pasos": {}, "vecinos": vecinos, "golpe_en_prensa": set(), "ucdp": {},
                   "exteriores": {}, "paises": alertas["paises"]}
            riesgo = {"bajo": 0, "medio": 1, "alto": 2}
            fila = {}
            for a3, p in alertas["paises"].items():
                escs, _ = inteligencia.escenarios(a3, p, ctx)
                pron = inteligencia.pronostico(p, escs)
                fila[a3] = [p["puntuacion"], act.RANGO[p["nivel"]], int(p["escalada"]), riesgo[pron["riesgo"]]]
            historico[dia] = fila
            hecho.append(dia)
    finally:
        act.HOY, act.AHORA = original_hoy, original_ahora
    act.escribir("historico.json", dict(sorted(historico.items())))
    registro["dias"] = sorted(set(registro["dias"]) | set(hecho))
    registro.update({"muestras": muestras, "actualizado": act.iso(act.AHORA),
                     "nota": "Días reconstruidos solo con GDELT y una muestra de ficheros: ver scripts/retroceso.py"})
    act.escribir("retroceso.json", registro)
    act.log(f"Reconstruidos {len(hecho)} días.")
    return hecho


if __name__ == "__main__":
    dias = min(90, max(1, int(sys.argv[1]))) if len(sys.argv) > 1 else 30
    muestras = int(sys.argv[2]) if len(sys.argv) > 2 else 12
    act.SALIDA.mkdir(parents=True, exist_ok=True)
    reconstruir(dias, muestras)
