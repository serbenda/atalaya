#!/usr/bin/env python3
"""Revisa el estado de las fuentes tras una actualización.

Sale con código 1 e imprime un informe en Markdown si alguna fuente lleva
varias ejecuciones seguidas fallando; la Action lo usa para abrir un issue.
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from actualizar import FALLOS_PARA_AVISAR, SALIDA  # noqa: E402


def main():
    try:
        estado = json.loads((SALIDA / "eventos.json").read_text("utf-8")).get("fuentes", {})
    except (OSError, ValueError) as e:
        print(f"No se ha podido leer `eventos.json`: {e}")
        return 1
    caidas = {n: f for n, f in estado.items() if f.get("fallos_seguidos", 0) >= FALLOS_PARA_AVISAR}
    if not caidas:
        print("Todas las fuentes responden.")
        return 0
    print("Estas fuentes llevan al menos "
          f"{FALLOS_PARA_AVISAR} actualizaciones seguidas fallando. El mapa sigue mostrando sus últimos datos buenos.\n")
    print("| Fuente | Error | Fallos seguidos | Último dato bueno |")
    print("|---|---|---|---|")
    for n, f in caidas.items():
        print(f"| {n} | {f.get('error') or '-'} | {f.get('fallos_seguidos')} | {f.get('ultimo_ok') or 'nunca'} |")
    ejecucion = os.environ.get("ENLACE_EJECUCION")
    if ejecucion:
        print(f"\nRegistro de la ejecución: {ejecucion}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
