#!/usr/bin/env python3
"""Lluvias extremas por satélite (NASA GPM IMERG, versión rápida diaria).

Las inundaciones graves llegan después de días de lluvia excepcional. IMERG mide la lluvia de
todo el planeta en celdas de 0,1° (unos 11 km) con un día de retraso, mucho antes de que haya
una alerta oficial o imágenes de los daños.

Cómo se mide:
  - Cada día se descarga el último IMERG diario rápido ("Early") y se guardan solo las celdas
    con 50 mm o más (lo demás no puede sumar una lluvia extrema).
  - Una celda es extrema si en un día cae 150 mm o más, o si en tres días suma 250 mm o más.
    Son umbrales altos a propósito, porque en los trópicos 100 mm en un día es frecuente.
  - Se agrupan por país en tierra. Hay aviso si al menos 3 celdas (unos 350 km²) son extremas.

Necesita EARTHDATA_TOKEN, h5py y numpy. Escribe lluvias.json, que actualizar.py lee como una fuente.

Uso: python scripts/lluvias.py
"""

import json
import re
import sys
import urllib.error
import urllib.request
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import actualizar as act  # noqa: E402

TOKEN = act.os.environ.get("EARTHDATA_TOKEN", "").strip()
BASE = "https://gpm1.gesdisc.eosdis.nasa.gov/data/GPM_L3/GPM_3IMERGDE.07"
MINIMO_GUARDAR = 50      # mm/día (lo que se guarda de cada día)
LAT_MAX = 60             # IMERG es poco fiable sobre nieve y hielo, y en latitudes altas
EXTREMO_DIA = 150        # mm en un día
EXTREMO_TRES = 250       # mm en tres días
CELDAS_MIN = 3
KM2_CELDA = 123          # 0,1° × 0,1° cerca del ecuador (se corrige con la latitud)


def pedir(url, destino=None):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOKEN}", "User-Agent": "atalaya/1.0"})
    for _ in range(3):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                datos = r.read()
            if destino:
                destino.write_bytes(datos)
                return destino
            return datos
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            act.log(f"  GES DISC ha respondido HTTP {e.code}")
            if e.code in (401, 403):
                raise SystemExit("El token de Earthdata no vale o falta autorizar GES DISC en tu cuenta.")
        except (urllib.error.URLError, TimeoutError) as e:
            act.log(f"  sin respuesta ({e}), reintento")
    return None


def ficheros(dia):
    html = pedir(f"{BASE}/{dia.year}/{dia.month:02d}/")
    if not html:
        return {}
    nombres = set(re.findall(rb'href="(3B-DAY-E\.MS\.MRG\.3IMERG\.(\d{8})-[^"]+\.nc4)"', html))
    return {f"{d[:4].decode()}-{d[4:6].decode()}-{d[6:].decode()}": f"{BASE}/{dia.year}/{dia.month:02d}/{n.decode()}"
            for n, d in nombres}


def celdas_humedas(ruta):
    """Celdas con al menos MINIMO_GUARDAR mm entre ±LAT_MAX: [[lat, lon, mm], ...]."""
    import h5py
    import numpy as np
    with h5py.File(ruta, "r") as h:
        lluvia = h["precipitation"][0]          # (lon, lat), mm/día
        lon, lat = h["lon"][:], h["lat"][:]
    i, j = np.nonzero((lluvia >= MINIMO_GUARDAR) & (np.abs(lat)[None, :] <= LAT_MAX))
    return [[round(float(lat[b]), 2), round(float(lon[a]), 2), int(round(float(lluvia[a, b])))] for a, b in zip(i, j)]


def principal():
    if not TOKEN:
        act.log("Sin EARTHDATA_TOKEN: no se miran las lluvias.")
        return
    act.SALIDA.mkdir(parents=True, exist_ok=True)
    dias = act.leer("lluvias_dias.json", {})
    hoy = act.AHORA.date()
    disponibles = {}
    for mes in {hoy.replace(day=1), (hoy.replace(day=1) - timedelta(days=1)).replace(day=1)}:
        disponibles.update(ficheros(mes))
    recientes = sorted(d for d in disponibles if d >= (hoy - timedelta(days=5)).isoformat())
    tmp = act.SALIDA.parent / "tmp_lluvias"
    tmp.mkdir(exist_ok=True)
    for d in recientes:
        if d in dias:
            continue
        ruta = pedir(disponibles[d], tmp / f"{d}.nc4")
        if ruta:
            dias[d] = celdas_humedas(ruta)
            ruta.unlink(missing_ok=True)
            act.log(f"IMERG {d}: {len(dias[d])} celdas con {MINIMO_GUARDAR} mm o más")
    try:
        tmp.rmdir()
    except OSError:
        pass
    dias = {d: v for d, v in sorted(dias.items())[-4:]}
    act.escribir("lluvias_dias.json", dias)
    if not dias:
        return
    ultimos = sorted(dias)[-3:]
    suma, maximo = {}, {}
    for d in ultimos:
        for la, lo, mm in dias[d]:
            suma[(la, lo)] = suma.get((la, lo), 0) + mm
            if d == ultimos[-1]:
                maximo[(la, lo)] = mm
    extremas = [(la, lo, suma[(la, lo)]) for (la, lo) in suma
                if suma[(la, lo)] >= EXTREMO_TRES or maximo.get((la, lo), 0) >= EXTREMO_DIA]
    paises = act.Paises()
    por_pais = {}
    for la, lo, mm in extremas:
        a3 = paises.punto(lo, la)
        if a3 and a3 not in ("GRL", "ATA"):
            por_pais.setdefault(a3, []).append((la, lo, mm))
    eventos, resumen = [], {}
    import math
    for a3, celdas in por_pais.items():
        if len(celdas) < CELDAS_MIN:
            continue
        km2 = round(sum(KM2_CELDA * math.cos(math.radians(la)) for la, _, _ in celdas))
        tope = max(mm for _, _, mm in celdas)
        lat = sum(la for la, _, _ in celdas) / len(celdas)
        lon = sum(lo for _, lo, _ in celdas) / len(celdas)
        resumen[a3] = {"mm": round(tope), "km2": km2, "dias": ultimos}
        eventos.append({
            "id": f"lluvias-{a3}-{ultimos[-1]}", "tipo": "lluvia",
            "titulo": f"Lluvias extremas: hasta {round(tope)} mm en 3 días sobre unos {km2:,} km²".replace(",", "."),
            "lugar": "", "pais": a3, "lat": round(lat, 2), "lon": round(lon, 2),
            "fecha": f"{ultimos[-1]}T23:59:00Z", "peso": 3 if km2 >= 2500 else 2, "nivel": "verde",
            "fuente": "NASA GPM IMERG", "familia": "tecnica", "url": "https://gpm.nasa.gov/data/imerg",
        })
    # "actualizado" solo avanza si hay un día reciente: si GES DISC deja de dar datos, actualizar.py lo
    # ve caducado a los 3 días y lo avisa como fuente caída
    reciente = ultimos[-1] >= (hoy - timedelta(days=3)).isoformat()
    previo = act.leer("lluvias.json", {}).get("actualizado", "")
    act.escribir("lluvias.json", {"actualizado": act.iso(act.AHORA) if reciente else previo, "dias": ultimos,
                                  "eventos": eventos, "paises": resumen})
    act.log(f"IMERG: {len(extremas)} celdas extremas, {len(eventos)} países con lluvias extremas")


if __name__ == "__main__":
    sys.exit(principal())
