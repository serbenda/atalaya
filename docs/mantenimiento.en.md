# Maintainer guide

[Español](mantenimiento.md) · **English**

This guide is for whoever takes over atalaya: where everything lives, what to touch for each task, what not to touch and how to check that everything still works. The other guides go into detail:

| Document | What for |
|---|---|
| [Data sources](fuentes.en.md) | What each source provides, how it is requested and filtered, what fails and how to check it by hand |
| [Calculations](calculos.en.md) | Every formula, with examples and the constants that can be tuned |
| [Telegram alerts](telegram.en.md) | Creating the bot and channel, testing it and fixing errors |
| [README](../README.en.md) | Overview, architecture and design decisions |

---

## Contents

- [In five minutes](#in-five-minutes)
- [Repository map](#repository-map)
- [How work is done](#how-work-is-done)
- [Common tasks](#common-tasks)
- [Periodic maintenance](#periodic-maintenance)
- [What to do if…](#what-to-do-if)
- [Things not to touch without thinking](#things-not-to-touch-without-thinking)
- [Checklist before opening a PR](#checklist-before-opening-a-pr)
- [Glossary](#glossary)

---

## In five minutes

1. **There is no server.** Every 30 minutes a GitHub Action ([`actualizar.yml`](../.github/workflows/actualizar.yml)) downloads the sources, computes and publishes the results as JSON on the `datos` branch. The website ([`index.html`](../index.html), [`js/app.js`](../js/app.js)) is static, lives on GitHub Pages and reads that JSON.
2. **All the computation is in `scripts/`**, in standard-library Python. Only the NASA satellites need `h5py` and `numpy`, and they run in a separate step.
3. **Nothing is changed on `main` directly.** Work happens on `development` and reaches `main` through a PR. Merging runs the Action automatically.
4. **Before merging anything that changes the computation, test it with real data** without touching the website: *Run workflow* on `development` with *Publicar* unchecked. Results go to the `datos-prueba` branch.
5. **If a source is down for 3 hours in a row**, the issue *Fuentes de datos caídas* opens by itself. It is the first thing to check.

## Repository map

| To change… | Touch | And also |
|---|---|---|
| A source: URL, filter or threshold | [`scripts/actualizar.py`](../scripts/actualizar.py), in the source's function | Its test in [`tests/test_actualizar.py`](../tests/test_actualizar.py) and [fuentes.en.md](fuentes.en.md) |
| How much each thing adds to the score | `puntuar()` and each source's `peso` in `actualizar.py` | [calculos.en.md](calculos.en.md) and the README scoring table |
| When a country goes to *watch* or *alert* | `calcular_alertas()` in `actualizar.py` | Same |
| Scenarios, indicators, forecast and report | [`scripts/inteligencia.py`](../scripts/inteligencia.py) | The translations in [`js/i18n.js`](../js/i18n.js) |
| The simulation | [`scripts/simulacion.py`](../scripts/simulacion.py) | Same |
| The learned forecast | [`scripts/aprendizaje.py`](../scripts/aprendizaje.py) | [`tests/test_aprendizaje.py`](../tests/test_aprendizaje.py) |
| Night lights or rainfall | [`scripts/luces.py`](../scripts/luces.py), [`scripts/lluvias.py`](../scripts/lluvias.py) | [`tests/test_satelites.py`](../tests/test_satelites.py) |
| Telegram alerts or the RSS feed | [`scripts/telegram.py`](../scripts/telegram.py) | [`tests/test_telegram.py`](../tests/test_telegram.py) and [telegram.en.md](telegram.en.md) |
| The failing-sources issue | [`scripts/salud.py`](../scripts/salud.py) | |
| Backtest reconstruction | [`scripts/retroceso.py`](../scripts/retroceso.py) | |
| What the website shows | [`js/app.js`](../js/app.js), [`css/estilo.css`](../css/estilo.css), [`index.html`](../index.html) | Bump `?v=N` in `index.html` (see below) |
| An English text | [`js/i18n.js`](../js/i18n.js): `UI` (interface), `FRASES` (fixed script phrases) and `PATRONES` (phrases with numbers or names) | |
| Spain's interests per country | [`data/intereses_espana.json`](../data/intereses_espana.json) | It is indicative: review the deployments from time to time |
| A country's names or aliases | [`data/paises.json`](../data/paises.json) (`nombres` in English, `nombres_es` in Spanish) | |
| Model version and acknowledged errors | [`data/modelo.json`](../data/modelo.json) | Shown under *How it is calculated* |
| When and how everything runs | [`.github/workflows/actualizar.yml`](../.github/workflows/actualizar.yml) | |

The data generated on each run (alerts, events, history, Telegram state, night lights…) **is not on `main`**: it lives on the `datos` branch. The file table is in the [README](../README.en.md#data).

## How work is done

### Branches and authorship

- `development` is the working branch; `main` is what is published. Changes always go through a PR from `development` to `main`.
- `datos` and `datos-prueba` are written by the Action: never by hand. They are single-commit orphan branches, overwritten on every run.
- Commits are signed by the maintainer, with their name and email.

### Testing a change

```bash
python3 -m unittest discover -s tests    # tests (satellite tests are skipped without h5py)
python3 -m http.server                   # the website at http://localhost:8000 with local data/
```

To see the website with the real data without downloading anything:

```bash
git fetch origin datos && git --work-tree=. checkout origin/datos -- data && git reset -q
```

Careful: that overwrites your local `data/` with the published files. Do not commit them: `git status` must show no changes in `data/` except the fixed files (`paises.json`, `mundo.geojson`, `intereses_espana.json`, `modelo.json`).

To test with real data on GitHub without touching the website: **Actions → Actualizar datos → Run workflow**, branch `development`, *Publicar* unchecked. Check the log and the result on the `datos-prueba` branch:

```bash
git fetch origin +refs/heads/datos-prueba:refs/remotes/origin/datos-prueba
git show origin/datos-prueba:data/alertas.json | python3 -m json.tool | less
```

### The website cache

Browsers cache `app.js`, `i18n.js` and `estilo.css`. **Every time one of them changes, bump the `?v=N` number** on the three lines of [`index.html`](../index.html) that load them. Otherwise many people will keep seeing the old version.

## Common tasks

### Tuning a threshold

1. Look up the constant in [calculos.en.md](calculos.en.md): it says which file it is in and what happens if it goes up or down.
2. Change it, adjust the test if it checked the old value, and run the tests.
3. Test with real data on `datos-prueba` and compare with `datos` how many countries change level.
4. If the model's behaviour changes, add a line to `cambios` in [`data/modelo.json`](../data/modelo.json) and bump its `version`.

### Adding a source

Follow the checklist in [fuentes.en.md](fuentes.en.md). Summary: a function following the source contract, an entry in `FUENTES`, its weight in `puntuar()` if it scores, a test with a sample response, translations, the README, [fuentes.en.md](fuentes.en.md) and `modelo.json`.

### Adding or changing a text

- If it is on the website, wrap it in `t("…")` in `app.js` and add its translation to `UI` in `i18n.js`.
- If a script generates it (reasons, scenarios, simulation…), add the exact phrase to `FRASES` or, if it has numbers or names, a pattern to `PATRONES` in `i18n.js`.

**Without a translation it appears in Spanish on the English website.** Nothing breaks, but it looks wrong.

### Reconstructing the past

Useful after changing the model, so the learned forecast and the performance measurement have data: **Run workflow** with `retroceso_dias` = 30 to 90. It only uses GDELT and never touches the real baseline (`historial.json`). See [calculos.en.md](calculos.en.md).

### Testing Telegram

**Actions → Probar Telegram → Run workflow** sends a test message and the daily summary without touching anything else. Errors and fixes are in [telegram.en.md](telegram.en.md#if-nothing-arrives).

## Periodic maintenance

| Every | What | How |
|---|---|---|
| Day | Check for a *Fuentes de datos caídas* issue | The repository's *Issues* tab |
| Week | Look at the model's performance | On the website: *Report → Accuracy and performance* |
| 60 days | **Renew `EARTHDATA_TOKEN`** (it expires) | [urs.earthdata.nasa.gov](https://urs.earthdata.nasa.gov/) → *Generate Token* → update the secret |
| Month | Review `intereses_espana.json` (military deployments, communities) | They are marked as indicative |
| Month | Review GitHub Actions deprecation warnings (`actions/*` versions) | Run logs |
| When an API changes | Adjust the source and its test | [fuentes.en.md](fuentes.en.md) lists each source's known failures |

Secrets and variables, and where to get each one, are in [fuentes.en.md](fuentes.en.md).

## What to do if…

| This happens | Check | It is usually |
|---|---|---|
| The website is not updating | The latest *Actualizar datos* run | A failed run: the log says which step |
| The failing-sources issue opens | The source it names, in [fuentes.en.md](fuentes.en.md) | The API changed, or a key expired |
| A country is on alert for no apparent reason | Its sheet (*Why*) and `alertas.json` on `datos` | Press noise: see *Other possible explanations* in the sheet |
| No Telegram alerts arrive | The *Avisos por Telegram y RSS* step | See [telegram.en.md](telegram.en.md#if-nothing-arrives) |
| *Satélites de la NASA* fails | Its step in the log | Expired Earthdata token (401) or an unauthorised application |
| The learned forecast says "Not in use yet" | *Report → Learned forecast* | Expected while it does not beat the baseline |
| The English website has Spanish phrases | `js/i18n.js` | A new text has no translation |
| The website shows old things | `?v=N` in `index.html` | The number was not bumped after changing `app.js` or `estilo.css` |

## Things not to touch without thinking

- **The "no official validity" notice.** It is on the website, in every Telegram message and in the RSS feed. atalaya makes automatic estimates, not official forecasts.
- **Neutrality.** Texts describe facts and data; they do not give opinions on governments or parties. US travel advisories only reinforce what the other sources measure and are never enough on their own.
- **`historial.json`.** It is each country's "normal" baseline: deleting it or mixing it with reconstructed data triggers false escalations for weeks.
- **The shape of the published JSON** (`alertas.json`, `eventos.json`). The website and Telegram depend on it: if it changes, `app.js` and `telegram.py` must change at the same time.
- **Keys.** Never in code, issues or chats: always as GitHub secrets. If one is exposed, revoke it and generate another.
- **The Copernicus attribution** under *How it is calculated*, required by EU rules.

## Checklist before opening a PR

- [ ] The tests pass (`python3 -m unittest discover -s tests`).
- [ ] If the computation changes, it has been tested on `datos-prueba` and the result checked.
- [ ] If `app.js`, `i18n.js` or `estilo.css` changes, `?v=N` has been bumped in `index.html`.
- [ ] New texts have a translation in `i18n.js`.
- [ ] The README, [fuentes.en.md](fuentes.en.md) or [calculos.en.md](calculos.en.md) are up to date, as relevant.
- [ ] If the model's behaviour changes, there is a new line in `data/modelo.json`.
- [ ] No keys or personal data in the change.

## Glossary

| Term | Meaning |
|---|---|
| **Score** | Sum of a country's points for what happened in the last 48 hours (30 days for epidemics) |
| **Baseline** | What is normal for a country: mean and deviation of its scores over the last 30 days |
| **z** | How many deviations today is above its baseline |
| **Escalation** | The country is worse than normal for it, or has been rising for 3 days |
| **Source family** | Press, official, technical, health, humanitarian or academic: confidence rises the more of them agree |
| **Calibrating** | The first 7 days without history: escalation is not computed |
| **Indicator** | An observable signal that makes a scenario more likely (an internet shutdown, a blackout…) |
| **Brier** | Mean squared error between the stated probability and what happened: 0 is perfect |
| **Sustained worsening** | Moving up a level, or starting to worsen, for at least two days in a row within the next 7 |
| **Reconstructed** | A past day recomputed with GDELT only to measure the model |
| `datos` / `datos-prueba` | Branches where the Action publishes the real and the test results |
