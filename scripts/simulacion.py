"""Simulación de escenarios: qué podría pasar en los próximos 7 días en las crisis abiertas.

AVISO: es una simulación automática con reglas sencillas, hecha a partir de noticias y datos
públicos. No es una predicción oficial ni un análisis de inteligencia, y no tiene ninguna
validez oficial. Sirve para pensar en posibilidades, no para tomar decisiones.

Para cada país en crisis se simulan tres ramas (se contiene, sigue igual, escala) con una
probabilidad aproximada que sale de los indicadores encendidos, la tendencia y el contagio
de los vecinos. Después se simula el contagio a los países vecinos y el impacto para España.
"""

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

PESOS_RIESGO = {"alto": 0.40, "medio": 0.25, "bajo": 0.10}


def _redondeo5(x):
    return int(round(x * 20)) * 5


def probabilidades(p, escenario, vecinos_mal):
    """Probabilidad aproximada (en múltiplos de 5 %) de cada rama en 7 días."""
    riesgo = p.get("pronostico", {}).get("riesgo", "bajo")
    pendiente = p.get("pronostico", {}).get("pendiente", 0)
    escala = PESOS_RIESGO[riesgo]
    if escenario:
        activos = sum(1 for i in escenario["indicadores"] if i["activo"])
        escala += min(0.15, 0.04 * activos)
    escala += 0.05 if pendiente > 0.5 else -0.05 if pendiente < -0.5 else 0
    escala += min(0.09, 0.03 * len(vecinos_mal or []))
    escala = max(0.05, min(0.70, escala))
    contiene = max(0.10, min(0.50, 0.45 - escala / 2 + (0.10 if pendiente < -0.5 else 0)))
    igual = 1 - escala - contiene
    ps = {"escala": _redondeo5(escala), "igual": _redondeo5(igual), "contiene": _redondeo5(contiene)}
    ps["igual"] += 100 - sum(ps.values())  # que sumen 100 tras redondear
    return ps


def palabras(pct):
    """Lenguaje estimativo para una probabilidad."""
    if pct >= 60:
        return "probable"
    if pct >= 40:
        return "tan probable como no"
    if pct >= 20:
        return "posible"
    return "poco probable"


def simular(alertas, vecinos, intereses_de, pasos_de, max_casos=8):
    """Simula las crisis más relevantes y el contagio a sus vecinos."""
    paises = alertas["paises"]
    candidatos = [a for a, p in paises.items()
                  if p["nivel"] != "verde" or p.get("pronostico", {}).get("riesgo") in ("alto", "medio")]
    orden = {"rojo": 0, "ambar": 1, "verde": 2}
    candidatos.sort(key=lambda a: (orden[paises[a]["nivel"]],
                                   {"alto": 0, "medio": 1}.get(paises[a].get("pronostico", {}).get("riesgo"), 2),
                                   -paises[a].get("puntuacion", 0)))
    casos, contagio = [], {}
    simulados = set(candidatos[:max_casos])
    for a3 in candidatos[:max_casos]:
        p = paises[a3]
        escenario = next((e for e in p.get("escenarios", []) if e["riesgo"] != "bajo"), None)
        tipo = escenario["id"] if escenario else None
        ps = probabilidades(p, escenario, p.get("vecinos_mal"))
        ramas = [{"id": r, "probabilidad": ps[r], "palabras": palabras(ps[r]), "texto": RAMAS[tipo][r]}
                 for r in ("escala", "igual", "contiene")]

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
            "pais": a3, "nivel": p["nivel"], "escenario": escenario["nombre"] if escenario else None,
            "confianza": p.get("confianza", "baja"), "ramas": ramas, "contagio": afectados[:4],
            "espana": impacto, "confirman": confirman, "desmienten": DESMIENTEN[tipo],
            "base": [i["texto"] for i in (escenario or {}).get("indicadores", []) if i["activo"]] or p.get("motivos", []),
        })
    return {"aviso": AVISO, "horizonte_dias": 7, "casos": casos,
            "contagio": dict(sorted(contagio.items(), key=lambda x: -x[1])[:20])}
