/* atalaya: idiomas de la web (español e inglés).
 *
 * - t("texto en español {n}", { n: 3 }): textos de la interfaz. La clave es el propio texto en
 *   español, así el código se sigue leyendo en español y en español no hace falta diccionario.
 * - tb("texto"): textos que genera el análisis en Python (motivos, escenarios, simulación...).
 *   Se traducen con frases exactas y patrones; lo que no se conoce se queda en español.
 *
 * El idioma sale de ?lang=en, de la última elección guardada en este navegador o del idioma del
 * navegador, por ese orden.
 */
(() => {
  "use strict";

  const DISPONIBLES = ["es", "en"];
  function elegir() {
    const url = new URLSearchParams(location.search).get("lang");
    if (DISPONIBLES.includes(url)) return url;
    try {
      const guardado = localStorage.getItem("atalaya-idioma");
      if (DISPONIBLES.includes(guardado)) return guardado;
    } catch { /* sin almacenamiento */ }
    return (navigator.language || "es").toLowerCase().startsWith("en") ? "en" : "es";
  }
  const idioma = elegir();
  document.documentElement.lang = idioma;

  // ------------------------------------------------------- interfaz (EN)

  const UI = {
    // Niveles y confianza
    "Alerta": "Alert",
    "Vigilar": "Watch",
    "Actividad sin alerta": "Activity without alert",
    "Late si empeora": "Pulses if worsening",
    "Contagio simulado": "Simulated spillover",
    "Coinciden varios tipos de fuente independientes": "Several independent types of source agree",
    "Lo confirma una fuente oficial, técnica o sanitaria": "Confirmed by an official, technical or health source",
    "Solo lo recoge la prensa": "Reported only by the press",
    "Muy contrastado": "Well corroborated",
    "Contrastado": "Corroborated",
    "Solo prensa": "Press only",
    "precauciones normales": "exercise normal precautions",
    "más precaución": "exercise increased caution",
    "reconsiderar el viaje": "reconsider travel",
    "no viajar": "do not travel",
    "y": "and",
    "o": "or",

    // Cabecera, capas y controles
    "Cargando datos…": "Loading data…",
    "Buscar un país": "Search for a country",
    "Capas del mapa": "Map layers",
    "Conflictos": "Conflicts",
    "Protestas": "Protests",
    "Terremotos": "Earthquakes",
    "Desastres": "Disasters",
    "Epidemias": "Epidemics",
    "Internet y censura": "Internet and censorship",
    "Rutas marítimas": "Shipping routes",
    "Controles del mapa": "Map controls",
    "Ver otro día": "See another day",
    "Periodo": "Period",
    "Reproducir la semana": "Play the week",
    "Parar": "Stop",
    "7 días": "7 days",
    "Vista": "View",
    "Globo": "Globe",
    "Plano": "Flat",
    "Zoom": "Zoom",
    "Acercar": "Zoom in",
    "Alejar": "Zoom out",
    "Centrar": "Reset",
    "Ocultar panel": "Hide panel",
    "Mostrar panel": "Show panel",
    "Informe": "Report",
    "Simulación": "Simulation",
    "Países": "Countries",
    "Eventos": "Events",
    "Titulares": "Headlines",
    "Leyenda": "Legend",
    "Idioma": "Language",
    "Mapa del mundo con el nivel de alerta de cada país": "World map with the alert level of each country",
    "Pronósticos y simulaciones: estimaciones automáticas a partir de noticias, sin validez oficial.": "Forecasts and simulations: automatic estimates from the news, with no official validity.",
    "Cómo se calcula": "How it works",
    "Apoya atalaya": "Support atalaya",
    "Cerrar": "Close",

    // Mapa y fichas
    ", empeora": ", worsening",
    "Sin eventos recientes": "No recent events",
    "Simulación: {n} % de contagio en 7 días (sin validez oficial)": "Simulation: {n}% chance of spillover in 7 days (no official validity)",
    "hecho violento": "violent event",
    "hechos violentos": "violent events",
    "{n} en la zona en 24 horas": "{n} in the area in 24 hours",
    "noticia": "news story",
    "noticias": "news stories",
    "{n} de ataques o enfrentamientos": "{n} about attacks or clashes",
    "{n} de protestas": "{n} about protests",
    "Lo recoge la prensa: es una señal, no un hecho verificado.": "Reported by the press: it is a signal, not a verified fact.",
    "Ver {pais}": "See {pais}",
    "{n} en la zona en las últimas 24 horas.": "{n} in the area in the last 24 hours.",
    "Sin hechos violentos en la zona en las últimas 24 horas.": "No violent events in the area in the last 24 hours.",
    " Si sigue así, puede afectar al transporte marítimo y a los precios de la energía.": " If this continues, it may affect shipping and energy prices.",
    "Empeora": "Worsening",
    "Mejora": "Improving",
    "protesta": "protest",
    "protestas": "protests",
    "terremoto": "earthquake",
    "terremotos": "earthquakes",
    "brote epidémico": "disease outbreak",
    "corte de internet": "internet outage",
    "Sin eventos en las últimas 48 horas": "No events in the last 48 hours",

    // Informe
    "Todavía no hay datos. La primera actualización automática los descargará en unos minutos.": "No data yet. The first automatic update will download it in a few minutes.",
    "Conclusión principal": "Bottom line",
    "Sin crisis nuevas destacables": "No notable new crises",
    "país": "country",
    "países": "countries",
    "{rojo} {paises} en alerta y {ambar} para vigilar.": "{rojo} {paises} on alert and {ambar} to watch.",
    "sube": "rises",
    "suben": "rise",
    "baja": "drops",
    "bajan": "drop",
    "{n} de nivel": "{n} in level",
    " Desde ayer, {cambios}.": " Since yesterday, {cambios}.",
    " El histórico aún es corto: la comparación con lo habitual de cada país empieza a contar cuando hay una semana de datos.": " The history is still short: comparison with each country's usual level starts to count once there is a week of data.",
    "Mis países": "My countries",
    "Juicios clave": "Key judgements",
    "Qué vigilar en las próximas 72 horas": "What to watch in the next 72 hours",
    "Subiría si aparece: {x}.": "Would rise if this appears: {x}.",
    "Interés para España": "Relevance for Spain",
    "Regiones con más tensión": "Regions with most tension",
    "en alerta: {x}": "on alert: {x}",
    "para vigilar: {x}": "to watch: {x}",
    "empeoran: {x}": "worsening: {x}",
    "Fechas clave": "Key dates",
    "Elecciones y referendos en las próximas semanas, según Wikidata. Son fechas con más riesgo de protestas, cortes de internet o crisis de gobierno.": "Elections and referendums in the coming weeks, according to Wikidata. These dates carry a higher risk of protests, internet shutdowns or government crises.",
    "Rutas marítimas estratégicas": "Strategic shipping routes",
    "hecho": "event",
    "hechos": "events",
    "Sin hechos": "No events",
    "Acierto de los pronósticos": "Forecast accuracy",
    "pronóstico": "forecast",
    "pronósticos": "forecasts",
    "De {n} de empeoramiento probable en los últimos 30 días, se cumplieron {a} ({p} %).": "Of {n} of likely worsening in the last 30 days, {a} came true ({p}%).",
    " De los poco probables, empeoró el {p} %.": " Of the unlikely ones, {p}% worsened.",
    "Se medirá cuando haya más de una semana de histórico: cada pronóstico se compara con lo que pasó en los 7 días siguientes.": "It will be measured once there is more than a week of history: each forecast is compared with what happened in the following 7 days.",
    "acierta un {p} más": "is {p} more accurate",
    "acierta un {p} menos": "is {p} less accurate",
    "acierta lo mismo": "is just as accurate",
    "día": "day",
    "días": "days",
    "Rendimiento del modelo": "Model performance",
    "({n} en {d}{r}).": "({n} over {d}{r}).",
    ", {n} de días reconstruidos con GDELT": ", {n} from days reconstructed with GDELT",
    "Comparado con decir siempre la misma probabilidad, {a}; comparado con fiarse solo del nivel actual de cada país, {b}.": "Compared with always giving the same probability, it {a}; compared with relying only on each country's current level, it {b}.",
    "Puntuación de Brier {n} (0 es perfecto).": "Brier score {n} (0 is perfect).",
    "Pronóstico": "Forecast",
    "Probabilidad que da": "Probability given",
    "Empeoró de verdad": "Actually worsened",
    "Casos": "Cases",
    "Probable": "Likely",
    "Posible": "Possible",
    "Poco probable": "Unlikely",
    "Estado de las fuentes": "Source status",
    "al día": "up to date",
    "sin respuesta": "not responding",
    ", datos de {t}": ", data from {t}",

    // Simulación
    "Esto es una simulación.": "This is a simulation.",
    "Simulación automática basada en noticias y datos públicos. No tiene ninguna validez oficial.": "Automatic simulation based on news and public data. It has no official validity whatsoever.",
    "No hay crisis con datos suficientes para simular ahora mismo.": "There are no crises with enough data to simulate right now.",
    "crisis abierta": "open crisis",
    "crisis abiertas": "open crises",
    "Qué podría pasar en los próximos {d} días en {n}. En el mapa, los países rayados son los que podrían contagiarse.": "What could happen in the next {d} days in {n}. On the map, hatched countries are those that could be affected by spillover.",
    "Más riesgo de escalada": "Highest risk of escalation",
    "Más margen para contenerse": "Most room for containment",
    "Por regiones: que al menos una crisis escale": "By region: at least one crisis escalates",
    " y {n} más": " and {n} more",
    "Escala": "Escalates",
    "Sigue igual": "Stays the same",
    "Se contiene": "Is contained",
    "Igual": "Same",
    "Las crisis más graves, en detalle": "The most serious crises, in detail",
    "Simulado": "Simulated",
    "Escenario principal: {x}.": "Main scenario: {x}.",
    "Por qué:": "Why:",
    "Si escala, podría extenderse a:": "If it escalates, it could spread to:",
    "Para España:": "For Spain:",
    "Señales de que escala:": "Signs of escalation:",
    "Señales de que se contiene:": "Signs of containment:",
    "El resto de crisis abiertas": "The other open crises",
    "Crisis prolongada, sin señales nuevas": "Protracted crisis, no new signals",
    "Sin escenario dominante": "No dominant scenario",
    "Cómo se simula": "How the simulation works",
    "SIM_METODO": "The probability that a crisis escalates starts at {alto}% if the forecast says it will probably worsen, {medio}% if possible and {bajo}% if unlikely. It rises with each indicator switched on, if the situation worsened over the last week or sped up in the last 12 hours, if neighbours are in crisis and if the country is already on alert; it drops if things slow down. The range in brackets is the margin of uncertainty: narrower the more independent sources agree.",
    "Estas probabilidades ya están ajustadas con el acierto real de los pronósticos anteriores.": "These probabilities are already adjusted with the real accuracy of earlier forecasts.",
    "Cuando haya suficientes pronósticos comprobados, las probabilidades se ajustarán solas con su acierto real.": "Once enough forecasts have been checked, the probabilities will adjust themselves to their real accuracy.",
    "En una semana, lo más frecuente es que una crisis siga como está: por eso «sigue igual» suele ser la rama más probable.": "Within a week, a crisis most often stays as it is: that is why “stays the same” is usually the most likely branch.",

    // Países, eventos, titulares
    "Todavía no hay datos.": "No data yet.",
    "Cambios en avisos de viaje esta semana": "Travel advisory changes this week",
    "Brotes epidémicos (OMS, 30 días)": "Disease outbreaks (WHO, 30 days)",
    "Crisis humanitarias abiertas": "Open humanitarian crises",
    "Monedas que se hunden frente al dólar (7 días)": "Currencies plunging against the dollar (7 days)",
    "Cortes de internet grandes en 24 horas": "Major internet outages in 24 hours",
    "Más noticias de ataques o enfrentamientos": "Most reported attacks or clashes",
    "Más noticias de protestas": "Most reported protests",
    "Terremotos y desastres de los últimos 7 días": "Earthquakes and disasters in the last 7 days",
    "No hay eventos en las capas activas.": "There are no events in the active layers.",
    "Noticias en español de las últimas 24 horas sobre ataques, ofensivas, evacuaciones y terremotos.": "Spanish-language news from the last 24 hours about attacks, offensives, evacuations and earthquakes (headlines are shown in Spanish).",
    "No hay titulares disponibles ahora mismo.": "No headlines available right now.",

    // Ficha de país
    "Puntuación de los últimos {n} días": "Score over the last {n} days",
    "Evolución desde {d}": "Trend since {d}",
    "{d}: {n} puntos": "{d}: {n} points",
    "Evolución desde el {d}. Pincha un día para ver el mundo ese día.": "Trend since {d}. Click a day to see the world on that day.",
    "{n} por hechos violentos": "{n} from violent events",
    " (el {p} % de lo que se cuenta del país)": " ({p}% of what is reported about the country)",
    "{n} por protestas": "{n} from protests",
    "{n} por terremotos y desastres": "{n} from earthquakes and disasters",
    "{n} por brotes epidémicos": "{n} from disease outbreaks",
    "{n} por cortes de internet": "{n} from internet outages",
    "{n} por subir el aviso de viaje": "{n} from a raised travel advisory",
    "{n} por crisis humanitaria": "{n} from a humanitarian crisis",
    "{n} por la caída de su moneda": "{n} from the fall of its currency",
    "La puntuación de hoy suma {x}.": "Today's score adds up {x}.",
    "La puntuación de ese día suma {x}.": "That day's score adds up {x}.",
    " Está por encima de lo habitual para este país.": " It is above the usual level for this country.",
    " Está por debajo de lo habitual para este país.": " It is below the usual level for this country.",
    " Es parecida a lo habitual para este país.": " It is similar to the usual level for this country.",
    " EE. UU. tiene su aviso de viaje en nivel {n} de 4 ({t}).": " The US travel advisory is at level {n} of 4 ({t}).",
    "Volver": "Back",
    "Quitar de mis países": "Remove from my countries",
    "Seguir este país": "Follow this country",
    "★ Siguiendo": "★ Following",
    "☆ Seguir": "☆ Follow",
    "Ese día": "That day",
    "Hoy": "Today",
    "Media 30 días": "30-day average",
    "Tendencia": "Trend",
    "Sube": "Rising",
    "Baja": "Falling",
    "Estable": "Stable",
    "Pronóstico y escenarios": "Forecast and scenarios",
    "Estimación automática, sin validez oficial.": "Automatic estimate, no official validity.",
    " Tendencia de la última semana: {n} puntos al día.": " Trend over the last week: {n} points per day.",
    "Ningún escenario de crisis tiene indicadores suficientes ahora mismo.": "No crisis scenario has enough indicators right now.",
    "(rebajado un grado por señales de desescalada)": "(lowered one step because of de-escalation signals)",
    " (no se observa)": " (not observed)",
    "Vecinos en alerta o empeorando: {x}.": "Neighbours on alert or worsening: {x}.",
    "Señales tempranas": "Early signals",
    "Su moneda ha perdido un {p} % frente al dólar en 7 días.": "Its currency has lost {p}% against the dollar in 7 days.",
    " Las caídas bruscas suelen adelantarse a protestas o crisis de gobierno.": " Sharp falls often come before protests or government crises.",
    "Próximas citas electorales:": "Upcoming elections:",
    "Análisis": "Analysis",
    "Dónde se concentra la violencia:": "Where the violence is concentrated:",
    "Quién contra quién": "Who against whom",
    "(nombres tal como los codifica GDELT, en inglés)": "(names as coded by GDELT)",
    "{a} contra {b}": "{a} vs {b}",
    "Señales en contra:": "Signals against:",
    "Otras explicaciones posibles:": "Other possible explanations:",
    "Qué desmentiría «{x}»:": "What would disprove “{x}”:",
    "España": "Spain",
    "Exteriores: {x}.": "Spanish Foreign Ministry: {x}.",
    " Actualizado el {d}.": " Updated on {d}.",
    "Ver la ficha": "See the advice page",
    "muerte verificada": "verified death",
    "muertes verificadas": "verified deaths",
    "{n} en conflictos en los últimos 90 días (UCDP).": "{n} in conflicts in the last 90 days (UCDP).",
    "Análisis de expertos": "Expert analysis (in Spanish)",
    "En la prensa española": "In the Spanish press",
    "No hay eventos registrados en este país en los últimos 7 días.": "No events recorded in this country in the last 7 days.",

    // Carga e histórico
    "Actualizado {t}": "Updated {t}",
    ". Sin respuesta de {x}: se muestran sus últimos datos": ". No response from {x}: showing its latest data",
    "Esperando la primera actualización": "Waiting for the first update",
    "No se han podido cargar los datos. Vuelve a cargar la página en unos minutos.": "The data could not be loaded. Reload the page in a few minutes.",
    "{d}, foto de las {h}.": "{d}, snapshot taken at {h}.",
    "Volver a hoy": "Back to today",
    "No hay foto guardada del {d}.": "There is no saved snapshot for {d}.",
    "Versión del modelo: {v}": "Model version: {v}",
    "Errores reconocidos y corregidos": "Acknowledged and corrected errors",
  };

  // ------------------------------------------- textos del análisis (EN)

  // Frases exactas que genera scripts/*.py y data/*.json
  const FRASES = {
    // Motivos
    "Actividad muy alta": "Very high activity",
    "Actividad alta": "High activity",
    "Alerta oficial roja": "Official red alert",
    "Alerta oficial naranja": "Official orange alert",
    "Muy por encima de lo habitual": "Far above usual",
    "Por encima de lo habitual": "Above usual",
    "Crisis prolongada": "Protracted crisis",
    "EE. UU. desaconseja viajar": "US advises against travel",
    "Crisis humanitaria abierta": "Open humanitarian crisis",
    "Exteriores desaconseja viajar": "Spain advises against travel",

    // Escenarios e indicadores
    "Escalada militar": "Military escalation",
    "Golpe o crisis de gobierno": "Coup or government crisis",
    "Disturbios graves": "Serious unrest",
    "Emergencia humanitaria": "Humanitarian emergency",
    "Probable": "Likely",
    "Posible": "Possible",
    "Poco probable": "Unlikely",
    "La violencia política sube respecto a lo habitual": "Political violence is rising above usual",
    "Violencia política intensa": "Intense political violence",
    "Enfrentamientos entre países": "Clashes between countries",
    "Hechos con ejército o grupos armados": "Events involving the army or armed groups",
    "Un gobierno ha subido su aviso de viaje": "A government has raised its travel advisory",
    "España desaconseja viajar al país": "Spain advises against travel to the country",
    "Países vecinos en alerta o empeorando": "Neighbouring countries on alert or worsening",
    "Ruta marítima cercana en riesgo": "Nearby shipping route at risk",
    "Corte de internet en el país": "Internet outage in the country",
    "Bloqueo de aplicaciones de mensajería": "Messaging apps blocked",
    "Protestas al alza": "Protests on the rise",
    "Protestas violentas o disturbios": "Violent protests or riots",
    "La prensa habla de golpe de Estado": "The press is talking about a coup",
    "Desastre con alerta oficial": "Disaster with an official alert",
    "Brote epidémico grave": "Serious disease outbreak",
    "Crisis humanitaria abierta.": "Open humanitarian crisis.",
    "Muertes en combate verificadas (UCDP)": "Verified battle deaths (UCDP)",
    "La moneda se hunde frente al dólar": "The currency is plunging against the dollar",
    "Elecciones o referéndum en las próximas semanas": "Elections or a referendum in the coming weeks",

    // Pronóstico e informe
    "Probable que empeore en los próximos 7 días": "Likely to worsen in the next 7 days",
    "Posible que empeore en los próximos 7 días": "Could worsen in the next 7 days",
    "Poco probable que empeore en los próximos 7 días": "Unlikely to worsen in the next 7 days",
    "Sin crisis nuevas destacables": "No notable new crises",
    "Ruta clave para la energía y el comercio de España": "Key route for Spain's energy and trade",

    // Análisis estructurado
    "Señales de desescalada: negociaciones, alto el fuego o acceso humanitario": "De-escalation signals: negotiations, ceasefire or humanitarian access",
    "La prensa habla de tregua o negociaciones de paz": "The press is talking about a truce or peace talks",
    "Una parte importante de la cobertura viene de medios estatales: puede ser propaganda": "A large part of the coverage comes from state media: it may be propaganda",
    "Solo lo recoge la prensa: puede ser un pico mediático por un hecho aislado": "Only the press reports it: it may be a media spike over an isolated event",
    "La mayoría son hechos entre países: puede ser un conflicto exterior y no una crisis interna": "Most are events between countries: it may be an external conflict rather than an internal crisis",
    "Es una crisis prolongada: el nivel alto refleja que dura, no que empeore": "It is a protracted crisis: the high level reflects that it lasts, not that it is worsening",
    "Que la violencia vuelva a su nivel habitual en 48-72 horas": "Violence returning to its usual level within 48-72 hours",
    "Un alto el fuego o negociaciones que se mantengan": "A ceasefire or negotiations that hold",
    "Que los hechos sean de un solo lugar y no se extiendan": "Events staying in a single place and not spreading",
    "Que internet y las aplicaciones vuelvan a funcionar con normalidad": "Internet and apps working normally again",
    "Que el gobierno siga funcionando y no haya movimientos del ejército en la capital": "The government continuing to function, with no army movements in the capital",
    "Que la prensa deje de hablar de golpe sin confirmarlo ninguna fuente oficial": "The press dropping talk of a coup without any official source confirming it",
    "Que las protestas bajen tras el fin de semana o una fecha señalada": "Protests easing after the weekend or a key date",
    "Que el gobierno negocie o retire la medida que las provocó": "The government negotiating or withdrawing the measure that triggered them",
    "Que no haya muertos ni toques de queda": "No deaths and no curfews",
    "Que se retire la alerta oficial del desastre o del brote": "The official alert for the disaster or outbreak being lifted",
    "Que llegue ayuda humanitaria sin restricciones": "Humanitarian aid arriving without restrictions",
    "Que no haya desplazamientos masivos": "No mass displacement",

    // Simulación
    "Simulación automática basada en noticias y datos públicos, con reglas sencillas. No es una predicción oficial ni un análisis de inteligencia y no tiene ninguna validez oficial. Para decisiones reales, consulta fuentes oficiales como el Ministerio de Asuntos Exteriores.":
      "Automatic simulation based on news and public data, using simple rules. It is not an official forecast or an intelligence assessment, and it has no official validity whatsoever. For real decisions, consult official sources such as your country's foreign ministry.",
    "probable": "likely",
    "tan probable como no": "as likely as not",
    "posible": "possible",
    "poco probable": "unlikely",
    "Aumentan los ataques y los combates, con más desplazados dentro del país y hacia los vecinos.": "Attacks and fighting increase, with more people displaced inside the country and into neighbouring ones.",
    "Los enfrentamientos siguen con la intensidad actual.": "Clashes continue at the current intensity.",
    "Baja la intensidad: treguas locales, mediación o negociaciones.": "Intensity drops: local truces, mediation or negotiations.",
    "Ruptura institucional o estado de excepción: cortes de internet, toque de queda, cierre de fronteras y aeropuertos.": "Institutional breakdown or state of emergency: internet shutdowns, curfews, closed borders and airports.",
    "Tensión política sin ruptura, con protestas y bloqueos intermitentes.": "Political tension without a breakdown, with intermittent protests and blockades.",
    "La crisis se encauza por vías institucionales y la tensión baja.": "The crisis is channelled through institutions and tension eases.",
    "Las protestas se extienden a más ciudades, con más respuesta policial y posibles cortes de internet.": "Protests spread to more cities, with a tougher police response and possible internet shutdowns.",
    "Protestas intermitentes, sin cambios importantes.": "Intermittent protests, with no major changes.",
    "Las protestas remiten.": "Protests subside.",
    "Más personas afectadas y desplazadas; riesgo de brotes por falta de agua y saneamiento; petición de ayuda internacional.": "More people affected and displaced; risk of outbreaks due to lack of water and sanitation; calls for international aid.",
    "La emergencia continúa, con la ayuda en marcha.": "The emergency continues, with aid under way.",
    "La situación mejora y empieza la recuperación.": "The situation improves and recovery begins.",
    "La situación empeora respecto a la semana pasada.": "The situation worsens compared with last week.",
    "La situación se mantiene parecida.": "The situation stays much the same.",
    "La situación mejora.": "The situation improves.",
    "Posible presión sobre los precios del gas o del petróleo en España.": "Possible pressure on gas or oil prices in Spain.",
    "Posible aumento de salidas por las rutas migratorias hacia España.": "Possible increase in departures along migration routes to Spain.",
    "Más riesgo para los militares españoles desplegados en la zona.": "Higher risk for Spanish troops deployed in the area.",
    "Los españoles residentes podrían necesitar asistencia consular.": "Spanish residents could need consular assistance.",
    "Efectos directos en la frontera y en la relación con España.": "Direct effects on the border and on relations with Spain.",
    "Exteriores ya desaconseja viajar al país.": "Spain's Foreign Ministry already advises against travel to the country.",
    "Varios días seguidos de menos violencia": "Several days in a row of less violence",
    "Anuncio de tregua o de negociaciones": "A truce or negotiations announced",
    "Vuelve internet y se levantan los bloqueos": "Internet comes back and blocks are lifted",
    "Las instituciones siguen funcionando con normalidad": "Institutions keep functioning normally",
    "Bajan las protestas varios días seguidos": "Protests drop several days in a row",
    "Acuerdo entre el gobierno y los convocantes": "Agreement between the government and the organisers",
    "Baja el número de afectados": "The number of people affected drops",
    "Llega la ayuda internacional sin obstáculos": "International aid arrives unhindered",
    "La puntuación baja varios días seguidos": "The score drops several days in a row",
    "sube en la última semana": "rising over the last week",
    "baja en la última semana": "falling over the last week",
    "se frena en las últimas 12 horas": "slowing down in the last 12 hours",
    "ya está en alerta": "already on alert",
    "hay señales de desescalada (negociaciones, tregua o acceso humanitario)": "there are de-escalation signals (negotiations, truce or humanitarian access)",
    "crisis prolongada: difícil que se resuelva en una semana": "protracted crisis: unlikely to be resolved in a week",

    // Interés para España (data/intereses_espana.json)
    "Vecindad inmediata": "Immediate neighbourhood",
    "Rutas migratorias hacia España": "Migration routes to Spain",
    "Suministro de gas o petróleo": "Gas or oil supply",
    "Despliegues militares españoles (revisar)": "Spanish military deployments (to be reviewed)",
    "Gran comunidad española residente": "Large resident Spanish community",

    // Exteriores (niveles)
    "sin restricciones especiales": "no special restrictions",
    "precaución o zonas desaconsejadas": "caution or areas to avoid",
    "se desaconseja viajar salvo necesidad": "travel not advised unless necessary",
    "se desaconseja viajar bajo cualquier circunstancia": "travel not advised under any circumstances",
    "Exteriores actualiza sus recomendaciones de viaje": "Spain's Foreign Ministry updates its travel advice",

    // Avisos de EE. UU.
    "precauciones normales": "exercise normal precautions",
    "más precaución": "exercise increased caution",
    "reconsiderar el viaje": "reconsider travel",
    "no viajar": "do not travel",

    // Rutas marítimas
    "Estrecho de Ormuz": "Strait of Hormuz",
    "Bab el-Mandeb y mar Rojo sur": "Bab el-Mandeb and southern Red Sea",
    "Canal de Suez": "Suez Canal",
    "Bósforo": "Bosphorus",
    "Estrecho de Gibraltar": "Strait of Gibraltar",
    "Estrecho de Malaca": "Strait of Malacca",
    "Estrecho de Taiwán": "Taiwan Strait",
    "Canal de Panamá": "Panama Canal",
    "Salida del petróleo y el gas del golfo Pérsico": "Exit for Persian Gulf oil and gas",
    "Entrada al mar Rojo y al canal de Suez desde Asia": "Gateway to the Red Sea and the Suez Canal from Asia",
    "Ruta más corta entre Asia y Europa": "Shortest route between Asia and Europe",
    "Salida del mar Negro: cereal, petróleo y gas": "Exit from the Black Sea: grain, oil and gas",
    "Entrada al Mediterráneo, junto a España": "Gateway to the Mediterranean, next to Spain",
    "Principal ruta entre el Índico y el Pacífico": "Main route between the Indian Ocean and the Pacific",
    "Ruta de los semiconductores y del comercio de Asia oriental": "Route for semiconductors and East Asian trade",
    "Paso entre el Atlántico y el Pacífico": "Passage between the Atlantic and the Pacific",

    // Regiones
    "Magreb": "Maghreb",
    "Sahel": "Sahel",
    "África Occidental": "West Africa",
    "Cuerno de África y Sudán": "Horn of Africa and Sudan",
    "África Central y Grandes Lagos": "Central Africa and Great Lakes",
    "África Austral": "Southern Africa",
    "Oriente Próximo": "Middle East",
    "Golfo e Irán": "Gulf and Iran",
    "Mediterráneo oriental": "Eastern Mediterranean",
    "Europa del Este": "Eastern Europe",
    "Cáucaso": "Caucasus",
    "Balcanes": "Balkans",
    "Asia Central y Afganistán": "Central Asia and Afghanistan",
    "Asia Meridional": "South Asia",
    "Sudeste Asiático": "Southeast Asia",
    "Asia Oriental": "East Asia",
    "Centroamérica y Caribe": "Central America and Caribbean",
    "Sudamérica": "South America",

    // Títulos de eventos
    "Ataques o enfrentamientos": "Attacks or clashes",
    "Protestas": "Protests",
    "Corte de internet": "Internet outage",
    "Corte de internet ordenado por el gobierno": "Government-ordered internet shutdown",
    "Corte de internet en todo el país": "Nationwide internet outage",
    "Crisis humanitaria": "Humanitarian crisis",
    "Ciclón tropical": "Tropical cyclone",
    "Inundación": "Flood",
    "Erupción volcánica": "Volcanic eruption",
    "Sequía": "Drought",
    "Incendio forestal": "Wildfire",
    "Tsunami": "Tsunami",
    "Incendio": "Fire",
    "Tormenta severa": "Severe storm",
    "Volcán activo": "Active volcano",
    "Deslizamiento de tierra": "Landslide",
    "Polvo o calima": "Dust or haze",
    "Nevada": "Snowfall",
    "Fenómeno natural": "Natural event",
    "inundación": "flood",
    "incendio": "fire",
    "tormenta": "storm",
    "terremoto": "earthquake",
    "volcán": "volcano",
    "deslizamiento": "landslide",
    "crisis humanitaria": "humanitarian crisis",
    "accidente industrial": "industrial accident",
    "emergencia": "emergency",

    // Nombres de fuentes
    "Titulares": "Headlines",
    "Análisis": "Analysis",
    "Exteriores (España)": "Spanish Foreign Ministry",
    "Avisos de viaje EE. UU.": "US travel advisories",
    "OMS": "WHO",
    "Tipos de cambio": "Exchange rates",
    "Elecciones (Wikidata)": "Elections (Wikidata)",

    // data/modelo.json
    "Cada noticia cuenta una sola vez aunque GDELT saque varios hechos de ella": "Each news story counts only once, even when GDELT extracts several events from it",
    "Los medios estatales de países sin prensa libre cuentan la mitad": "State media from countries without a free press count half",
    "Señales de desescalada (negociaciones, alto el fuego, acceso humanitario) que rebajan el escenario de escalada": "De-escalation signals (negotiations, ceasefire, humanitarian access) that lower the escalation scenario",
    "Señales tempranas nuevas: caída brusca de la moneda y elecciones próximas": "New early signals: sharp currency falls and upcoming elections",
    "Análisis por país: dónde se concentra la violencia, quién contra quién, otras explicaciones y qué lo desmentiría": "Country analysis: where violence is concentrated, who against whom, other explanations and what would disprove it",
    "Medición del rendimiento con la puntuación de Brier frente a referencias ingenuas, y reconstrucción del pasado con GDELT": "Performance measured with the Brier score against naive baselines, and reconstruction of the past with GDELT",
    "Avisos por Telegram y feed RSS": "Telegram alerts and RSS feed",
    "Simulación con márgenes de incertidumbre, calibración con lo observado, contagio y correlación regional": "Simulation with uncertainty margins, calibration against observed outcomes, spillover and regional correlation",
    "Escenarios con indicadores, pronóstico a 7 días con lenguaje estimativo e informe diario": "Scenarios with indicators, 7-day forecast in estimative language and daily report",
    "Fuentes nuevas: Exteriores, OONI, Copernicus, EMSC, IGN, UCDP, análisis de Elcano, IEEE y CIDOB": "New sources: Spanish Foreign Ministry, OONI, Copernicus, EMSC, IGN, UCDP, analysis from Elcano, IEEE and CIDOB",
    "Modelo de tres ejes: gravedad, escalada respecto a lo habitual y confianza según tipos de fuente": "Three-axis model: severity, escalation compared with usual, and confidence by type of source",
    "Primera versión del mapa": "First version of the map",
    "Ciudades como Nueva York o Washington salían en alerta por crónica de sucesos y noticias de política interior. Corregido: solo cuenta la violencia política y el hecho principal de cada noticia.":
      "Cities such as New York or Washington showed up on alert because of crime reports and domestic political news. Fixed: only political violence and the main event of each story count.",
    "Algunas recomendaciones de Exteriores se leían con un nivel equivocado (por ejemplo, «salvo por motivos imprescindibles»). Corregido: se analizan frase a frase.":
      "Some Spanish Foreign Ministry advice was read at the wrong level (for example, “except for essential reasons”). Fixed: it is now analysed sentence by sentence.",
    "Un bloqueo crónico de una sola aplicación marcaba censura permanente. Corregido: hacen falta al menos dos aplicaciones.":
      "A chronic block of a single app flagged permanent censorship. Fixed: at least two apps are now required.",
    "La misma noticia podía contar varias veces e inflar un país. Corregido: se cuenta una vez por noticia.":
      "The same story could count several times and inflate a country. Fixed: it counts once per story.",
  };

  // Frases con partes variables (números, nombres)
  const PATRONES = [
    [/^(\d+) días seguidos subiendo$/, (m) => `${m[1]} days in a row rising`],
    [/^([\d.,]+) muertes verificadas en 90 días \(UCDP\)$/, (m) => `${m[1]} verified deaths in 90 days (UCDP)`],
    [/^(Probable|Posible|Poco probable) (.+)$/i, (m) => `${tb(mayus(m[1]))} ${tb(mayus(m[2])).toLowerCase()}`],
    [/^pronóstico: (probable|posible|poco probable) que empeore$/, (m) => `forecast: ${tb(m[1])} to worsen`.replace("possible to worsen", "could worsen")],
    [/^(\d+) indicador(?:es)? encendidos?$/, (m) => `${m[1]} ${m[1] === "1" ? "indicator" : "indicators"} switched on`],
    [/^se acelera en las últimas 12 horas \(×([\d.]+)\)$/, (m) => `speeding up in the last 12 hours (×${m[1]})`],
    [/^(\d+) vecinos? en crisis$/, (m) => `${m[1]} ${m[1] === "1" ? "neighbour" : "neighbours"} in crisis`],
    [/^Posibles desvíos en (.+): fletes más caros y retrasos en el comercio\.$/, (m) => `Possible diversions at the ${tb(m[1])}: more expensive freight and trade delays.`.replace("the Bosphorus", "the Bosphorus")],
    [/^Casi todo pasa en (.+): puede ser un problema local y no de todo el país$/, (m) => `Almost everything happens in ${m[1]}: it may be a local problem rather than a nationwide one`],
    [/^Terremoto de magnitud ([\d.]+)$/, (m) => `Magnitude ${m[1]} earthquake`],
    [/^Ciclón tropical (.+)$/, (m) => `Tropical cyclone ${m[1]}`],
    [/^EE\. UU\. (sube|baja) su aviso de viaje a nivel (\d) \((.+)\)$/, (m) => `US ${m[1] === "sube" ? "raises" : "lowers"} its travel advisory to level ${m[2]} (${tb(m[3])})`],
    [/^Brote: (.+)$/, (m) => `Outbreak: ${m[1]}`],
    [/^(Nuevo bloqueo|Bloqueo habitual) de (.+)$/, (m) => `${m[1] === "Nuevo bloqueo" ? "New block" : "Ongoing block"} of ${m[2].replace(/ y /g, " and ")}`],
    [/^La UE activa Copernicus: (.+)$/, (m) => `EU activates Copernicus: ${tb(m[1])}`],
    [/^Exteriores eleva su recomendación: (.+)$/, (m) => `Spain's Foreign Ministry raises its advice: ${tb(m[1])}`],
    [/^El ([A-Z]{3}) pierde un (\d+) % frente al dólar en 7 días$/, (m) => `The ${m[1]} loses ${m[2]}% against the dollar in 7 days`],
  ];

  function mayus(t) { return t ? t.charAt(0).toUpperCase() + t.slice(1) : t; }
  const FRASES_MIN = new Map(Object.entries(FRASES).map(([k, v]) => [k.toLowerCase(), v]));

  // Traduce un texto del análisis. Lo desconocido se devuelve tal cual (en español).
  function tb(texto) {
    if (idioma === "es" || texto == null || texto === "") return texto;
    const s = String(texto);
    const limpio = s.trim();
    if (FRASES[limpio] !== undefined) return FRASES[limpio];
    const min = FRASES_MIN.get(limpio.toLowerCase());
    if (min !== undefined) {
      // Respeta si el original venía en minúscula ("escalada militar")
      return limpio.charAt(0) === limpio.charAt(0).toLowerCase() ? min.charAt(0).toLowerCase() + min.slice(1) : min;
    }
    for (const [re, fn] of PATRONES) {
      const m = limpio.match(re);
      if (m) return fn(m);
    }
    // Con punto final, o varias frases seguidas
    if (limpio.endsWith(".") && !limpio.endsWith("..")) {
      const sin = limpio.slice(0, -1);
      const tr = tb(sin);
      if (tr !== sin) return tr + ".";
    }
    if (limpio.includes(". ")) {
      const partes = limpio.split(/(?<=\.) /);
      const tr = partes.map((p) => tb(p));
      if (tr.some((x, i) => x !== partes[i])) return tr.join(" ");
    }
    return s;
  }

  function t(clave, vars) {
    let s = idioma === "en" && UI[clave] !== undefined ? UI[clave] : clave;
    if (vars) s = s.replace(/\{(\w+)\}/g, (_, k) => (vars[k] ?? ""));
    return s;
  }

  function cambiar(nuevo) {
    if (!DISPONIBLES.includes(nuevo) || nuevo === idioma) return;
    try { localStorage.setItem("atalaya-idioma", nuevo); } catch { /* sin almacenamiento */ }
    const url = new URL(location.href);
    url.searchParams.set("lang", nuevo);
    location.href = url.toString();
  }

  // Textos fijos del HTML: data-i18n traduce el texto; data-i18n-attr="placeholder,aria-label" los atributos
  function traducirHTML() {
    if (idioma === "es") return;
    document.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.textContent.trim()); });
    document.querySelectorAll("[data-i18n-attr]").forEach((el) => {
      for (const a of el.dataset.i18nAttr.split(",")) {
        const v = el.getAttribute(a.trim());
        if (v) el.setAttribute(a.trim(), t(v));
      }
    });
    document.title = "atalaya";
    const desc = document.querySelector('meta[name="description"]');
    if (desc) desc.content = "World situation viewer: conflicts, protests, disasters, epidemics and internet outages, with an alert level for each country.";
  }

  window.I18N = { idioma, locale: idioma === "en" ? "en-GB" : "es-ES", t, tb, cambiar, traducirHTML };
})();
