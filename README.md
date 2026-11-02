# atalaya

Visor de la situación mundial: mapa en tiempo real con conflictos, protestas, desastres, epidemias y cortes de internet, y un nivel de alerta por país que detecta cuándo algo se está calentando.

## Qué muestra

- **Globo o mapa plano**, con día y noche, que se puede girar, acercar y compartir (`#pais=SDN`).
- **Conflictos y protestas** recogidos por la prensa mundial en las últimas 24 horas.
- **Terremotos**, **desastres** con alerta oficial y **brotes epidémicos** de la OMS.
- **Cortes de internet** grandes en todo un país.
- **Rutas marítimas estratégicas** (Ormuz, Bab el-Mandeb, Suez, Gibraltar…) según la violencia en su zona.
- **Parte de situación**: qué empeora, qué cambia desde ayer y el estado de cada fuente.
- **Reproducción de la última semana** y titulares en español.

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
- Si una fuente falla, el mapa sigue con sus últimos datos buenos. Si lleva 3 horas fallando, la Action abre el issue **Fuentes de datos caídas**.
- Para probar cambios con datos reales sin tocar la web: Actions → *Actualizar datos* → *Run workflow* en `development` con *Publicar* desmarcado. Los datos quedan en la rama `datos-prueba`.

### ReliefWeb (opcional)

La API de ReliefWeb (OCHA) exige un nombre de aplicación aprobado. Se pide en [apidoc.reliefweb.int](https://apidoc.reliefweb.int/). Cuando lo tengas, créalo como variable del repositorio: Settings → Secrets and variables → Actions → Variables → `RELIEFWEB_APPNAME`.

## Fuentes

| Fuente | Datos |
|---|---|
| [GDELT](https://www.gdeltproject.org/) | Hechos geolocalizados de la prensa mundial (ficheros cada 15 min) |
| [Google Noticias](https://news.google.com/) | Titulares en español |
| [USGS](https://earthquake.usgs.gov/) | Terremotos |
| [GDACS](https://www.gdacs.org/) | Alertas de desastres (ONU y Comisión Europea) |
| [NASA EONET](https://eonet.gsfc.nasa.gov/) | Fenómenos naturales activos |
| [OMS](https://www.who.int/emergencies/disease-outbreak-news) | Brotes epidémicos |
| [IODA](https://ioda.inetintel.cc.gatech.edu/) | Cortes de internet por país (Georgia Tech) |
| [Travel Advisories](https://travel.state.gov/content/travel/en/traveladvisories/traveladvisories.html) | Avisos de viaje del Departamento de Estado de EE. UU. |
| [ReliefWeb](https://reliefweb.int/) | Crisis humanitarias (opcional) |
| [world.geo.json](https://github.com/johan/world.geo.json) | Fronteras de los países (dominio público) |

Las recomendaciones de viaje del Ministerio de Asuntos Exteriores de España no tienen API ni RSS.

## Probar en local

```bash
python3 scripts/actualizar.py             # descarga los datos en data/
python3 -m http.server                    # y abre http://localhost:8000
python3 -m unittest discover -s tests     # pruebas
```

En local la web lee de `data/`; publicada, de la rama `datos`.
