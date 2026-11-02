# atalaya

Visor de la situación mundial: mapa en tiempo real con conflictos, protestas, desastres, epidemias y cortes de internet, y un nivel de alerta por país que detecta cuándo algo se está calentando.

[![Apoya atalaya en GitHub Sponsors](https://img.shields.io/badge/Apoya_atalaya-GitHub_Sponsors-ea4aaa?logo=githubsponsors&logoColor=white)](https://github.com/sponsors/serbenda)

## Qué muestra

- **Globo o mapa plano**, con día y noche, que se puede girar, acercar y compartir (`#pais=SDN`).
- **Conflictos y protestas** recogidos por la prensa mundial en las últimas 24 horas.
- **Terremotos**, **desastres** con alerta oficial y **brotes epidémicos** de la OMS.
- **Cortes de internet** grandes en todo un país.
- **Rutas marítimas estratégicas** (Ormuz, Bab el-Mandeb, Suez, Gibraltar…) según la violencia en su zona.
- **Parte de situación**: qué empeora, qué cambia desde ayer y el estado de cada fuente.
- **Reproducción de la última semana** y titulares en español.
- **Histórico**: la foto del mundo de cualquier día pasado (*Ver otro día*) y la evolución completa de cada país. Se puede compartir un día concreto: `#dia=2026-10-28&pais=SDN`.

## Modelo de alerta

Como en los equipos de alerta temprana, se separan tres cosas:

- **Gravedad**: lo mal que está un país. Incluye las crisis prolongadas, que siguen en alerta aunque hoy no empeoren.
- **Escalada**: si está peor de lo que es normal para él (más de 1,5 desviaciones sobre su media de 30 días) o lleva tres días seguidos subiendo. En el mapa, esos países laten.
- **Confianza**: cuántos tipos de fuente independientes coinciden (prensa, oficial, técnica, sanitaria, humanitaria). Si solo lo recoge la prensa, la confianza es baja.

Cada país suma una puntuación con lo ocurrido en las últimas 48 horas (30 días para epidemias):

| Señal | Puntos |
|---|---|
| Violencia política (GDELT) | `3 × log2(1 + hechos)`, al 100 % cuando es al menos el 5 % de lo que se cuenta del país |
| Protestas (GDELT) | La mitad que la violencia, con la misma proporción |
| Terremotos (USGS) | `(magnitud − 4)²`, más un extra con alerta PAGER |
| Desastres (GDACS, NASA EONET) | 1, 6 o 15 según alerta verde, naranja o roja |
| Brotes (OMS) | 3, u 8 si es una enfermedad grave (ébola, Marburgo, cólera…) |
| Cortes de internet (IODA) | Hasta 12 según la gravedad; los cortes pequeños no cuentan |
| Avisos de viaje de EE. UU. | 4 por cada nivel que suben |
| Crisis humanitarias (ReliefWeb) | 6 si están en alerta (opcional) |

Para no confundir delincuencia con conflicto, de GDELT solo cuentan los hechos principales de cada noticia y la violencia en la que intervienen ejércitos, grupos armados, insurgentes, gobiernos o dos países distintos.

El nivel sale de la puntuación, de su comparación con lo habitual, de las alertas oficiales naranja o roja y de las crisis prolongadas. El nivel 4 de los avisos de EE. UU. solo refuerza lo que ya muestran los datos, porque también refleja la política exterior de ese país. Durante los primeros 7 días solo cuentan los umbrales absolutos.

Son señales tempranas, no predicciones.

## Cómo funciona

```
GitHub Action (cada 30 min)
  └─ scripts/actualizar.py  →  rama `datos`: eventos.json, alertas.json, historial.json, avisos.json
GitHub Pages (rama main)
  └─ index.html + js/app.js  →  lee esos JSON de la rama `datos` y pinta el mapa
```

- El navegador no llama a ninguna API: todo lo descarga la Action. El script solo usa la biblioteca estándar de Python.
- La rama `datos` solo guarda la última versión (un único commit que se reemplaza). En `main` solo entra código, por PR desde `development`.
- El histórico no se recorta nunca: `historico.json` guarda la puntuación y el nivel de cada país por día, y `archivo/AAAA-MM-DD.json` la foto de cada día (niveles, parte, rutas y los 300 eventos más relevantes). Ocupa del orden de 50 MB al año.
- Si una fuente falla, el mapa sigue con sus últimos datos buenos. Si lleva 3 horas fallando, la Action abre el issue **Fuentes de datos caídas**.
- Para probar cambios con datos reales sin tocar la web: Actions → *Actualizar datos* → *Run workflow* en `development` con *Publicar* desmarcado. Los datos quedan en la rama `datos-prueba`.

## Capa de inteligencia

Sobre los datos se hace el análisis que haría un gabinete de crisis (`scripts/inteligencia.py`):

- **Escenarios con indicadores**. Escalada militar, golpe o crisis de gobierno, disturbios graves y emergencia humanitaria. Cada escenario tiene indicadores observables (enfrentamientos entre países, corte de internet, bloqueo de WhatsApp, la prensa habla de golpe, Exteriores desaconseja viajar…). Según cuántos se encienden, el escenario es *probable*, *posible* o *poco probable*.
- **Pronóstico a 7 días** según la tendencia de la última semana y los escenarios, con el mismo lenguaje estimativo. Cada pronóstico se guarda en el histórico y se compara con lo que pasó en los 7 días siguientes: el informe muestra su porcentaje de acierto.
- **Contagio regional**: los vecinos en alerta o empeorando son un indicador más. Los vecinos se calculan con las fronteras de `mundo.geojson`.
- **Regiones** (Sahel, Magreb, Cuerno de África, Oriente Próximo…) con su nivel de tensión.
- **Interés para España**: vecindad, rutas migratorias, energía, despliegues militares y comunidades españolas, definidos en `data/intereses_espana.json`. Es una lista orientativa: revísala y ajústala.
- **Informe diario** en la pestaña *Informe*: conclusión principal, juicios clave con su confianza, qué vigilar en las próximas 72 horas, interés para España, regiones, rutas marítimas, acierto de los pronósticos y estado de las fuentes.

Son reglas transparentes, no un modelo entrenado: cada juicio muestra los indicadores que lo sostienen.

### Simulación de escenarios

La pestaña *Simulación* (`scripts/simulacion.py`) imagina qué podría pasar en los próximos 7 días en las crisis abiertas:

- Tres ramas por país (**se contiene**, **sigue igual**, **escala**) con una probabilidad aproximada en múltiplos del 5 %, que sale del pronóstico, los indicadores encendidos, la tendencia de la semana y la situación de los vecinos.
- **Contagio simulado** a los países vecinos, que aparecen rayados en el mapa.
- **Impacto para España** (energía, migración, despliegues, comunidad española, rutas marítimas) y las señales que confirmarían o desmentirían cada rama.

> **Sin validez oficial.** Los pronósticos y las simulaciones son estimaciones automáticas hechas con reglas sencillas a partir de noticias y datos públicos. No son predicciones oficiales ni análisis de inteligencia, pueden equivocarse y no sirven para tomar decisiones. La web lo indica en la propia pestaña, en cada pronóstico y en la leyenda.

## Fuentes opcionales

Se activan al crear estas variables o secretos en el repositorio (Settings → Secrets and variables → Actions):

| Nombre | Tipo | Fuente | Cómo conseguirlo |
|---|---|---|---|
| `UCDP_TOKEN` | Secreto | Muertes en conflictos verificadas (Universidad de Uppsala) | Email al responsable de la API, explicando el proyecto ([ucdp.uu.se/apidocs](https://ucdp.uu.se/apidocs/)) |
| `UCDP_VERSION` | Variable | Versión mensual de UCDP (por defecto `26.0.9`) | La última versión candidata de la misma página |
| `CLOUDFLARE_TOKEN` | Secreto | Cortes de internet de Cloudflare Radar, con su causa | Token de API de una cuenta de Cloudflare con permiso de lectura de Radar |
| `RELIEFWEB_APPNAME` | Variable | Crisis humanitarias de ReliefWeb (OCHA) | Nombre de aplicación aprobado en [apidoc.reliefweb.int](https://apidoc.reliefweb.int/) |

## Fuentes

| Fuente | Datos |
|---|---|
| [GDELT](https://www.gdeltproject.org/) | Hechos geolocalizados de la prensa mundial (ficheros cada 15 min) |
| [Exteriores](https://www.exteriores.gob.es/es/ServiciosAlCiudadano/Paginas/Recomendaciones-de-viaje.aspx) | Recomendaciones de viaje de España por país (se lee la web dos veces al día) |
| [Travel Advisories](https://travel.state.gov/content/travel/en/traveladvisories/traveladvisories.html) | Avisos de viaje del Departamento de Estado de EE. UU. |
| [USGS](https://earthquake.usgs.gov/), [EMSC](https://www.seismicportal.eu/), [IGN](https://www.ign.es/) | Terremotos: mundo, Euromediterráneo y España |
| [GDACS](https://www.gdacs.org/) | Alertas de desastres (ONU y Comisión Europea) |
| [Copernicus EMS](https://mapping.emergency.copernicus.eu/) | Activaciones de cartografía de emergencia de la UE |
| [NASA EONET](https://eonet.gsfc.nasa.gov/) | Fenómenos naturales activos |
| [OMS](https://www.who.int/emergencies/disease-outbreak-news) | Brotes epidémicos |
| [IODA](https://ioda.inetintel.cc.gatech.edu/) | Cortes de internet por país (Georgia Tech) |
| [OONI](https://explorer.ooni.org/) | Bloqueos de WhatsApp, Telegram, Signal y Messenger |
| [Google Noticias](https://news.google.com/), [El País](https://elpais.com/internacional/), EFE, RTVE | Titulares en español |
| Real Instituto Elcano, IEEE, CIDOB | Análisis de expertos por país (a través de Google Noticias) |
| [world.geo.json](https://github.com/johan/world.geo.json) | Fronteras de los países (dominio público) |
| UCDP, Cloudflare Radar, ReliefWeb | Opcionales, ver arriba |

## Probar en local

```bash
python3 scripts/actualizar.py             # descarga los datos en data/
python3 -m http.server                    # y abre http://localhost:8000
python3 -m unittest discover -s tests     # pruebas
```

En local la web lee de `data/`; publicada, de la rama `datos`.

## Apoya el proyecto

atalaya es un proyecto personal, gratuito y sin publicidad. Si te resulta útil, puedes apoyarlo en [GitHub Sponsors](https://github.com/sponsors/serbenda).
