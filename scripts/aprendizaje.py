"""Pronóstico aprendido de los datos.

En vez de fijar a mano cuánto pesa cada señal, se aprende de lo que pasó: con el histórico
(real y reconstruido con GDELT) se ajusta una regresión logística que estima la probabilidad
de que un país empeore en los 7 días siguientes.

Reglas para que sea honesto:
  - Se valida en el tiempo: se entrena con los días más antiguos y se mide con los más
    recientes, que el modelo no ha visto. Solo se usa si en esos días acierta más que la
    referencia ingenua (decir siempre la frecuencia media).
  - Solo usa señales que existen tanto en los días reales como en los reconstruidos
    (GDELT, la puntuación y su evolución). Los cortes de internet, la censura o los avisos
    de viaje siguen contando en los escenarios y en la simulación.
  - Sin librerías: Python estándar, para que funcione igual en cualquier sitio.
"""

import math
import statistics

# Señales que entran en el modelo, en este orden (se guardan así en historico.json)
RASGOS = ("puntuacion", "nivel", "escalada", "z", "pendiente", "dias_subiendo", "aceleracion",
          "cuota_violencia", "entre_paises", "protestas", "militar", "desescalada", "vecinos_mal", "media")
NOMBRES = {
    "puntuacion": "Puntuación actual", "nivel": "Nivel actual", "escalada": "Ya está empeorando",
    "z": "Distancia a lo habitual", "pendiente": "Tendencia de la semana", "dias_subiendo": "Días seguidos subiendo",
    "aceleracion": "Aceleración en 12 horas", "cuota_violencia": "Parte de la cobertura que es violencia",
    "entre_paises": "Hechos entre países", "protestas": "Peso de las protestas", "militar": "Hechos con ejércitos o grupos armados",
    "desescalada": "Señales de desescalada", "vecinos_mal": "Vecinos en alerta", "media": "Nivel habitual del país",
}
MIN_ENTRENAR = 300   # muestras mínimas para entrenar
MIN_PROBAR = 100     # muestras mínimas para validar
PARTE_PRUEBA = 0.3   # últimos días reservados para validar
L2 = 0.01
ITERACIONES = 400
PASO = 0.5


def pendiente(serie):
    s = serie[-7:]
    if len(s) < 3:
        return 0.0
    xs = range(len(s))
    mx, my = statistics.fmean(xs), statistics.fmean(s)
    den = sum((x - mx) ** 2 for x in xs)
    return sum((x - mx) * (y - my) for x, y in zip(xs, s)) / den if den else 0.0


def acotar(x, lo, hi):
    return max(lo, min(hi, x))


def rasgos(p, g, vecinos_mal=0):
    """Vector de señales de un país (p: su ficha de alertas; g: su resumen de GDELT)."""
    rango = {"verde": 0, "ambar": 1, "rojo": 2}.get(p.get("nivel"), 0)
    conflicto = g.get("conflicto", 0)
    total = max(g.get("conflicto", 0) + g.get("protesta", 0), 1)
    acel = p.get("aceleracion") or 1
    # El modelo aprende de días reconstruidos solo con GDELT: en los días reales se usa también solo la
    # parte de GDELT (conflictos y protestas), para no comparar peras con manzanas. El nivel habitual
    # se reescala con la misma proporción.
    total_hoy = max(p.get("puntuacion", 0), 0)
    gdelt_hoy = (p.get("conflicto") or 0) + (p.get("protestas") or 0)
    if "conflicto" not in p and "protestas" not in p:
        gdelt_hoy = total_hoy
    proporcion = gdelt_hoy / total_hoy if total_hoy else 1.0
    valores = {
        "puntuacion": math.log1p(gdelt_hoy),
        "nivel": rango / 2,
        "escalada": float(bool(p.get("escalada"))),
        "z": acotar(p.get("z", 0), -3, 5) / 5,
        "pendiente": acotar(pendiente(p.get("serie") or []), -5, 5) / 5,
        "dias_subiendo": min(p.get("dias_subiendo", 0), 7) / 7,
        "aceleracion": acotar(math.log(max(acel, 0.05)), -2, 2) / 2,
        "cuota_violencia": acotar(p.get("cuota_violencia", 0), 0, 1),
        "entre_paises": g.get("interestatal", 0) / conflicto if conflicto else 0.0,
        "protestas": g.get("protesta", 0) / total,
        "militar": g.get("militar", 0) / conflicto if conflicto else 0.0,
        "desescalada": acotar(g.get("desescalada", 0) / max(conflicto, 1), 0, 1),
        "vecinos_mal": min(vecinos_mal, 3) / 3,
        "media": math.log1p(max(p.get("media", 0), 0) * proporcion),
    }
    return [round(valores[r], 4) for r in RASGOS]


def empeoro(historico, a3, fila, siguientes):
    """Lo que se quiere predecir: en los 7 días siguientes el país sube de nivel, o empieza a
    empeorar cuando no lo estaba. (Si ya estaba empeorando, seguir así no cuenta como acierto fácil.)"""
    rango, escalaba = fila[1], fila[2]
    for d in siguientes:
        otra = historico[d].get(a3)
        if not otra:
            continue
        if otra[1] > rango or (otra[2] and not escalaba):
            return True
    return False


def muestras(historico, reconstruidos=()):
    """(día, rasgos, resultado) de cada país y día con 7 días de futuro, sin mezclar días reales
    con reconstruidos en una misma ventana."""
    fechas = sorted(historico)
    salida = []
    for i, d in enumerate(fechas):
        siguientes = fechas[i + 1:i + 8]
        if len(siguientes) < 7 or len({x in reconstruidos for x in [d, *siguientes]}) > 1:
            continue
        for a3, fila in historico[d].items():
            if len(fila) < 6 or not fila[5]:
                continue
            salida.append((d, fila[5], int(empeoro(historico, a3, fila, siguientes))))
    return salida


def sigmoide(x):
    return 1 / (1 + math.exp(-acotar(x, -30, 30)))


def ajustar(X, y):
    """Regresión logística con regularización L2 por descenso de gradiente (variables tipificadas)."""
    n, k = len(X), len(X[0])
    medias = [statistics.fmean(f[j] for f in X) for j in range(k)]
    desv = [statistics.pstdev([f[j] for f in X]) or 1.0 for j in range(k)]
    Z = [[(f[j] - medias[j]) / desv[j] for j in range(k)] for f in X]
    tasa = sum(y) / n
    b = math.log(max(tasa, 1e-3) / max(1 - tasa, 1e-3))
    w = [0.0] * k
    for _ in range(ITERACIONES):
        gw, gb = [0.0] * k, 0.0
        for z, yi in zip(Z, y):
            e = sigmoide(b + sum(wj * zj for wj, zj in zip(w, z))) - yi
            gb += e
            for j in range(k):
                gw[j] += e * z[j]
        b -= PASO * gb / n
        w = [wj - PASO * (gj / n + L2 * wj) for wj, gj in zip(w, gw)]
    return {"medias": medias, "desv": desv, "pesos": w, "sesgo": b}


def predecir(modelo, x):
    z = [(xi - m) / s for xi, m, s in zip(x, modelo["medias"], modelo["desv"])]
    return sigmoide(modelo["sesgo"] + sum(w * zi for w, zi in zip(modelo["pesos"], z)))


def brier(ps, ys):
    return sum((p - y) ** 2 for p, y in zip(ps, ys)) / len(ys)


def calibracion(ps, ys):
    grupos = []
    for nombre, lo, hi in (("bajo", 0, 0.2), ("medio", 0.2, 0.4), ("alto", 0.4, 1.01)):
        sel = [(p, y) for p, y in zip(ps, ys) if lo <= p < hi]
        if sel:
            grupos.append({"riesgo": nombre, "dicho": round(statistics.fmean(p for p, _ in sel), 3),
                           "observado": round(statistics.fmean(y for _, y in sel), 3), "muestras": len(sel)})
    return grupos


def entrenar(historico, reconstruidos=(), hoy=""):
    """Entrena y valida. Devuelve el modelo (activo o no) con sus métricas fuera de muestra."""
    datos = muestras(historico, set(reconstruidos))
    dias = sorted({d for d, _, _ in datos})
    resultado = {"rasgos": list(RASGOS), "muestras": len(datos), "dias": len(dias), "activo": False,
                 "entrenado": hoy}
    if len(dias) < 10:
        resultado["motivo"] = "Pocos días con 7 días de futuro"
        return resultado
    corte = dias[int(len(dias) * (1 - PARTE_PRUEBA))]
    ent = [(x, y) for d, x, y in datos if d < corte]
    pru = [(x, y) for d, x, y in datos if d >= corte]
    if len(ent) < MIN_ENTRENAR or len(pru) < MIN_PROBAR:
        resultado["motivo"] = "Pocas muestras para entrenar y validar"
        return resultado
    m = ajustar([x for x, _ in ent], [y for _, y in ent])
    ps = [predecir(m, x) for x, _ in pru]
    ys = [y for _, y in pru]
    tasa = sum(y for _, y in ent) / len(ent)
    b_modelo, b_ref = brier(ps, ys), brier([tasa] * len(ys), ys)
    mejora = 1 - b_modelo / b_ref if b_ref else 0
    resultado["validacion"] = {"desde": corte, "muestras": len(pru), "brier": round(b_modelo, 4),
                               "brier_referencia": round(b_ref, 4), "mejora": round(mejora, 3),
                               "calibracion": calibracion(ps, ys)}
    if mejora <= 0:
        resultado["motivo"] = "En los días de validación no acierta más que la frecuencia media"
        return resultado
    # Validado: se reentrena con todo para usar la información más reciente
    final = ajustar([x for _, x, _ in datos], [y for _, _, y in datos])
    importancia = sorted(zip(RASGOS, final["pesos"]), key=lambda x: -abs(x[1]))
    resultado.update({"activo": True, "modelo": final, "frecuencia": round(sum(y for *_, y in datos) / len(datos), 3),
                      "importancia": [{"rasgo": r, "nombre": NOMBRES[r], "peso": round(w, 3)} for r, w in importancia]})
    return resultado
