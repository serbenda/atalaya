# atalaya

Visor de la situación mundial: mapa en tiempo real con conflictos, noticias y catástrofes naturales, y un nivel de alerta por país que detecta cuándo algo se está calentando.

## Qué muestra

- **Conflictos y protestas**: lugares donde la prensa mundial recoge ataques, enfrentamientos o protestas en las últimas 24 horas.
- **Cortes de internet** que afectan a todo un país.
- **Cambios en los avisos de viaje** oficiales.
- **Terremotos** de magnitud 4,5 o más de los últimos 7 días.
- **Desastres naturales**: ciclones, inundaciones, volcanes, sequías e incendios.
- **Titulares** en español sobre conflictos.
- **Nivel de alerta por país**: alerta, vigilar o lo habitual, con la evolución de los últimos 30 días.

## Cómo funciona

```
GitHub Action (cada 30 min)
  └─ scripts/actualizar.py  →  rama `datos`: eventos.json, alertas.json, historial.json, avisos.json
GitHub Pages (rama main)
  └─ index.html + js/app.js  →  lee esos JSON de la rama `datos` y pinta el mapa
```

- El navegador no llama a ninguna API: todo lo descarga la Action, así no hay problemas de CORS, claves ni límites de peticiones. El script solo usa la biblioteca estándar de Python.
- Los datos viven en la rama `datos`, que solo guarda la última versión (un único commit que se reemplaza en cada ejecución). En `main` solo entra código, siempre por PR desde `development`.
- Si una fuente falla, el mapa sigue con sus últimos datos buenos. Si lleva 3 horas fallando, la Action abre (o actualiza) el issue **Fuentes de datos caídas** con el error.

### Nivel de alerta

Cada país suma una puntuación con lo ocurrido en las últimas 48 horas:

- Terremotos: `(magnitud − 4)²`, más un extra si USGS emite alerta PAGER amarilla, naranja o roja.
- Desastres de GDACS: 1 (verde), 6 (naranja) o 15 (rojo). Eventos de NASA EONET: entre 0,5 y 2 según el tipo.
- Conflictos: `3 × log2(1 + hechos violentos)`, multiplicado por la proporción de lo que se cuenta del país que es violencia (al 100 % a partir del 15 %). Así, que de EE. UU. se hable mucho no lo pone en alerta. Las protestas se calculan igual con la mitad de peso.
- Cortes de internet (IODA): según la gravedad del corte, hasta 15.
- Avisos de viaje de EE. UU.: 4 puntos por cada nivel que suben.

La puntuación se compara con la media del país en los últimos 30 días (`data/historial.json`). El país pasa a **vigilar** o **alerta** cuando sube claramente sobre lo normal para él, cuando lleva tres días seguidos subiendo, cuando supera un umbral absoluto o cuando un organismo oficial emite una alerta naranja o roja. Durante los primeros 7 días solo cuentan los umbrales absolutos.

Son señales tempranas, no predicciones: las noticias no son hechos verificados.

## Fuentes

| Fuente | Datos |
|---|---|
| [GDELT](https://www.gdeltproject.org/) | Eventos geolocalizados de la prensa mundial (ficheros cada 15 min) y titulares |
| [USGS](https://earthquake.usgs.gov/) | Terremotos |
| [GDACS](https://www.gdacs.org/) | Alertas de desastres (ONU y Comisión Europea) |
| [NASA EONET](https://eonet.gsfc.nasa.gov/) | Fenómenos naturales activos |
| [IODA](https://ioda.inetintel.cc.gatech.edu/) | Cortes de internet por país (Georgia Tech) |
| [Travel Advisories](https://travel.state.gov/content/travel/en/traveladvisories/traveladvisories.html) | Avisos de viaje del Departamento de Estado de EE. UU. |
| [world.geo.json](https://github.com/johan/world.geo.json) | Fronteras de los países (dominio público) |

Las recomendaciones de viaje del Ministerio de Asuntos Exteriores de España no tienen API ni RSS, por eso de momento se usan las de EE. UU.

## Probar en local

```bash
python3 scripts/actualizar.py             # descarga los datos en data/
python3 -m http.server                    # y abre http://localhost:8000
python3 -m unittest discover -s tests     # pruebas
```

En local la web lee de `data/`; publicada, de la rama `datos`.
