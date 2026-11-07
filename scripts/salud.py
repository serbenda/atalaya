#!/usr/bin/env python3
"""Revisa el estado de las fuentes tras una actualización.

Códigos de salida, que usa la Action para la issue "Fuentes de datos caídas":
  0: todas responden (si hay una issue abierta, se cierra)
  1: una fuente acaba de llegar a FALLOS_PARA_AVISAR fallos seguidos, o toca el recordatorio
     diario: se abre la issue o se comenta en ella
  2: siguen caídas, pero ya se avisó: no se hace nada
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from actualizar import FALLOS_PARA_AVISAR, SALIDA  # noqa: E402

AVISO_CADA = 48  # ejecuciones entre recordatorios (una al día)


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
    # Se avisa cuando una fuente acaba de llegar al umbral, y luego una vez al día mientras siga caída:
    # así la issue no recibe un comentario cada 30 minutos
    nuevas = [n for n, f in caidas.items() if (f["fallos_seguidos"] - FALLOS_PARA_AVISAR) % AVISO_CADA == 0]
    if not nuevas:
        print("Siguen caídas: " + ", ".join(caidas) + " (ya avisado).")
        return 2
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
