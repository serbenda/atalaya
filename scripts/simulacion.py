"""Simulación de escenarios: qué podría pasar en los próximos 7 días en las crisis abiertas.

AVISO: es una simulación automática con reglas sencillas, hecha a partir de noticias y datos
públicos. No es una predicción oficial ni un análisis de inteligencia, y no tiene ninguna
validez oficial. Sirve para pensar en posibilidades, no para tomar decisiones.

Para cada país en crisis se simulan tres ramas (se contiene, sigue igual, escala) con una
probabilidad aproximada que sale de los indicadores encendidos, la tendencia y el contagio
de los vecinos. Después se simula el contagio a los países vecinos y el impacto para España.
"""

import math

AVISO = ("Simulación automática basada en noticias y datos públicos, con reglas sencillas. "
         "No es una predicción oficial ni un análisis de inteligencia y no tiene ninguna validez oficial. "
         "Para decisiones reales, consulta fuentes oficiales como el Ministerio de Asuntos Exteriores.")

RAMAS = {
    "escalada": {
        "escala": "Aumentan los ataques y los combates, con más desplazados dentro del país y hacia los vecinos.",
        "igual": "Los enfrentamientos siguen con la intensidad actual.",
        "contiene": "Baja la intensidad: treguas locales, mediación o negociaciones.",
    },
    "golpe": {
        "escala": "Ruptura institucional o estado de excepción: cortes de internet, toque de queda, cierre de fronteras y aeropuertos.",
        "igual": "Tensión política sin ruptura, con protestas y bloqueos intermitentes.",
        "contiene": "La crisis se encauza por vías institucionales y la tensión baja.",
    },
    "disturbios": {
        "escala": "Las protestas se extienden a más ciudades, con más respuesta policial y posibles cortes de internet.",
        "igual": "Protestas intermitentes, sin cambios importantes.",
        "contiene": "Las protestas remiten.",
    },
    "humanitaria": {
        "escala": "Más personas afectadas y desplazadas; riesgo de brotes por falta de agua y saneamiento; petición de ayuda internacional.",
        "igual": "La emergencia continúa, con la ayuda en marcha.",
        "contiene": "La situación mejora y empieza la recuperación.",
    },
    None: {
        "escala": "La situación empeora respecto a la semana pasada.",
        "igual": "La situación se mantiene parecida.",
        "contiene": "La situación mejora.",
    },
}

IMPACTO_ESPANA = {
    "Suministro de gas o petróleo": "Posible presión sobre los precios del gas o del petróleo en España.",
    "Rutas migratorias hacia España": "Posible aumento de salidas por las rutas migratorias hacia España.",
    "Despliegues militares españoles (revisar)": "Más riesgo para los militares españoles desplegados en la zona.",
    "Gran comunidad española residente": "Los españoles residentes podrían necesitar asistencia consular.",
    "Vecindad inmediata": "Efectos directos en la frontera y en la relación con España.",
}

DESMIENTEN = {
    "escalada": ["Varios días seguidos de menos violencia", "Anuncio de tregua o de negociaciones"],
    "golpe": ["Vuelve internet y se levantan los bloqueos", "Las instituciones siguen funcionando con normalidad"],
    "disturbios": ["Bajan las protestas varios días seguidos", "Acuerdo entre el gobierno y los convocantes"],
    "humanitaria": ["Baja el número de afectados", "Llega la ayuda internacional sin obstáculos"],
    None: ["La puntuación baja varios días seguidos"],
}

# Probabilidad de partida de "escala" según el pronóstico. Con la experiencia: en una semana lo más
# frecuente es que una crisis siga igual; las escaladas fuertes son la excepción.
PESOS_RIESGO = {"alto": 0.40, "medio": 0.25, "bajo": 0.10}
# Margen de incertidumbre (± puntos) según cuántas fuentes independientes coinciden
MARGEN = {"alta": 5, "media": 10, "baja": 15}
# Muestras mínimas de pronósticos ya comprobados antes de recalibrar con el acierto real
MUESTRAS_CALIBRAR = 20
DETALLADOS = 8
MAX_CASOS = 40


def _redondeo5(x):
    return int(round(x * 20)) * 5


def pesos_calibrados(fiabilidad):
    """Mezcla los pesos de partida con el acierto real de los pronósticos, cuando ya hay muestras.
    Si los 'probables' empeoran el 60 % de las veces, el peso de partida se acerca a ese 60 %."""
    pesos, calibrado = dict(PESOS_RIESGO), False
    for riesgo, f in (fiabilidad or {}).items():
        if riesgo in pesos and f.get("total", 0) >= MUESTRAS_CALIBRAR:
            observado = f["aciertos"] / f["total"]
            peso = min(1.0, f["total"] / 100)  # cuantas más muestras, más manda lo observado
            pesos[riesgo] = (1 - peso / 2) * pesos[riesgo] + (peso / 2) * observado
            calibrado = True
    return pesos, calibrado


def probabilidades(p, escenario, vecinos_mal, pesos=None):
    """Probabilidad aproximada (en múltiplos de 5 %) de cada rama en 7 días y por qué."""
    pesos = pesos or PESOS_RIESGO
    pron = p.get("pronostico", {})
    riesgo, pendiente = pron.get("riesgo", "bajo"), pron.get("pendiente", 0)
    acel = p.get("aceleracion") or 1
    escala = pesos[riesgo]
    factores = [f"pronóstico: {'probable' if riesgo == 'alto' else 'posible' if riesgo == 'medio' else 'poco probable'} que empeore"]
    if escenario:
        activos = sum(1 for i in escenario["indicadores"] if i["activo"])
        if activos:
            escala += min(0.15, 0.04 * activos)
            factores.append(f"{activos} {'indicador encendido' if activos == 1 else 'indicadores encendidos'}")
    if pendiente > 0.5:
        escala += 0.05
        factores.append("sube en la última semana")
    elif pendiente < -0.5:
        escala -= 0.05
        factores.append("baja en la última semana")
    if acel >= 1.8:
        escala += 0.08
        factores.append(f"se acelera en las últimas 12 horas (×{acel:g})")
    elif acel <= 0.55:
        escala -= 0.05
        factores.append("se frena en las últimas 12 horas")
    if vecinos_mal:
        escala += min(0.09, 0.03 * len(vecinos_mal))
        factores.append(f"{len(vecinos_mal)} {'vecino' if len(vecinos_mal) == 1 else 'vecinos'} en crisis")
    if p.get("nivel") == "rojo":
        escala += 0.05
        factores.append("ya está en alerta")
    if p.get("desescalada"):
        escala -= 0.08
        factores.append("hay señales de desescalada (negociaciones, tregua o acceso humanitario)")
    # Unas protestas en un país estable no "escalan" como una guerra: tope más bajo
    tope = 0.40 if escenario and escenario.get("id") == "disturbios" and p.get("nivel") == "verde" else 0.75
    escala = max(0.05, min(tope, escala))
    contiene = 0.45 - escala / 2 + (0.10 if pendiente < -0.5 or acel <= 0.55 else 0)
    # Una crisis prolongada rara vez se resuelve en una semana: lo esperable es que siga igual
    cronica = any(m in ("Crisis prolongada", "EE. UU. desaconseja viajar", "Exteriores desaconseja viajar",
                        "Crisis humanitaria abierta") or "UCDP" in m for m in p.get("motivos", []))
    if cronica:
        contiene -= 0.20
        factores.append("crisis prolongada: difícil que se resuelva en una semana")
    if p.get("desescalada"):
        contiene += 0.10
    contiene = max(0.05, min(0.50, contiene))
    igual = 1 - escala - contiene
    ps = {"escala": _redondeo5(escala), "igual": _redondeo5(igual), "contiene": _redondeo5(contiene)}
    ps["igual"] += 100 - sum(ps.values())  # que sumen 100 tras redondear
    return ps, factores


def intervalo(pct, confianza):
    m = MARGEN.get(confianza, 15)
    return [max(0, pct - m), min(100, pct + m)]


def palabras(pct):
    """Lenguaje estimativo para una probabilidad."""
    if pct >= 60:
        return "probable"
    if pct >= 40:
        return "tan probable como no"
    if pct >= 20:
        return "posible"
    return "poco probable"


def simular(alertas, vecinos, region_de, fiabilidad, intereses_de, pasos_de):
    """Simula todas las crisis abiertas (las más graves con detalle), el contagio y las regiones."""
    paises = alertas["paises"]
    pesos, calibrado = pesos_calibrados(fiabilidad)
    # Se simulan los países en alerta o para vigilar, y los demás solo si es probable que empeoren:
    # con un "posible" en un país sin alerta habría demasiado ruido
    candidatos = [a for a, p in paises.items()
                  if p["nivel"] != "verde" or p.get("pronostico", {}).get("riesgo") == "alto"]
    orden = {"rojo": 0, "ambar": 1, "verde": 2}
    candidatos.sort(key=lambda a: (orden[paises[a]["nivel"]],
                                   {"alto": 0, "medio": 1}.get(paises[a].get("pronostico", {}).get("riesgo"), 2),
                                   -paises[a].get("puntuacion", 0)))
    candidatos = candidatos[:MAX_CASOS]
    simulados = set(candidatos)
    casos, contagio = [], {}
    for a3 in candidatos:
        p = paises[a3]
        escenario = next((e for e in p.get("escenarios", []) if e["riesgo"] != "bajo"), None)
        tipo = escenario["id"] if escenario else None
        ps, factores = probabilidades(p, escenario, p.get("vecinos_mal"), pesos)
        confianza = p.get("confianza", "baja")
        ramas = [{"id": r, "probabilidad": ps[r], "intervalo": intervalo(ps[r], confianza),
                  "palabras": palabras(ps[r]), "texto": RAMAS[tipo][r]} for r in ("escala", "igual", "contiene")]

        # Contagio: si el país escala, los vecinos más frágiles tienen más papeletas
        afectados = []
        for v in vecinos.get(a3, []):
            if v in simulados:  # ya está en crisis: no es contagio
                continue
            q = paises.get(v, {})
            fragil = 1.5 if q.get("nivel", "verde") != "verde" else 1.0
            prob = ps["escala"] / 100 * 0.35 * fragil
            if prob >= 0.05:
                afectados.append({"pais": v, "probabilidad": _redondeo5(prob)})
                contagio[v] = max(contagio.get(v, 0), _redondeo5(prob))
        afectados.sort(key=lambda x: -x["probabilidad"])

        impacto = [IMPACTO_ESPANA[t] for t in intereses_de(a3) if t in IMPACTO_ESPANA]
        for nombre_paso in pasos_de(a3):
            impacto.append(f"Posibles desvíos en {nombre_paso}: fletes más caros y retrasos en el comercio.")
        if (p.get("exteriores") or {}).get("nivel", 0) >= 3:
            impacto.append("Exteriores ya desaconseja viajar al país.")

        confirman = [i["texto"] for i in (escenario or {}).get("indicadores", []) if not i["activo"]][:3]
        casos.append({
            "pais": a3, "nivel": p["nivel"], "region": region_de.get(a3),
            "escenario": escenario["nombre"] if escenario else None,
            "confianza": confianza, "ramas": ramas, "factores": factores, "contagio": afectados[:4],
            "espana": impacto, "confirman": confirman, "desmienten": DESMIENTEN[tipo],
            "base": [i["texto"] for i in (escenario or {}).get("indicadores", []) if i["activo"]] or p.get("motivos", []),
        })

    # Los más graves primero; dentro de cada nivel, los que más pueden escalar
    casos.sort(key=lambda c: (orden[c["nivel"]], -c["ramas"][0]["probabilidad"]))

    # Regiones: probabilidad de que al menos una de sus crisis escale en la semana
    regiones = {}
    for c in casos:
        if c["region"]:
            regiones.setdefault(c["region"], []).append(c)
    por_region = []
    for region, lista in regiones.items():
        # Las crisis de una misma región no son independientes (se alimentan entre sí): en lugar de
        # multiplicar como si lo fueran, se usa la media elevada a la raíz del número de crisis
        media = sum(c["ramas"][0]["probabilidad"] for c in lista) / 100 / len(lista)
        prob = 1 - (1 - media) ** math.sqrt(len(lista))
        por_region.append({"region": region, "probabilidad": _redondeo5(prob),
                           "paises": [c["pais"] for c in sorted(lista, key=lambda c: -c["ramas"][0]["probabilidad"])]})
    por_region.sort(key=lambda r: -r["probabilidad"])

    # Lo que más preocupa no es solo lo más probable, sino lo más probable y más grave a la vez
    gravedad = {"rojo": 3, "ambar": 2, "verde": 1}
    tipo_peso = {"Escalada militar": 1.0, "Golpe o crisis de gobierno": 1.0, "Emergencia humanitaria": 1.0,
                 "Disturbios graves": 0.6}
    mas_escala = sorted(casos, key=lambda c: -c["ramas"][0]["probabilidad"] * gravedad[c["nivel"]]
                        * tipo_peso.get(c["escenario"], 0.8))[:3]
    mas_contiene = sorted(casos, key=lambda c: -c["ramas"][2]["probabilidad"])[:3]
    return {
        "aviso": AVISO, "horizonte_dias": 7, "detallados": DETALLADOS, "calibrado": calibrado,
        "pesos": {k: _redondeo5(v) for k, v in pesos.items()},
        "resumen": {"mas_escala": [c["pais"] for c in mas_escala], "mas_contiene": [c["pais"] for c in mas_contiene],
                    "media_escala": _redondeo5(sum(c["ramas"][0]["probabilidad"] for c in casos) / 100 / len(casos)) if casos else 0},
        "casos": casos, "regiones": por_region[:8],
        "contagio": dict(sorted(contagio.items(), key=lambda x: -x[1])[:25]),
    }
