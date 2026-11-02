# atalaya

Visor de la situación mundial: mapa en tiempo real con conflictos, noticias y catástrofes naturales, y un nivel de alerta por país que detecta cuándo algo se está calentando.

## Qué muestra

- **Conflictos**: lugares donde la prensa mundial habla de ataques, bombardeos o enfrentamientos en las últimas 24 horas.
- **Terremotos** de magnitud 4,5 o más de los últimos 7 días.
- **Desastres naturales**: ciclones, inundaciones, volcanes, sequías e incendios.
- **Titulares** en español sobre conflictos.
- **Nivel de alerta por país**: alerta, vigilar o actividad normal.

## Cómo funciona

```
GitHub Action (cada 30 min)
  └─ scripts/actualizar.py  →  data/eventos.json, data/alertas.json, data/historial.json
GitHub Pages
  └─ index.html + js/app.js  →  lee esos JSON y pinta el mapa
```

El navegador no llama a ninguna API: todo lo descarga la Action, así no hay problemas de CORS, claves ni límites de peticiones. El script solo usa la biblioteca estándar de Python.

### Nivel de alerta

Cada país suma una puntuación con lo ocurrido en las últimas 48 horas:

- Terremotos: `(magnitud − 4)²`, más un extra si USGS emite alerta PAGER amarilla, naranja o roja.
- Desastres de GDACS: 1 (verde), 6 (naranja) o 15 (rojo). Eventos de NASA EONET: entre 0,5 y 2 según el tipo.
- Conflictos: `3 × log2(1 + menciones en GDELT)`.

La puntuación se compara con la media del país en los últimos 30 días (`data/historial.json`). El país pasa a **vigilar** o **alerta** cuando sube claramente sobre lo normal para él, cuando supera un umbral absoluto o cuando un organismo oficial emite una alerta naranja o roja. Durante los primeros 7 días solo cuentan los umbrales absolutos.

Son señales tempranas, no predicciones: las noticias no son hechos verificados.

## Fuentes

| Fuente | Datos |
|---|---|
| [GDELT](https://www.gdeltproject.org/) | Noticias geolocalizadas y titulares |
| [USGS](https://earthquake.usgs.gov/) | Terremotos |
| [GDACS](https://www.gdacs.org/) | Alertas de desastres (ONU y Comisión Europea) |
| [NASA EONET](https://eonet.gsfc.nasa.gov/) | Fenómenos naturales activos |
| [world.geo.json](https://github.com/johan/world.geo.json) | Fronteras de los países (dominio público) |

## Probar en local

```bash
python3 scripts/actualizar.py   # descarga los datos
python3 -m http.server          # y abre http://localhost:8000
```
