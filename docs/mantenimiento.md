# Guía para quien mantiene atalaya

**Español** · [English](mantenimiento.en.md)

Esta guía es para quien se hace cargo de atalaya: dónde está cada cosa, qué se toca para cada tarea, qué no hay que tocar y cómo comprobar que todo sigue bien. Las otras guías entran en detalle:

| Documento | Para qué |
|---|---|
| [Fuentes de datos](fuentes.md) | Qué da cada fuente, cómo se pide, cómo se filtra, qué falla y cómo comprobarla a mano |
| [Cálculos](calculos.md) | Todas las fórmulas, con ejemplos y las constantes que se pueden ajustar |
| [Avisos por Telegram](telegram.md) | Crear el bot y el canal, probarlo y resolver errores |
| [README](../README.md) | Visión general, arquitectura y decisiones de diseño |

---

## Índice

- [En cinco minutos](#en-cinco-minutos)
- [Mapa del repositorio](#mapa-del-repositorio)
- [Cómo se trabaja](#cómo-se-trabaja)
- [Tareas habituales](#tareas-habituales)
- [Mantenimiento periódico](#mantenimiento-periódico)
- [Qué hacer si…](#qué-hacer-si)
- [Lo que no hay que tocar sin pensarlo](#lo-que-no-hay-que-tocar-sin-pensarlo)
- [Lista antes de abrir una PR](#lista-antes-de-abrir-una-pr)
- [Glosario](#glosario)

---

## En cinco minutos

1. **No hay servidor.** Cada 30 minutos, una GitHub Action ([`actualizar.yml`](../.github/workflows/actualizar.yml)) descarga las fuentes, calcula y publica los resultados como JSON en la rama `datos`. La web ([`index.html`](../index.html), [`js/app.js`](../js/app.js)) es estática, está en GitHub Pages y lee esos JSON.
2. **Todo el cálculo está en `scripts/`**, en Python estándar. Solo los satélites de la NASA necesitan `h5py` y `numpy`, y van en un paso aparte.
3. **Nada se cambia en `main` directamente.** Se trabaja en `development` y se lleva a `main` con una PR. Al fusionar, la Action se ejecuta sola.
4. **Antes de fusionar algo que cambie el cálculo, se prueba con datos reales** sin tocar la web: *Run workflow* en `development` con *Publicar* desmarcado. Los resultados van a la rama `datos-prueba`.
5. **Si una fuente cae 3 horas seguidas**, se abre sola la issue *Fuentes de datos caídas*. Es lo primero que hay que mirar.

## Mapa del repositorio

| Si quieres cambiar… | Toca | Y además |
|---|---|---|
| Una fuente: URL, filtro o umbral | [`scripts/actualizar.py`](../scripts/actualizar.py), en la función de la fuente | Su prueba en [`tests/test_actualizar.py`](../tests/test_actualizar.py) y [fuentes.md](fuentes.md) |
| Cuánto suma cada cosa a la puntuación | `puntuar()` y los `peso` de cada fuente en `actualizar.py` | [calculos.md](calculos.md) y la tabla de puntuación del README |
| Cuándo un país pasa a *vigilar* o *alerta* | `calcular_alertas()` en `actualizar.py` | Ídem |
| Escenarios, indicadores, pronóstico e informe | [`scripts/inteligencia.py`](../scripts/inteligencia.py) | Las traducciones en [`js/i18n.js`](../js/i18n.js) |
| La simulación | [`scripts/simulacion.py`](../scripts/simulacion.py) | Ídem |
| El pronóstico aprendido | [`scripts/aprendizaje.py`](../scripts/aprendizaje.py) | [`tests/test_aprendizaje.py`](../tests/test_aprendizaje.py) |
| Luces nocturnas o lluvias | [`scripts/luces.py`](../scripts/luces.py), [`scripts/lluvias.py`](../scripts/lluvias.py) | [`tests/test_satelites.py`](../tests/test_satelites.py) |
| Avisos de Telegram o el RSS | [`scripts/telegram.py`](../scripts/telegram.py) | [`tests/test_telegram.py`](../tests/test_telegram.py) y [telegram.md](telegram.md) |
| La issue de fuentes caídas | [`scripts/salud.py`](../scripts/salud.py) | |
| La reconstrucción del pasado | [`scripts/retroceso.py`](../scripts/retroceso.py) | |
| Lo que se ve en la web | [`js/app.js`](../js/app.js), [`css/estilo.css`](../css/estilo.css), [`index.html`](../index.html) | Subir `?v=N` en `index.html` (ver abajo) |
| Un texto en inglés | [`js/i18n.js`](../js/i18n.js): `UI` (interfaz), `FRASES` (frases fijas de los scripts) y `PATRONES` (frases con números o nombres) | |
| Los intereses de España por país | [`data/intereses_espana.json`](../data/intereses_espana.json) | Es orientativo: revisar los despliegues de vez en cuando |
| Nombres o alias de un país | [`data/paises.json`](../data/paises.json) (`nombres` en inglés, `nombres_es` en español) | |
| La versión del modelo y los errores reconocidos | [`data/modelo.json`](../data/modelo.json) | Se muestra en *Cómo se calcula* |
| Cuándo y cómo corre todo | [`.github/workflows/actualizar.yml`](../.github/workflows/actualizar.yml) | |

Los datos que se generan en cada ejecución (alertas, eventos, histórico, estados de Telegram, luces…) **no están en `main`**: viven en la rama `datos`. La tabla de ficheros está en el [README](../README.md#datos).

## Cómo se trabaja

### Ramas y autoría

- `development` es la rama de trabajo; `main` es lo publicado. Los cambios van siempre por PR de `development` a `main`.
- `datos` y `datos-prueba` las escribe la Action: no se tocan a mano. Son ramas huérfanas de un solo commit que se sobrescriben en cada ejecución.
- Los commits los firma la persona que mantiene, con su nombre y su correo.

### Probar un cambio

```bash
python3 -m unittest discover -s tests    # pruebas (las de satélites se saltan sin h5py)
python3 -m http.server                   # la web en http://localhost:8000 con data/ local
```

Para ver la web con los datos reales sin descargar nada:

```bash
git fetch origin datos && git --work-tree=. checkout origin/datos -- data && git reset -q
```

Ojo: eso sobrescribe tu `data/` local con los ficheros publicados. No lo subas: `git status` no debe mostrar cambios en `data/` salvo los fijos (`paises.json`, `mundo.geojson`, `intereses_espana.json`, `modelo.json`).

Para probar con datos reales en GitHub sin tocar la web: **Actions → Actualizar datos → Run workflow**, rama `development`, *Publicar* desmarcado. Mira el registro y el resultado en la rama `datos-prueba`:

```bash
git fetch origin +refs/heads/datos-prueba:refs/remotes/origin/datos-prueba
git show origin/datos-prueba:data/alertas.json | python3 -m json.tool | less
```

### La caché de la web

Los navegadores guardan `app.js`, `i18n.js` y `estilo.css`. **Cada vez que se cambie uno de ellos, sube el número `?v=N`** en las tres líneas de [`index.html`](../index.html) que los cargan. Si no, mucha gente seguirá viendo la versión vieja.

## Tareas habituales

### Ajustar un umbral

1. Busca la constante en [calculos.md](calculos.md): ahí dice en qué fichero está y qué pasa si sube o baja.
2. Cámbiala, ajusta la prueba si comprobaba el valor anterior y pasa las pruebas.
3. Prueba con datos reales en `datos-prueba` y compara con `datos` cuántos países cambian de nivel.
4. Si cambia el comportamiento del modelo, añade una línea en `cambios` de [`data/modelo.json`](../data/modelo.json) y sube su `version`.

### Añadir una fuente

Sigue la lista de [fuentes.md](fuentes.md#añadir-una-fuente-nueva). Resumen: función con el contrato de fuentes, entrada en `FUENTES`, peso en `puntuar()` si suma, prueba con una respuesta de ejemplo, traducciones, README, [fuentes.md](fuentes.md) y `modelo.json`.

### Añadir o cambiar un texto

- Si es de la web, pásalo por `t("…")` en `app.js` y añade su traducción a `UI` en `i18n.js`.
- Si lo genera un script (motivos, escenarios, simulación…), añade la frase exacta a `FRASES` o, si lleva números o nombres, un patrón a `PATRONES` en `i18n.js`.

**Si no se traduce, sale en español en la web en inglés.** No rompe nada, pero queda mal.

### Reconstruir el pasado

Útil tras cambiar el modelo, para que el pronóstico aprendido y el rendimiento tengan datos: **Run workflow** con `retroceso_dias` = 30 a 90. Solo usa GDELT y no toca la línea base real (`historial.json`). Ver [calculos.md](calculos.md).

### Probar Telegram

**Actions → Probar Telegram → Run workflow** manda un mensaje de prueba y el resumen del día sin tocar nada más. Los errores y su solución están en [telegram.md](telegram.md#si-no-llega-nada).

## Mantenimiento periódico

| Cada | Qué | Cómo |
|---|---|---|
| Día | Mirar si hay issue *Fuentes de datos caídas* | Pestaña *Issues* del repositorio |
| Semana | Echar un vistazo al rendimiento del modelo | En la web: *Informe → Acierto y rendimiento* |
| 60 días | **Renovar `EARTHDATA_TOKEN`** (caduca) | [urs.earthdata.nasa.gov](https://urs.earthdata.nasa.gov/) → *Generate Token* → actualizar el secreto |
| Mes | Revisar `intereses_espana.json` (despliegues militares, comunidades) | Están marcados como orientativos |
| Mes | Revisar los avisos de dependencias de GitHub Actions (versiones de `actions/*`) | Registros de las ejecuciones |
| Cuando cambie una API | Ajustar la fuente y su prueba | [fuentes.md](fuentes.md) indica los fallos conocidos de cada una |

Los secretos y variables, y dónde se consigue cada uno, están en [fuentes.md](fuentes.md#secretos-y-variables).

## Qué hacer si…

| Pasa esto | Mira | Normalmente es |
|---|---|---|
| La web no se actualiza | La última ejecución de *Actualizar datos* | Una ejecución fallida: el registro dice en qué paso |
| Se abre la issue de fuentes caídas | La fuente que nombra, en [fuentes.md](fuentes.md) | La API cambió, o una clave caducó |
| Un país sale en alerta sin motivo aparente | Su ficha (*Por qué*) y `alertas.json` en `datos` | Ruido de prensa: ver *Otras explicaciones posibles* en la ficha |
| No llegan avisos de Telegram | El paso *Avisos por Telegram y RSS* | Ver [telegram.md](telegram.md#si-no-llega-nada) |
| *Satélites de la NASA* falla | Su paso en el registro | Token de Earthdata caducado (401) o una aplicación sin autorizar |
| El pronóstico aprendido dice «Todavía no se usa» | *Informe → Pronóstico aprendido* | Es lo esperado mientras no acierte más que la referencia |
| La web en inglés tiene frases en español | `js/i18n.js` | Falta la traducción de un texto nuevo |
| Se ven cosas viejas en la web | El `?v=N` de `index.html` | No se subió el número tras cambiar `app.js` o `estilo.css` |

## Lo que no hay que tocar sin pensarlo

- **El aviso de «sin validez oficial».** Está en la web, en cada mensaje de Telegram y en el RSS. atalaya hace estimaciones automáticas, no predicciones oficiales.
- **La neutralidad.** Los textos describen hechos y datos; no opinan sobre gobiernos ni partidos. Los avisos de viaje de EE. UU. solo refuerzan lo que miden las demás fuentes, nunca bastan por sí solos.
- **`historial.json`.** Es la línea base de «lo habitual» de cada país: borrarlo o mezclarlo con datos reconstruidos dispara falsas escaladas durante semanas.
- **La forma de los JSON publicados** (`alertas.json`, `eventos.json`). La web y Telegram dependen de ella: si cambia, hay que cambiar `app.js` y `telegram.py` a la vez.
- **Las claves.** Nunca en el código, en issues ni en chats: siempre como secretos de GitHub. Si una se ve, revócala y genera otra.
- **La atribución de Copernicus** en *Cómo se calcula*, que la exige la normativa europea.

## Lista antes de abrir una PR

- [ ] Pasan las pruebas (`python3 -m unittest discover -s tests`).
- [ ] Si cambia el cálculo, se ha probado en `datos-prueba` y se ha mirado el resultado.
- [ ] Si cambia `app.js`, `i18n.js` o `estilo.css`, se ha subido `?v=N` en `index.html`.
- [ ] Los textos nuevos tienen traducción en `i18n.js`.
- [ ] Están al día el README, [fuentes.md](fuentes.md) o [calculos.md](calculos.md), según lo que cambie.
- [ ] Si cambia el comportamiento del modelo, hay línea nueva en `data/modelo.json`.
- [ ] No hay claves ni datos personales en el cambio.

## Glosario

| Término | Significa |
|---|---|
| **Puntuación** | Suma de puntos de un país con lo ocurrido en las últimas 48 horas (30 días para epidemias) |
| **Línea base** | Lo habitual para un país: media y desviación de sus puntuaciones de los últimos 30 días |
| **z** | Cuántas desviaciones está hoy por encima de su línea base |
| **Escalada** | El país está peor de lo que es normal para él, o lleva 3 días subiendo |
| **Familia de fuente** | Prensa, oficial, técnica, sanitaria, humanitaria o académica: la confianza sube cuantas más coinciden |
| **Calibrando** | Los primeros 7 días sin histórico: no se calcula la escalada |
| **Indicador** | Señal observable que hace más probable un escenario (un corte de internet, un apagón…) |
| **Brier** | Error cuadrático medio entre la probabilidad dicha y lo que pasó: 0 es perfecto |
| **Empeorar de forma sostenida** | Subir de nivel, o empezar a empeorar, al menos dos días seguidos en los 7 siguientes |
| **Reconstruido** | Día pasado recalculado solo con GDELT para medir el modelo |
| `datos` / `datos-prueba` | Ramas donde la Action publica los resultados reales y los de prueba |
