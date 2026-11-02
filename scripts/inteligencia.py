"""Capa de análisis: lo que un gabinete de crisis añadiría a los datos.

- Escenarios con indicadores de alerta temprana (método de indicadores y alertas):
  cada escenario tiene una lista de indicadores observables y se mide cuántos están encendidos.
- Pronóstico a 7 días con lenguaje estimativo (probable, posible, poco probable), al estilo
  de los informes de inteligencia, y medición de su acierto con el histórico.
- Contagio regional: los conflictos se contagian a los vecinos.
- Interés para España: qué alertas afectan más a España y por qué.
- Informe diario: conclusión principal, juicios clave, qué vigilar y regiones.

Todo es transparente: cada juicio dice qué indicadores lo sostienen.
"""

import statistics

RANGO = {"verde": 0, "ambar": 1, "rojo": 2}
RIESGO = {0: "bajo", 1: "medio", 2: "alto"}
# Lenguaje estimativo (inspirado en la norma ICD 203 de la comunidad de inteligencia de EE. UU.)
ESTIMATIVO = {"alto": "Probable", "medio": "Posible", "bajo": "Poco probable"}

REGIONES = {
    "Magreb": ["MAR", "DZA", "TUN", "LBY", "ESH"],
    "Sahel": ["MRT", "MLI", "BFA", "NER", "TCD"],
    "África Occidental": ["SEN", "GMB", "GNB", "GIN", "SLE", "LBR", "CIV", "GHA", "TGO", "BEN", "NGA", "CPV"],
    "Cuerno de África y Sudán": ["SDN", "SSD", "ETH", "ERI", "DJI", "SOM", "KEN"],
    "África Central y Grandes Lagos": ["COD", "COG", "CAF", "CMR", "GAB", "GNQ", "RWA", "BDI", "UGA", "TZA"],
    "África Austral": ["AGO", "ZMB", "ZWE", "MOZ", "MWI", "NAM", "BWA", "ZAF", "LSO", "SWZ", "MDG"],
    "Oriente Próximo": ["ISR", "PSE", "LBN", "SYR", "JOR", "IRQ", "EGY"],
    "Golfo e Irán": ["SAU", "YEM", "OMN", "ARE", "QAT", "BHR", "KWT", "IRN"],
    "Mediterráneo oriental": ["TUR", "CYP", "GRC"],
    "Europa del Este": ["UKR", "RUS", "BLR", "MDA", "POL", "LTU", "LVA", "EST", "ROU"],
    "Cáucaso": ["GEO", "ARM", "AZE"],
    "Balcanes": ["SRB", "XKX", "BIH", "MNE", "MKD", "ALB"],
    "Asia Central y Afganistán": ["KAZ", "UZB", "TKM", "KGZ", "TJK", "AFG"],
    "Asia Meridional": ["PAK", "IND", "BGD", "NPL", "LKA", "BTN"],
    "Sudeste Asiático": ["MMR", "THA", "LAO", "KHM", "VNM", "MYS", "IDN", "PHL", "TLS"],
    "Asia Oriental": ["CHN", "TWN", "PRK", "KOR", "JPN", "MNG"],
    "Centroamérica y Caribe": ["MEX", "GTM", "BLZ", "SLV", "HND", "NIC", "CRI", "PAN", "CUB", "HTI", "DOM", "JAM"],
    "Sudamérica": ["COL", "VEN", "ECU", "PER", "BOL", "BRA", "PRY", "ARG", "CHL", "URY", "GUY", "SUR"],
}
REGION_DE = {a3: r for r, lista in REGIONES.items() for a3 in lista}

# Países que dan al paso marítimo (si el paso se calienta, les afecta)
PASOS_PAISES = {"ormuz": ["IRN", "OMN", "ARE"], "bab": ["YEM", "DJI", "ERI"], "suez": ["EGY"],
                "bosforo": ["TUR"], "gibraltar": ["ESP", "MAR"], "malaca": ["MYS", "IDN", "SGP"],
                "taiwan": ["TWN", "CHN"], "panama": ["PAN"]}

# Escenarios: (id, nombre, [(indicador, peso)]). Un indicador clave pesa 2.
ESCENARIOS = [
    ("escalada", "Escalada militar", [("violencia_sube", 2), ("interestatal", 2), ("militar", 1),
                                      ("aviso_sube", 1), ("exteriores_alto", 1), ("contagio", 1), ("ruta_cercana", 1)]),
    ("golpe", "Golpe o crisis de gobierno", [("corte_internet", 2), ("censura", 2), ("militar", 1),
                                             ("protestas_suben", 1), ("golpe_en_prensa", 2), ("aviso_sube", 1),
                                             ("moneda_cae", 1), ("eleccion_cercana", 1)]),
    ("disturbios", "Disturbios graves", [("protestas_suben", 2), ("disturbios", 2), ("censura", 1),
                                        ("corte_internet", 1), ("violencia_sube", 1), ("moneda_cae", 1),
                                        ("eleccion_cercana", 1)]),
    ("humanitaria", "Emergencia humanitaria", [("desastre_grave", 2), ("epidemia_grave", 2), ("crisis_humanitaria", 2),
                                               ("violencia_alta", 1), ("muertes_verificadas", 1), ("exteriores_alto", 1)]),
]
TEXTO_INDICADOR = {
    "violencia_sube": "La violencia política sube respecto a lo habitual",
    "violencia_alta": "Violencia política intensa",
    "interestatal": "Enfrentamientos entre países",
    "militar": "Hechos con ejército o grupos armados",
    "aviso_sube": "Un gobierno ha subido su aviso de viaje",
    "exteriores_alto": "España desaconseja viajar al país",
    "contagio": "Países vecinos en alerta o empeorando",
    "ruta_cercana": "Ruta marítima cercana en riesgo",
    "corte_internet": "Corte de internet en el país",
    "censura": "Bloqueo de aplicaciones de mensajería",
    "protestas_suben": "Protestas al alza",
    "disturbios": "Protestas violentas o disturbios",
    "golpe_en_prensa": "La prensa habla de golpe de Estado",
    "desastre_grave": "Desastre con alerta oficial",
    "epidemia_grave": "Brote epidémico grave",
    "crisis_humanitaria": "Crisis humanitaria abierta",
    "muertes_verificadas": "Muertes en combate verificadas (UCDP)",
    "moneda_cae": "La moneda se hunde frente al dólar",
    "eleccion_cercana": "Elecciones o referéndum en las próximas semanas",
}


# Análisis estructurado: qué desmentiría cada escenario (abogado del diablo)
DESMENTIRIA = {
    "escalada": ["Que la violencia vuelva a su nivel habitual en 48-72 horas",
                 "Un alto el fuego o negociaciones que se mantengan",
                 "Que los hechos sean de un solo lugar y no se extiendan"],
    "golpe": ["Que internet y las aplicaciones vuelvan a funcionar con normalidad",
              "Que el gobierno siga funcionando y no haya movimientos del ejército en la capital",
              "Que la prensa deje de hablar de golpe sin confirmarlo ninguna fuente oficial"],
    "disturbios": ["Que las protestas bajen tras el fin de semana o una fecha señalada",
                   "Que el gobierno negocie o retire la medida que las provocó",
                   "Que no haya muertos ni toques de queda"],
    "humanitaria": ["Que se retire la alerta oficial del desastre o del brote",
                    "Que llegue ayuda humanitaria sin restricciones",
                    "Que no haya desplazamientos masivos"],
}
NOMBRE_INDICADOR_CONTRA = {
    "desescalada": "Señales de desescalada: negociaciones, alto el fuego o acceso humanitario",
    "tregua_en_prensa": "La prensa habla de tregua o negociaciones de paz",
}


def analisis(a3, p, ctx, escs):
    """Lo que haría un analista con los datos: señales en contra, hipótesis alternativas a la principal
    y qué la desmentiría. Ayuda a no quedarse solo con la explicación más alarmante."""
    g = ctx["gdelt"].get(a3, {})
    conflicto = g.get("conflicto", 0)
    contra = []
    if g.get("desescalada", 0) >= max(3, 0.2 * conflicto):
        contra.append(NOMBRE_INDICADOR_CONTRA["desescalada"])
    if a3 in ctx.get("tregua_en_prensa", ()):
        contra.append(NOMBRE_INDICADOR_CONTRA["tregua_en_prensa"])
    alternativas = []
    total = g.get("conflicto", 0) + g.get("protesta", 0)
    if total and g.get("estatal", 0) / max(total, 1) >= 0.3:
        alternativas.append("Una parte importante de la cobertura viene de medios estatales: puede ser propaganda")
    if p.get("confianza") == "baja" and p.get("nivel") != "verde":
        alternativas.append("Solo lo recoge la prensa: puede ser un pico mediático por un hecho aislado")
    regiones = g.get("regiones") or []
    if regiones and regiones[0][1] >= 0.7:
        alternativas.append(f"Casi todo pasa en {regiones[0][0]}: puede ser un problema local y no de todo el país")
    if g.get("interestatal", 0) and conflicto and g["interestatal"] / conflicto >= 0.5:
        alternativas.append("La mayoría son hechos entre países: puede ser un conflicto exterior y no una crisis interna")
    if p.get("crisis_abierta") and not p.get("escalada"):
        alternativas.append("Es una crisis prolongada: el nivel alto refleja que dura, no que empeore")
    principal = next((e for e in escs if e["riesgo"] != "bajo"), None)
    resultado = {}
    if contra:
        resultado["contra"] = contra
    if alternativas:
        resultado["alternativas"] = alternativas
    if principal:
        resultado["desmentiria"] = DESMENTIRIA.get(principal["id"], [])
        resultado["hipotesis"] = principal["nombre"]
    if regiones:
        resultado["donde"] = regiones
    if g.get("actores"):
        resultado["actores"] = g["actores"]
    return resultado


def calcular_vecinos(paises):
    """Países que comparten frontera, a partir de los vértices comunes de sus polígonos."""
    por_punto = {}
    for a3, _, anillos in paises.formas:
        for x, y in anillos[0]:
            por_punto.setdefault((round(x, 1), round(y, 1)), set()).add(a3)
    vecinos = {}
    for grupo in por_punto.values():
        for a in grupo:
            vecinos.setdefault(a, set()).update(grupo - {a})
    return {a: sorted(v) for a, v in vecinos.items()}


def intereses_espana(intereses, a3):
    tipos = (intereses or {}).get("tipos", {})
    return [(t["texto"], t["peso"]) for t in tipos.values() if a3 in t.get("paises", [])]


def pendiente(serie):
    """Pendiente (puntos por día) de los últimos 7 días por mínimos cuadrados."""
    s = serie[-7:]
    if len(s) < 3:
        return 0.0
    xs = range(len(s))
    mx, my = statistics.fmean(xs), statistics.fmean(s)
    den = sum((x - mx) ** 2 for x in xs)
    return sum((x - mx) * (y - my) for x, y in zip(xs, s)) / den if den else 0.0


def indicadores(a3, p, ctx):
    """Qué indicadores están encendidos para un país."""
    g = ctx["gdelt"].get(a3, {})
    # Umbrales relativos al volumen de noticias del país: en EE. UU. o India siempre hay de todo
    base = max(g.get("total", 0), 1)
    def notable(clave, minimo, cuota):
        return g.get(clave, 0) >= max(minimo, cuota * base)
    escalando = {a for a, q in ctx["paises"].items() if q.get("escalada") or q.get("nivel") == "rojo"}
    vecinos_mal = [v for v in ctx["vecinos"].get(a3, []) if v in escalando]
    rutas = [pid for pid, lista in PASOS_PAISES.items() if a3 in lista and ctx["pasos"].get(pid, "verde") != "verde"]
    return {
        "violencia_sube": p.get("conflicto", 0) >= 4 and (p.get("z", 0) >= 1 or p.get("dias_subiendo", 0) >= 2),
        "violencia_alta": p.get("conflicto", 0) >= 12,
        "interestatal": notable("interestatal", 5, 0.005),
        "militar": notable("militar", 5, 0.005),
        "aviso_sube": p.get("avisos", 0) > 0,
        "exteriores_alto": (ctx.get("exteriores", {}).get(a3) or {}).get("nivel", 0) >= 3,
        "contagio": len(vecinos_mal) >= 2,
        "ruta_cercana": bool(rutas),
        "corte_internet": p.get("internet", 0) > 0,
        "censura": p.get("censura", 0) > 0,
        "protestas_suben": p.get("protestas", 0) >= 4 and (p.get("z", 0) >= 1 or p.get("cuota_protestas", 0) >= 0.05),
        "disturbios": notable("disturbios", 3, 0.003),
        "golpe_en_prensa": a3 in ctx["golpe_en_prensa"],
        "desastre_grave": p.get("rango_desastre", 0) >= 1,
        "epidemia_grave": p.get("epidemias", 0) >= 8,
        "crisis_humanitaria": bool(p.get("crisis_abierta")),
        "muertes_verificadas": ctx["ucdp"].get(a3, 0) >= 25,
        "moneda_cae": ctx.get("divisas", {}).get(a3, 0) >= 0.08,
        "eleccion_cercana": bool(ctx.get("elecciones", {}).get(a3)),
    }, vecinos_mal


def desescalando(a3, ctx):
    g = ctx["gdelt"].get(a3, {})
    return g.get("desescalada", 0) >= max(3, 0.2 * g.get("conflicto", 0)) or a3 in ctx.get("tregua_en_prensa", ())


def escenarios(a3, p, ctx):
    encendidos, vecinos_mal = indicadores(a3, p, ctx)
    contra = desescalando(a3, ctx)
    resultado = []
    for ide, nombre, lista in ESCENARIOS:
        total = sum(w for _, w in lista)
        suma = sum(w for i, w in lista if encendidos[i])
        if suma == 0:
            continue
        # Alto: más de la mitad del peso; medio: al menos un indicador clave o dos indicadores
        fraccion = suma / total
        riesgo = 2 if fraccion > 0.5 else 1 if suma >= 2 else 0
        if contra and ide == "escalada" and riesgo:
            riesgo -= 1  # hay señales de desescalada: el analista rebaja un grado
        resultado.append({
            "id": ide, "nombre": nombre, "riesgo": RIESGO[riesgo], "estimativo": ESTIMATIVO[RIESGO[riesgo]],
        **({"rebajado": True} if contra and ide == "escalada" else {}),
            "indicadores": [{"texto": TEXTO_INDICADOR[i], "activo": encendidos[i]} for i, _ in lista],
        })
    # Con el mismo riesgo, primero el escenario que encaja con lo que más pesa en el país
    componentes = {"escalada": p.get("conflicto", 0), "disturbios": p.get("protestas", 0),
                   "humanitaria": p.get("desastres", 0) + p.get("epidemias", 0) + p.get("humanitaria", 0),
                   "golpe": p.get("internet", 0) + p.get("censura", 0)}
    preferido = max(componentes, key=componentes.get) if any(componentes.values()) else None
    resultado.sort(key=lambda e: ({"alto": 0, "medio": 1, "bajo": 2}[e["riesgo"]], e["id"] != preferido))
    return resultado, vecinos_mal


def pronostico(p, escs):
    """Riesgo de que el país empeore en los próximos 7 días, con lenguaje estimativo."""
    serie = p.get("serie") or [p.get("puntuacion", 0)]
    m = pendiente(serie)
    actual = p.get("puntuacion", 0)
    peor_escenario = max((2 if e["riesgo"] == "alto" else 1 if e["riesgo"] == "medio" else 0) for e in escs) if escs else 0
    # Aceleración de las últimas 12 h: da tendencia aunque aún no haya histórico de días
    acel = p.get("aceleracion") or 1
    acelera = acel >= 1.8 and actual >= 6
    if (m >= 1.5 and actual >= 8) or peor_escenario == 2 or (p.get("escalada") and m > 0.5) or (acelera and peor_escenario):
        riesgo = "alto"
    elif m >= 0.5 or peor_escenario == 1 or p.get("escalada") or acelera:
        riesgo = "medio"
    else:
        riesgo = "bajo"
    textos = {"alto": "Probable que empeore en los próximos 7 días",
              "medio": "Posible que empeore en los próximos 7 días",
              "bajo": "Poco probable que empeore en los próximos 7 días"}
    return {"riesgo": riesgo, "texto": textos[riesgo], "pendiente": round(m, 2),
            "proyeccion": round(max(0.0, actual + 7 * m), 1), "aceleracion": p.get("aceleracion")}


def fiabilidad(historico, dias=30):
    """Acierto de los pronósticos: de los países que se pronosticó que empeorarían,
    cuántos subieron de nivel o empeoraron en los 7 días siguientes."""
    fechas = sorted(historico)
    cuenta = {"alto": [0, 0], "medio": [0, 0], "bajo": [0, 0]}
    for i, d in enumerate(fechas):
        siguientes = fechas[i + 1:i + 8]
        if len(siguientes) < 7 or d < fechas[max(0, len(fechas) - dias - 7)]:
            continue
        for a3, v in historico[d].items():
            if len(v) < 4:
                continue
            riesgo = {2: "alto", 1: "medio", 0: "bajo"}[v[3]]
            empeoro = any(historico[s].get(a3, [0, 0, 0])[1] > v[1] or historico[s].get(a3, [0, 0, 0])[2]
                          for s in siguientes)
            cuenta[riesgo][1] += 1
            cuenta[riesgo][0] += int(empeoro)
    return {r: {"aciertos": a, "total": t} for r, (a, t) in cuenta.items() if t}


# Probabilidad de empeorar que el modelo asigna a cada grado de pronóstico (la misma que usa la
# simulación sin calibrar). Se compara con lo que pasó para medir el rendimiento.
PROB_PRONOSTICO = {2: 0.40, 1: 0.25, 0: 0.10}


def rendimiento(historico, reconstruidos=(), dias=60):
    """Puntuación de Brier de los pronósticos frente a dos referencias ingenuas:
    - la frecuencia media (decir siempre la misma probabilidad para todos),
    - la persistencia (la frecuencia observada según el nivel que tenía el país).
    Mejora > 0 significa que el modelo acierta más que la referencia."""
    fechas = sorted(historico)[-(dias + 7):]
    pares = []
    for i, d in enumerate(fechas):
        siguientes = fechas[i + 1:i + 8]
        if len(siguientes) < 7:
            continue
        for a3, v in historico[d].items():
            if len(v) < 4:
                continue
            empeoro = any(historico[s].get(a3, [0, 0, 0])[1] > v[1] or historico[s].get(a3, [0, 0, 0])[2]
                          for s in siguientes)
            pares.append((PROB_PRONOSTICO[v[3]], int(empeoro), v[1], v[3], d in reconstruidos))
    if len(pares) < 30:
        return {"muestras": len(pares)}
    n = len(pares)
    brier = sum((p - y) ** 2 for p, y, *_ in pares) / n
    media = sum(y for _, y, *_ in pares) / n
    brier_media = sum((media - y) ** 2 for _, y, *_ in pares) / n
    por_nivel = {}
    for _, y, nivel, *_ in pares:
        por_nivel.setdefault(nivel, []).append(y)
    tasa_nivel = {k: sum(v) / len(v) for k, v in por_nivel.items()}
    brier_nivel = sum((tasa_nivel[nivel] - y) ** 2 for _, y, nivel, *_ in pares) / n
    calibracion = []
    for grado, nombre in ((2, "alto"), (1, "medio"), (0, "bajo")):
        ys = [y for _, y, _, g, _ in pares if g == grado]
        if ys:
            calibracion.append({"riesgo": nombre, "dicho": PROB_PRONOSTICO[grado],
                                "observado": round(sum(ys) / len(ys), 3), "muestras": len(ys)})

    def mejora(ref):
        return round(1 - brier / ref, 3) if ref else None
    return {"muestras": n, "dias": len({d for d in fechas[:-7]}), "brier": round(brier, 4),
            "brier_media": round(brier_media, 4), "brier_persistencia": round(brier_nivel, 4),
            "mejora_media": mejora(brier_media), "mejora_persistencia": mejora(brier_nivel),
            "frecuencia": round(media, 3), "calibracion": calibracion,
            "reconstruidas": sum(1 for *_, r in pares if r)}


def informe(paises, pasos, intereses, calibrando):
    """Informe diario al estilo de un gabinete: conclusión principal, juicios clave y qué vigilar."""
    def peso_pais(a3):
        p = paises[a3]
        return RANGO[p["nivel"]] * 10 + (5 if p.get("escalada") else 0) + \
            {"alto": 4, "medio": 2}.get(p.get("pronostico", {}).get("riesgo"), 0) + p.get("puntuacion", 0) / 10

    orden = sorted(paises, key=peso_pais, reverse=True)
    juicios = []
    for a3 in orden:
        p = paises[a3]
        if len(juicios) >= 6:
            break
        if p["nivel"] == "verde" and p.get("pronostico", {}).get("riesgo") != "alto":
            continue
        principal = next((e for e in p.get("escenarios", []) if e["riesgo"] != "bajo"), None)
        juicios.append({
            "pais": a3, "nivel": p["nivel"], "confianza": p.get("confianza"),
            "pronostico": p.get("pronostico", {}).get("texto"),
            "escenario": principal and f'{principal["estimativo"]} {principal["nombre"].lower()}',
            "escenario_id": principal and principal["id"],
            "porque": [i["texto"] for i in (principal or {}).get("indicadores", []) if i["activo"]][:3] or p.get("motivos", [])[:3],
        })

    # Qué vigilar: escenarios a medio camino (algún indicador encendido, pero no la mayoría)
    vigilar = []
    for a3 in orden:
        for e in paises[a3].get("escenarios", []):
            if e["riesgo"] == "medio":
                apagados = [i["texto"] for i in e["indicadores"] if not i["activo"]][:2]
                vigilar.append({"pais": a3, "escenario": e["nombre"], "si_aparece": apagados})
        if len(vigilar) >= 6:
            break

    espana = []
    for a3 in orden:
        p = paises[a3]
        motivos = intereses_espana(intereses, a3)
        if not motivos or (p["nivel"] == "verde" and not p.get("escalada")):
            continue
        espana.append({"pais": a3, "nivel": p["nivel"], "por": [m for m, _ in motivos],
                       "peso": sum(w for _, w in motivos) * (RANGO[p["nivel"]] + 1)})
    espana.sort(key=lambda x: -x["peso"])
    for pid in ("gibraltar", "suez", "bab", "ormuz"):
        paso = next((x for x in pasos if x["id"] == pid), None)
        if paso and paso["nivel"] != "verde":
            espana.append({"paso": pid, "nombre": paso["nombre"], "nivel": paso["nivel"],
                           "por": ["Ruta clave para la energía y el comercio de España"]})

    regiones = []
    for region, lista in REGIONES.items():
        en = [a for a in lista if a in paises]
        rojos = [a for a in en if paises[a]["nivel"] == "rojo"]
        ambar = [a for a in en if paises[a]["nivel"] == "ambar"]
        empeoran = [a for a in en if paises[a].get("escalada")]
        if not (rojos or ambar or empeoran):
            continue
        tension = len(rojos) * 2 + len(ambar) + len(empeoran)
        regiones.append({"region": region, "rojo": rojos, "ambar": ambar, "empeoran": empeoran,
                         "tension": tension, "nivel": "rojo" if tension >= 6 else "ambar" if tension >= 3 else "verde"})
    regiones.sort(key=lambda r: -r["tension"])

    if juicios:
        primero = juicios[0]
        conclusion = {"pais": primero["pais"], "texto": primero["escenario"] or primero["pronostico"]}
    else:
        conclusion = {"pais": None, "texto": "Sin crisis nuevas destacables"}
    return {"conclusion": conclusion, "juicios": juicios, "vigilar": vigilar[:6], "espana": espana[:8],
            "regiones": regiones[:8], "calibrando": calibrando}


def enriquecer(alertas, ctx, intereses, historico):
    """Añade escenarios, pronóstico, región e interés para España a cada país, y el informe."""
    ctx = {**ctx, "paises": alertas["paises"]}
    for a3, p in alertas["paises"].items():
        escs, vecinos_mal = escenarios(a3, p, ctx)
        p["escenarios"] = escs
        p["pronostico"] = pronostico(p, escs)
        an = analisis(a3, p, ctx, escs)
        if an:
            p["analisis"] = an
        if desescalando(a3, ctx):
            p["desescalada"] = True
        p["region"] = REGION_DE.get(a3)
        if vecinos_mal:
            p["vecinos_mal"] = vecinos_mal
        espana = intereses_espana(intereses, a3)
        if espana:
            p["espana"] = [t for t, _ in espana]
        if ctx["ucdp"].get(a3):
            p["muertes_ucdp"] = ctx["ucdp"][a3]
        if ctx["exteriores"].get(a3):
            p["exteriores"] = ctx["exteriores"][a3]
        if ctx.get("elecciones", {}).get(a3):
            p["elecciones"] = [{k: x[k] for k in ("fecha", "nombre", "url")} for x in ctx["elecciones"][a3]]
        if ctx.get("divisas", {}).get(a3):
            p["divisa_caida"] = ctx["divisas"][a3]
    pasos = alertas.get("pasos", [])
    alertas["informe"] = informe(alertas["paises"], pasos, intereses, alertas.get("calibrando"))
    # Fechas clave: elecciones próximas, primero en los países que ya están en alerta o para vigilar
    rango = {"rojo": 0, "ambar": 1, "verde": 2}
    fechas = [{"pais": a3, **x} for a3, lista in ctx.get("elecciones", {}).items() for x in lista[:1]]
    fechas.sort(key=lambda x: (rango.get(alertas["paises"].get(x["pais"], {}).get("nivel"), 3), x["fecha"]))
    alertas["informe"]["fechas"] = sorted(fechas[:12], key=lambda x: x["fecha"])
    alertas["fiabilidad"] = fiabilidad(historico)
    alertas["rendimiento"] = rendimiento(historico, set(ctx.get("reconstruidos", ())))

    # Simulación de escenarios (sin validez oficial: ver scripts/simulacion.py)
    import simulacion
    nombres_pasos = {x["id"]: x["nombre"] for x in pasos}
    niveles_pasos = {x["id"]: x["nivel"] for x in pasos}
    alertas["simulacion"] = simulacion.simular(
        alertas, ctx["vecinos"], REGION_DE, alertas["fiabilidad"],
        lambda a3: [t for t, _ in intereses_espana(intereses, a3)],
        lambda a3: [nombres_pasos[pid] for pid, lista in PASOS_PAISES.items()
                    if a3 in lista and pid in nombres_pasos and (niveles_pasos[pid] != "verde"
                                                                 or alertas["paises"][a3]["nivel"] != "verde")])
    return alertas

