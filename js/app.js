/* atalaya: pinta el mapa a partir de los JSON que genera scripts/actualizar.py */
(() => {
  "use strict";

  // ------------------------------------------------------------ constantes

  // Idioma: ver js/i18n.js. t() traduce la interfaz y tb() los textos que genera el análisis
  const { t, tb, locale: LOCALE, idioma: IDIOMA } = window.I18N;
  const NIVELES = {
    rojo: { texto: t("Alerta"), orden: 0 },
    ambar: { texto: t("Vigilar"), orden: 1 },
    verde: { texto: t("Actividad sin alerta"), orden: 2 },
  };
  const CONFIANZA = {
    alta: t("Coinciden varios tipos de fuente independientes"),
    media: t("Lo confirma una fuente oficial, técnica o sanitaria"),
    baja: t("Solo lo recoge la prensa"),
  };
  const AVISOS = { 1: t("precauciones normales"), 2: t("más precaución"), 3: t("reconsiderar el viaje"), 4: t("no viajar") };
  // Capa del mapa en la que se pinta cada tipo de evento (los que no tienen capa solo salen en el panel)
  const CAPA = { conflicto: "conflicto", protesta: "protesta", terremoto: "terremoto", desastre: "desastre",
    epidemia: "epidemia", internet: "internet", censura: "internet" };
  const HORA = 3600 * 1000;
  const ROTACION_INICIAL = [-10, -25, 0];

  // En GitHub Pages los datos vienen de la rama `datos`; en local, de la carpeta data/
  const local = ["localhost", "127.0.0.1", ""].includes(location.hostname);
  const DATOS = local ? "data/" : document.querySelector('meta[name="atalaya-datos"]').content;
  const reducirMovimiento = matchMedia("(prefers-reduced-motion: reduce)").matches;

  const nombresRegion = new Intl.DisplayNames([IDIOMA], { type: "region" });
  const relativo = new Intl.RelativeTimeFormat(IDIOMA, { numeric: "auto" });
  const numero = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 1 });
  const diaMes = (d) => new Date(d + "T12:00:00Z").toLocaleDateString(LOCALE, { day: "numeric", month: "short" });
  const fechaCorta = new Intl.DateTimeFormat(LOCALE, { weekday: "long", day: "numeric", hour: "2-digit", minute: "2-digit" });

  const estado = {
    eventos: [], titulares: [], alertas: {}, pasos: [], parte: {}, fuentes: {}, calibrando: true, actualizado: null,
    paises: new Map(), capas: new Set(["conflicto", "protesta", "terremoto", "desastre", "epidemia", "internet", "pasos"]),
    elegido: null, modo: "globo", ventanaHoras: 168, reproduciendo: null, instante: null,
    dia: null, dias: [], historico: null, informe: {}, fiabilidad: {}, analisis: [], simulacion: {},
    rendimiento: {}, modelo: null, mios: leerMios(),
  };

  // "Mis países": lista de seguimiento guardada solo en este navegador
  function leerMios() {
    try { return new Set(JSON.parse(localStorage.getItem("atalaya-mios") || "[]")); } catch { return new Set(); }
  }
  function guardarMios() {
    try { localStorage.setItem("atalaya-mios", JSON.stringify([...estado.mios])); } catch { /* sin almacenamiento */ }
  }
  const fechaLarga = new Intl.DateTimeFormat(LOCALE, { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  const fechaDia = (d) => mayuscula(fechaLarga.format(new Date(`${d}T12:00:00Z`)));
  const hoy = () => new Date().toISOString().slice(0, 10);

  const $ = (sel) => document.querySelector(sel);
  const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const mayuscula = (t) => (t ? t.charAt(0).toUpperCase() + t.slice(1) : t);
  const plural = (n, s, p) => `${numero.format(n)} ${n === 1 ? t(s) : t(p)}`;
  const lista = (xs) => (xs.length > 1 ? `${xs.slice(0, -1).join(", ")} ${t("y")} ${xs.at(-1)}` : xs[0] || "");
  const pct = (x) => (IDIOMA === "en" ? `${x}%` : `${x} %`);

  function nombrePais(a3, respaldo) {
    const p = estado.paises.get(a3);
    if (p?.a2) {
      try { return nombresRegion.of(p.a2); } catch { /* código sin nombre en español */ }
    }
    return respaldo || p?.nombres?.[0] || a3;
  }

  const fechaHora = new Intl.DateTimeFormat(LOCALE, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  function haceCuanto(iso) {
    // Viendo un día pasado, "hace 14 horas" confunde: se da la fecha
    if (estado.dia) return fechaHora.format(new Date(iso));
    let v = (new Date(iso) - Date.now()) / 1000;
    for (const [n, u] of [[60, "second"], [60, "minute"], [24, "hour"], [7, "day"]]) {
      if (Math.abs(v) < n) return relativo.format(Math.round(v), u);
      v /= n;
    }
    return relativo.format(Math.round(v), "week");
  }

  async function json(url) {
    const r = await fetch(url, { cache: "no-cache" });
    if (!r.ok) throw new Error(`${url}: ${r.status}`);
    return r.json();
  }

  // ------------------------------------------------------------------ mapa

  const contenedor = $("#mapa");
  const svg = d3.select(contenedor).append("svg");
  const defs = svg.append("defs");
  // Luz del globo, halo de la atmósfera y brillo de los focos de violencia
  const luz = defs.append("radialGradient").attr("id", "luz-esfera").attr("cx", "38%").attr("cy", "32%").attr("r", "75%");
  luz.append("stop").attr("offset", "0%").attr("stop-color", "#2D5263");
  luz.append("stop").attr("offset", "100%").attr("stop-color", "#14303C");
  // Rayado para los países que la simulación marca como posible contagio
  const rayado = defs.append("pattern").attr("id", "rayado-simulado").attr("patternUnits", "userSpaceOnUse")
    .attr("width", 6).attr("height", 6).attr("patternTransform", "rotate(45)");
  rayado.append("rect").attr("width", 6).attr("height", 6).attr("fill", "#355564");
  rayado.append("rect").attr("width", 2.4).attr("height", 6).attr("fill", "#E6A03B");
  const halo = defs.append("radialGradient").attr("id", "halo");
  halo.append("stop").attr("offset", "86%").attr("stop-color", "#7FD3E0").attr("stop-opacity", 0.16);
  halo.append("stop").attr("offset", "100%").attr("stop-color", "#7FD3E0").attr("stop-opacity", 0);
  for (const [id, color] of [["brillo-conflicto", "#FF8A5B"], ["brillo-protesta", "#C7B8E6"]]) {
    const g = defs.append("radialGradient").attr("id", id);
    g.append("stop").attr("offset", "0%").attr("stop-color", color).attr("stop-opacity", 0.55);
    g.append("stop").attr("offset", "100%").attr("stop-color", color).attr("stop-opacity", 0);
  }

  const capaAtmosfera = svg.append("circle").attr("class", "atmosfera");
  const capaEsfera = svg.append("path").attr("class", "esfera");
  const capaReticula = svg.append("path").attr("class", "reticula");
  const capaPaises = svg.append("g");
  const capaNoche = svg.append("path").attr("class", "noche");
  const capaBrillos = svg.append("g");
  const capaMarcadores = svg.append("g");
  const capaOndas = svg.append("g");
  const capaPasos = svg.append("g");
  const capaEtiquetas = svg.append("g");

  let proyeccion, ruta, mundo = null;
  let alto = 0, escalaBase = 1, centroBase = [0, 0];
  let rotacion = [...ROTACION_INICIAL];
  let ultimoZoom = d3.zoomIdentity;
  let girando = null;
  let reanudar = null;
  // Giro del globo: activado por defecto; si se toca el mapa, se para y vuelve solo a los pocos segundos
  const ESPERA_GIRO = 6000;
  let giroActivo = (() => { try { return localStorage.getItem("atalaya-giro") !== "no"; } catch { return true; } })();

  function areaUtil() {
    const { width, height } = contenedor.getBoundingClientRect();
    const movil = width < 760;
    // Deja sitio al panel lateral en escritorio y al inferior en móvil
    const w = movil ? width : width - 416;
    const h = movil ? height * 0.56 : height;
    return { width, height, movil, x0: 16, y0: movil ? 110 : 120, x1: w - 16, y1: h - (movil ? 10 : 70) };
  }

  function configurarProyeccion() {
    const a = areaUtil();
    alto = a.height;
    svg.attr("viewBox", `0 0 ${a.width} ${a.height}`);
    const cx = (a.x0 + a.x1) / 2, cy = (a.y0 + a.y1) / 2;
    if (estado.modo === "globo") {
      proyeccion = d3.geoOrthographic().clipAngle(90).rotate(rotacion);
      escalaBase = Math.min(a.x1 - a.x0, a.y1 - a.y0) / 2;
      centroBase = [cx, cy];
    } else {
      proyeccion = d3.geoNaturalEarth1();
      proyeccion.fitExtent([[a.x0, a.y0], [a.x1, a.y1]], { type: "Sphere" });
      escalaBase = proyeccion.scale();
      centroBase = proyeccion.translate();
    }
    proyeccion.scale(escalaBase).translate(centroBase);
    ruta = d3.geoPath(proyeccion);
    svg.classed("plano", estado.modo === "plano");
  }

  function aplicarZoom(t) {
    if (estado.modo === "globo") {
      // Arrastrar gira el globo; la rueda acerca
      if (t.k === ultimoZoom.k) {
        const sensibilidad = 0.25 / t.k;
        rotacion = [rotacion[0] + (t.x - ultimoZoom.x) * sensibilidad,
          Math.max(-80, Math.min(80, rotacion[1] - (t.y - ultimoZoom.y) * sensibilidad)), 0];
      }
      proyeccion.rotate(rotacion).scale(escalaBase * t.k).translate(centroBase);
    } else {
      proyeccion.scale(escalaBase * t.k).translate([centroBase[0] * t.k + t.x, centroBase[1] * t.k + t.y]);
    }
    ultimoZoom = t;
    redibujar();
  }

  const zoom = d3.zoom().scaleExtent([1, 14])
    .on("start", (ev) => { if (ev.sourceEvent) { pararGiro(); ocultarFicha(); } })
    .on("end", (ev) => { if (ev.sourceEvent) reanudarLuego(); })
    .on("zoom", (ev) => aplicarZoom(ev.transform));
  svg.call(zoom).on("dblclick.zoom", null);

  function visible(lon, lat) {
    if (estado.modo !== "globo") return true;
    const r = proyeccion.rotate();
    return d3.geoDistance([lon, lat], [-r[0], -r[1]]) < Math.PI / 2 - 0.02;
  }

  // Zona de noche: un círculo de 90° centrado en el punto opuesto al sol
  function zonaNoche() {
    const ahora = new Date(estado.instante ?? Date.now());
    const dia = (ahora - Date.UTC(ahora.getUTCFullYear(), 0, 0)) / 864e5;
    const declinacion = -23.44 * Math.cos((2 * Math.PI / 365) * (dia + 10));
    const horas = ahora.getUTCHours() + ahora.getUTCMinutes() / 60;
    const lonSol = -15 * (horas - 12);
    return d3.geoCircle().center([lonSol + 180, -declinacion]).radius(90)();
  }

  function redibujar() {
    if (!mundo) return;
    const k = ultimoZoom.k;
    const [cx, cy] = proyeccion.translate();
    capaAtmosfera.attr("cx", cx).attr("cy", cy).attr("r", estado.modo === "globo" ? proyeccion.scale() * 1.08 : 0);
    capaEsfera.attr("d", ruta({ type: "Sphere" }));
    capaReticula.attr("d", ruta(d3.geoGraticule10()));
    capaPaises.selectAll("path").attr("d", ruta);
    capaNoche.attr("d", ruta(zonaNoche()));

    const posicion = (sel) => sel
      .attr("transform", (d) => {
        const p = proyeccion([d.lon, d.lat]);
        return p ? `translate(${p[0]},${p[1]})` : null;
      })
      .attr("display", (d) => (visible(d.lon, d.lat) ? null : "none"));
    posicion(capaMarcadores.selectAll(".marcador"));
    posicion(capaBrillos.selectAll(".brillo"));
    posicion(capaOndas.selectAll("g"));
    posicion(capaPasos.selectAll(".paso"));
    capaPasos.selectAll("text").attr("display", k >= 1.6 ? null : "none");

    capaEtiquetas.selectAll("text")
      .attr("transform", (d) => { const p = proyeccion(d.centro); return p ? `translate(${p[0]},${p[1]})` : null; })
      .attr("display", (d) => (visible(...d.centro) && (d.nivel === "rojo" ? k >= 1.4 : k >= 2.6) ? null : "none"));
  }

  function dibujarPaises() {
    capaPaises.selectAll("path").data(mundo.features, (f) => f.id).join("path")
      .attr("class", (f) => {
        const a = estado.alertas[f.id];
        const simulado = document.body.classList.contains("simulando") ? estado.simulacion?.contagio?.[f.id] : null;
        const caso = document.body.classList.contains("simulando") && estado.simulacion?.casos?.some((c) => c.pais === f.id);
        return ["pais", a?.nivel, a?.escalada && !reducirMovimiento ? "escalada" : "", f.id === estado.elegido ? "elegido" : "",
          simulado ? "contagio-simulado" : "", caso ? "caso-simulado" : ""].join(" ");
      })
      .on("click", (ev, f) => { ev.stopPropagation(); abrirPais(f.id, f.properties.name); })
      .on("mousemove", (ev, f) => {
        const a = estado.alertas[f.id];
        let texto = a ? `${NIVELES[a.nivel].texto}${a.escalada ? t(", empeora") : ""}${a.motivos?.length ? `<br>${esc(a.motivos.map(tb).join(". "))}` : ""}` : t("Sin eventos recientes");
        const sim = estado.simulacion?.contagio?.[f.id];
        if (sim && document.body.classList.contains("simulando")) texto += `<br>${t("Simulación: {n} % de contagio en 7 días (sin validez oficial)", { n: sim })}`;
        mostrarInfo(ev, `<strong>${esc(nombrePais(f.id, f.properties.name))}</strong><span>${texto}</span>`);
      })
      .on("mouseleave", ocultarInfo);

    const etiquetas = mundo.features
      .filter((f) => ["rojo", "ambar"].includes(estado.alertas[f.id]?.nivel))
      .map((f) => ({ id: f.id, nivel: estado.alertas[f.id].nivel, centro: d3.geoCentroid(f), nombre: nombrePais(f.id, f.properties.name) }));
    capaEtiquetas.selectAll("text").data(etiquetas, (d) => d.id).join("text")
      .attr("class", "etiqueta").text((d) => d.nombre);
    redibujar();
  }

  function enVentana(e) {
    const fin = estado.instante ?? Date.now();
    const t = new Date(e.fecha).getTime();
    // Las epidemias evolucionan despacio: se ven hasta 30 días
    const horas = e.tipo === "epidemia" ? 24 * 30 : estado.reproduciendo ? 24 : estado.ventanaHoras;
    return t <= fin + HORA && t >= fin - horas * HORA;
  }

  function radio(d) {
    let r;
    if (d.tipo === "terremoto") r = 2.5 + Math.max((d.magnitud || 4.5) - 4.5, 0) * 3.4;
    else if (d.tipo === "conflicto" || d.tipo === "protesta") r = Math.min(15, 2 + Math.sqrt(d.menciones || 1) * 0.55);
    else if (["internet", "epidemia", "censura"].includes(d.tipo)) r = 7;
    else r = d.nivel === "rojo" ? 8.5 : d.nivel === "ambar" ? 7 : 5;
    return r * Math.max(0.6, Math.min(1, alto / 900));
  }

  function forma(d) {
    const r = radio(d);
    if (d.tipo === "desastre") return `M0,${-r}L${r * 0.9},${r * 0.6}L${-r * 0.9},${r * 0.6}Z`;
    if (d.tipo === "protesta") { const l = r * 0.8; return `M${-l},${-l}H${l}V${l}H${-l}Z`; }
    if (["internet", "epidemia", "censura"].includes(d.tipo)) return `M0,${-r}L${r},0L0,${r}L${-r},0Z`;
    return `M${-r},0a${r},${r} 0 1,0 ${2 * r},0a${r},${r} 0 1,0 ${-2 * r},0`;
  }

  function dibujarEventos() {
    const visibles = estado.eventos.filter((e) => CAPA[e.tipo] && estado.capas.has(CAPA[e.tipo]) && e.lat != null && enVentana(e));
    visibles.sort((a, b) => radio(b) - radio(a)); // los grandes debajo

    const focos = visibles.filter((e) => (e.tipo === "conflicto" || e.tipo === "protesta") && e.menciones >= 8).slice(0, 160);
    capaBrillos.selectAll(".brillo").data(focos, (d) => d.id).join("circle")
      .attr("class", "brillo").attr("r", (d) => radio(d) * 3.4)
      .attr("fill", (d) => `url(#brillo-${d.tipo})`);

    capaMarcadores.selectAll(".marcador").data(visibles, (d) => d.id).join("path")
      .attr("class", (d) => `marcador ${d.tipo} ${["terremoto", "desastre"].includes(d.tipo) && d.nivel !== "verde" ? `${d.nivel}-oficial` : ""}`)
      .attr("d", forma)
      .on("mousemove", (ev, d) => mostrarInfo(ev, `<strong>${esc(tituloEvento(d))}</strong><span>${esc(detalleEvento(d))}</span>`))
      .on("mouseleave", ocultarInfo)
      .on("click", (ev, d) => { ev.stopPropagation(); abrirFicha(ev, d); });

    // Ondas: lo más reciente y relevante, sin saturar
    const fin = estado.instante ?? Date.now();
    const ondas = reducirMovimiento ? [] : visibles
      .filter((e) => fin - new Date(e.fecha) < 6 * HORA && (e.nivel !== "verde" || (e.magnitud || 0) >= 5.8))
      .slice(0, 14);
    capaOndas.selectAll("g").data(ondas, (d) => d.id).join((enter) => {
      const n = enter.append("g");
      n.append("circle");
      return n;
    }).select("circle").attr("class", (d) => `onda ${d.nivel}`).attr("r", (d) => radio(d));

    const pasos = estado.capas.has("pasos") ? estado.pasos : [];
    const p = capaPasos.selectAll(".paso").data(pasos, (d) => d.id).join((enter) => {
      const n = enter.append("g");
      n.append("path").attr("class", "rombo").attr("d", "M0,-6L6,0L0,6L-6,0Z");
      n.append("text").attr("x", 9).attr("dy", "0.35em");
      return n;
    });
    p.attr("class", (d) => `paso ${d.nivel}`)
      .on("mousemove", (ev, d) => mostrarInfo(ev, `<strong>${esc(tb(d.nombre))}</strong><span>${esc(tb(d.porque))}<br>${t("{n} en la zona en 24 horas", { n: plural(d.hechos, "hecho violento", "hechos violentos") })}</span>`))
      .on("mouseleave", ocultarInfo)
      .on("click", (ev, d) => { ev.stopPropagation(); abrirFichaPaso(ev, d); });
    p.select("text").text((d) => tb(d.nombre));
    redibujar();
  }

  function tituloEvento(e) {
    return e.tipo === "conflicto" || e.tipo === "protesta" ? e.lugar.split(",")[0] : tb(e.titulo);
  }

  function detalleEvento(e) {
    const partes = [];
    if (e.pais && !["aviso"].includes(e.tipo)) partes.push(nombrePais(e.pais));
    if (e.tipo === "conflicto") partes.push(t("{n} de ataques o enfrentamientos", { n: plural(e.menciones, "noticia", "noticias") }));
    else if (e.tipo === "protesta") partes.push(t("{n} de protestas", { n: plural(e.menciones, "noticia", "noticias") }));
    else if (e.lugar && !["internet", "aviso", "epidemia", "crisis"].includes(e.tipo)) partes.push(e.lugar);
    partes.push(`${tb(e.fuente)}, ${haceCuanto(e.fecha)}`);
    return partes.join(". ");
  }

  // ----------------------------------------------- ficha flotante y globo

  const info = $("#globo-info");
  function mostrarInfo(ev, html) {
    info.innerHTML = html;
    info.hidden = false;
    const caja = contenedor.getBoundingClientRect();
    info.style.left = `${Math.min(ev.clientX - caja.left + 14, caja.width - info.offsetWidth - 8)}px`;
    info.style.top = `${Math.min(ev.clientY - caja.top + 14, caja.height - info.offsetHeight - 8)}px`;
  }
  function ocultarInfo() { info.hidden = true; }

  const ficha = $("#ficha-mapa");
  function colocarFicha(ev) {
    const caja = contenedor.getBoundingClientRect();
    ficha.hidden = false;
    const limite = caja.width < 760 ? caja.width : caja.width - 416;
    ficha.style.left = `${Math.max(8, Math.min(ev.clientX - caja.left + 16, limite - ficha.offsetWidth - 8))}px`;
    ficha.style.top = `${Math.max(8, Math.min(ev.clientY - caja.top - 20, caja.height - ficha.offsetHeight - 8))}px`;
    ocultarInfo();
  }
  function ocultarFicha() { ficha.hidden = true; }

  function abrirFicha(ev, e) {
    const enlaces = (e.enlaces?.length ? e.enlaces : e.url ? [e.url] : []).slice(0, 3);
    const dominio = (u) => { try { return new URL(u).hostname.replace(/^www\./, ""); } catch { return u; } };
    ficha.innerHTML = `<button class="cerrar" aria-label="${t("Cerrar")}">×</button>
      <h3>${esc(tituloEvento(e))}</h3>
      <p class="meta">${esc(detalleEvento(e))}</p>
      ${e.tipo === "conflicto" || e.tipo === "protesta" ? `<p class="meta">${t("Lo recoge la prensa: es una señal, no un hecho verificado.")}</p>` : ""}
      ${enlaces.length ? `<ul>${enlaces.map((u) => `<li><a href="${esc(u)}" target="_blank" rel="noopener">${esc(dominio(u))}</a></li>`).join("")}</ul>` : ""}
      ${e.pais ? `<div class="acciones"><button class="principal" data-pais="${e.pais}">${esc(t("Ver {pais}", { pais: nombrePais(e.pais) }))}</button></div>` : ""}`;
    colocarFicha(ev);
  }

  function abrirFichaPaso(ev, p) {
    ficha.innerHTML = `<button class="cerrar" aria-label="${t("Cerrar")}">×</button>
      <h3>${esc(tb(p.nombre))}</h3>
      <p class="meta">${esc(tb(p.porque))}.</p>
      <p>${p.hechos ? t("{n} en la zona en las últimas 24 horas.", { n: plural(p.hechos, "hecho violento", "hechos violentos") }) : t("Sin hechos violentos en la zona en las últimas 24 horas.")}
      ${p.nivel !== "verde" ? t(" Si sigue así, puede afectar al transporte marítimo y a los precios de la energía.") : ""}</p>`;
    colocarFicha(ev);
  }

  ficha.addEventListener("click", (ev) => { if (ev.target.closest(".cerrar")) ocultarFicha(); });
  svg.on("click", ocultarFicha);

  // ------------------------------------------------------- mover el mapa

  function centrarEn(a3) {
    const f = mundo?.features.find((x) => x.id === a3);
    if (!f) return;
    pararGiro();
    if (estado.modo === "globo") {
      const centro = d3.geoCentroid(f);
      const desde = [...rotacion];
      const hasta = [-centro[0], Math.max(-60, Math.min(60, -centro[1])), 0];
      const [[x0, y0], [x1, y1]] = d3.geoPath(d3.geoOrthographic().rotate(hasta).scale(escalaBase).translate(centroBase)).bounds(f);
      const kHasta = Math.max(1, Math.min(5, escalaBase / Math.max(x1 - x0, y1 - y0, 1)));
      const kDesde = ultimoZoom.k;
      const interpolar = d3.interpolate(desde, hasta);
      const paso = (t) => {
        rotacion = interpolar(t);
        const k = kDesde + (kHasta - kDesde) * t;
        ultimoZoom = d3.zoomIdentity.scale(k);
        svg.property("__zoom", ultimoZoom);
        proyeccion.rotate(rotacion).scale(escalaBase * k);
        redibujar();
      };
      if (reducirMovimiento) paso(1);
      else svg.transition("girar").duration(900).ease(d3.easeCubicInOut).tween("girar", () => paso);
    } else {
      const base = d3.geoPath(d3.geoNaturalEarth1().scale(escalaBase).translate(centroBase));
      const [[x0, y0], [x1, y1]] = base.bounds(f);
      const a = areaUtil();
      const k = Math.max(1, Math.min(6, 0.6 / Math.max((x1 - x0) / (a.x1 - a.x0), (y1 - y0) / (a.y1 - a.y0))));
      const destino = d3.zoomIdentity
        .translate((a.x0 + a.x1) / 2 - ((x0 + x1) / 2) * k, (a.y0 + a.y1) / 2 - ((y0 + y1) / 2) * k).scale(k);
      (reducirMovimiento ? svg : svg.transition().duration(700)).call(zoom.transform, destino);
    }
  }

  function empezarGiro() {
    if (reducirMovimiento || !giroActivo || estado.modo !== "globo" || girando) return;
    let previo = performance.now();
    girando = d3.timer((ahora) => {
      rotacion = [rotacion[0] + (ahora - previo) * 0.004, rotacion[1], 0];
      previo = ahora;
      proyeccion.rotate(rotacion);
      redibujar();
    });
  }
  function pararGiro() {
    clearTimeout(reanudar);
    if (girando) { girando.stop(); girando = null; }
  }
  // Vuelve a girar tras unos segundos sin tocar el mapa, salvo con un país abierto o reproduciendo
  function reanudarLuego() {
    clearTimeout(reanudar);
    reanudar = setTimeout(() => {
      if (!estado.elegido && !estado.reproduciendo) empezarGiro();
    }, ESPERA_GIRO);
  }
  function ponerGiro(activo) {
    giroActivo = activo;
    try { localStorage.setItem("atalaya-giro", activo ? "si" : "no"); } catch { /* sin almacenamiento */ }
    const b = $("#giro");
    if (b) { b.setAttribute("aria-pressed", String(activo)); b.title = activo ? t("Parar el giro") : t("Girar el globo"); }
    if (activo) empezarGiro(); else pararGiro();
  }

  function cambiarModo(modo) {
    if (modo === estado.modo) return;
    estado.modo = modo;
    document.querySelectorAll("[data-modo]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.modo === modo)));
    pararGiro();
    ultimoZoom = d3.zoomIdentity;
    svg.property("__zoom", d3.zoomIdentity);
    configurarProyeccion();
    redibujar();
    if (estado.elegido) centrarEn(estado.elegido);
    else empezarGiro();
    $("#giro").hidden = modo !== "globo";
  }

  // ----------------------------------------------------------------- panel

  const vistas = ["parte", "simulacion", "paises", "eventos", "titulares", "pais"];
  function mostrarVista(nombre) {
    for (const v of vistas) $(`#vista-${v}`).hidden = v !== nombre;
    // En la pestaña Simulación el mapa muestra el contagio simulado
    const simulando = nombre === "simulacion";
    if (simulando !== document.body.classList.contains("simulando")) {
      document.body.classList.toggle("simulando", simulando);
      dibujarPaises();
    }
    document.querySelectorAll(".pestanas button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.pestana === nombre)));
  }

  // Etiqueta corta y comprensible de cuánto está contrastado lo que se ve en el país
  const CONF_CORTA = { alta: t("Muy contrastado"), media: t("Contrastado"), baja: t("Solo prensa") };
  const etiquetaConfianza = (c) => (c ? `<span class="etiqueta-conf conf-${c}" title="${esc(CONFIANZA[c])}">${CONF_CORTA[c]}</span>` : "");

  function filaPais(a3, nota) {
    const p = estado.alertas[a3];
    if (!p) return "";
    return `<button class="fila" data-pais="${a3}">
      <span class="punto ${p.nivel}"></span>
      <span class="nombre">${esc(nombrePais(a3))}${etiquetaConfianza(p.confianza)}<span class="detalle">${esc(mayuscula(resumenPais(p, a3)))}</span></span>
      <span class="cifra ${p.escalada ? "sube" : ""}">${esc(nota ?? (p.escalada ? t("Empeora") : p.tendencia === "baja" ? t("Mejora") : ""))}</span>
    </button>`;
  }

  function resumenPais(p, a3) {
    if (p.motivos?.length) return p.motivos.map(tb).join(". ");
    const partes = [];
    const ev = estado.eventos.filter((e) => e.pais === a3);
    if (p.hechos_violentos) partes.push(plural(p.hechos_violentos, "hecho violento", "hechos violentos"));
    if (p.protestas_n) partes.push(plural(p.protestas_n, "protesta", "protestas"));
    const terremotos = ev.filter((e) => e.tipo === "terremoto").length;
    if (terremotos) partes.push(plural(terremotos, "terremoto", "terremotos"));
    if (ev.some((e) => e.tipo === "epidemia")) partes.push(t("brote epidémico"));
    if (p.internet) partes.push(t("corte de internet"));
    return partes.join(", ") || t("Sin eventos en las últimas 48 horas");
  }

  // Informe diario, con la estructura de un parte de inteligencia: primero la conclusión,
  // después los juicios que la sostienen, qué vigilar y lo que afecta a España
  function pintarParte() {
    const el = $("#vista-parte");
    const paises = Object.entries(estado.alertas);
    if (!paises.length) {
      el.innerHTML = `<p class="vacio">${t("Todavía no hay datos. La primera actualización automática los descargará en unos minutos.")}</p>`;
      return;
    }
    const inf = estado.informe || {};
    const cuenta = (n) => paises.filter(([, p]) => p.nivel === n).length;
    const { suben = [], bajan = [] } = estado.parte;
    const c = inf.conclusion || {};
    const cambiosAyer = lista([suben.length && t("{n} de nivel", { n: plural(suben.length, "sube", "suben") }), bajan.length && plural(bajan.length, "baja", "bajan")].filter(Boolean));
    let html = `<p class="seccion-informe">${t("Conclusión principal")}</p>
      <h2 class="titular-parte">${c.pais ? `${esc(nombrePais(c.pais))}: ${esc(tb(c.texto || "").toLowerCase())}` : esc(tb(c.texto || "Sin crisis nuevas destacables"))}</h2>
      <p class="resumen">${t("{rojo} {paises} en alerta y {ambar} para vigilar.", { rojo: `<strong>${cuenta("rojo")}</strong>`, paises: cuenta("rojo") === 1 ? t("país") : t("países"), ambar: `<strong>${cuenta("ambar")}</strong>` })}
      ${suben.length || bajan.length ? esc(t(" Desde ayer, {cambios}.", { cambios: cambiosAyer })) : ""}
      ${estado.calibrando ? t(" El histórico aún es corto: la comparación con lo habitual de cada país empieza a contar cuando hay una semana de datos.") : ""}</p>`;

    if (estado.mios.size) {
      html += `<h3 class="grupo">${t("Mis países")}</h3>` + [...estado.mios].map((a3) => {
        const p = estado.alertas[a3];
        return `<button class="fila" data-pais="${a3}"><span class="punto ${p ? p.nivel : "neutro"}"></span>
          <span class="nombre">${esc(nombrePais(a3))}${p?.escalada ? `<span class="empeora">${t("Empeora")}</span>` : ""}
          <span class="detalle">${p ? esc(mayuscula(resumenPais(p, a3))) : t("Sin eventos recientes")}${p?.pronostico && p.pronostico.riesgo !== "bajo" ? `. ${esc(tb(p.pronostico.texto))}` : ""}</span></span>
          <span class="cifra"></span></button>`;
      }).join("");
    }
    if (inf.juicios?.length) {
      html += `<h3 class="grupo">${t("Juicios clave")}</h3>` + inf.juicios.map((j) => `<button class="fila juicio" data-pais="${j.pais}">
        <span class="punto ${j.nivel}"></span>
        <span class="nombre">${esc(nombrePais(j.pais))}${etiquetaConfianza(j.confianza)}
          <span class="detalle"><strong>${esc(tb(j.escenario || j.pronostico || ""))}</strong>${j.porque?.length ? `. ${esc(j.porque.map(tb).join(". "))}.` : ""}</span>
          ${j.escenario && j.pronostico ? `<span class="detalle">${esc(tb(j.pronostico))}.</span>` : ""}</span>
        <span class="cifra"></span></button>`).join("");
    }
    if (inf.vigilar?.length) {
      html += `<h3 class="grupo">${t("Qué vigilar en las próximas 72 horas")}</h3>` + inf.vigilar.map((v) => `<button class="fila sin-punto" data-pais="${v.pais}">
        <span class="nombre">${esc(nombrePais(v.pais))}: ${esc(tb(v.escenario).toLowerCase())}
          <span class="detalle">${v.si_aparece?.length ? esc(t("Subiría si aparece: {x}.", { x: v.si_aparece.map(tb).join(` ${t("o")} `).toLowerCase() })) : ""}</span></span>
        <span class="cifra"></span></button>`).join("");
    }
    if (inf.espana?.length) {
      html += `<h3 class="grupo">${t("Interés para España")}</h3>` + inf.espana.map((e) => e.pais ? `<button class="fila" data-pais="${e.pais}">
        <span class="punto ${e.nivel}"></span>
        <span class="nombre">${esc(nombrePais(e.pais))}<span class="detalle">${esc(e.por.map(tb).join(". "))}</span></span>
        <span class="cifra"></span></button>` : `<div class="fila"><span class="punto ${e.nivel}"></span>
        <span class="nombre">${esc(tb(e.nombre))}<span class="detalle">${esc(e.por.map(tb).join(". "))}</span></span><span class="cifra"></span></div>`).join("");
    }
    if (inf.regiones?.length) {
      html += `<h3 class="grupo">${t("Regiones con más tensión")}</h3>` + inf.regiones.map((r) => `<div class="fila">
        <span class="punto ${r.nivel === "verde" ? "neutro" : r.nivel}"></span>
        <span class="nombre">${esc(tb(r.region))}<span class="detalle">${esc(lista([
          r.rojo.length && t("en alerta: {x}", { x: lista(r.rojo.map((a) => nombrePais(a))) }),
          r.ambar.length && t("para vigilar: {x}", { x: lista(r.ambar.map((a) => nombrePais(a))) }),
          r.empeoran.length && t("empeoran: {x}", { x: lista(r.empeoran.map((a) => nombrePais(a))) })].filter(Boolean)))}</span></span>
        <span class="cifra"></span></div>`).join("");
    }

    if (inf.fechas?.length) {
      html += `<h3 class="grupo">${t("Fechas clave")}</h3>` + inf.fechas.map((x) => {
        const p = estado.alertas[x.pais];
        return `<button class="fila" data-pais="${x.pais}"><span class="punto ${p ? p.nivel : "neutro"}"></span>
          <span class="nombre">${esc(nombrePais(x.pais))}<span class="detalle">${esc(x.nombre)}</span></span>
          <span class="cifra">${esc(diaMes(x.fecha))}</span></button>`;
      }).join("") + `<p class="detalle-gris nota">${t("Elecciones y referendos en las próximas semanas, según Wikidata. Son fechas con más riesgo de protestas, cortes de internet o crisis de gobierno.")}</p>`;
    }

    const pasos = [...estado.pasos].sort((a, b) => b.hechos - a.hechos);
    if (pasos.length) {
      html += `<h3 class="grupo">${t("Rutas marítimas estratégicas")}</h3>` + pasos.map((p) => `<div class="fila">
        <span class="punto ${p.nivel === "verde" ? "neutro" : p.nivel}"></span>
        <span class="nombre">${esc(tb(p.nombre))}<span class="detalle">${esc(tb(p.porque))}</span></span>
        <span class="cifra ${p.nivel !== "verde" ? "sube" : ""}">${p.hechos ? plural(p.hechos, "hecho", "hechos") : t("Sin hechos")}</span></div>`).join("");
    }

    const f = estado.fiabilidad || {};
    html += `<h3 class="grupo">${t("Acierto de los pronósticos")}</h3><p class="resumen">${f.alto?.total
      ? t("De {n} de empeoramiento probable en los últimos 30 días, se cumplieron {a} ({p} %).", { n: plural(f.alto.total, "pronóstico", "pronósticos"), a: f.alto.aciertos, p: Math.round(100 * f.alto.aciertos / f.alto.total) })
        + (f.bajo?.total ? t(" De los poco probables, empeoró el {p} %.", { p: Math.round(100 * f.bajo.aciertos / f.bajo.total) }) : "")
      : t("Se medirá cuando haya más de una semana de histórico: cada pronóstico se compara con lo que pasó en los 7 días siguientes.")}</p>`;
    const r = estado.rendimiento || {};
    if (r.brier != null) {
      const porc = (x) => pct(Math.round(x * 100));
      const mejor = (m) => (m > 0.02 ? t("acierta un {p} más", { p: porc(m) }) : m < -0.02 ? t("acierta un {p} menos", { p: porc(-m) }) : t("acierta lo mismo"));
      html += `<div class="rendimiento"><p class="resumen"><strong>${t("Rendimiento del modelo")}</strong> ${esc(t("({n} en {d}{r}).", { n: plural(r.muestras, "pronóstico", "pronósticos"), d: plural(r.dias, "día", "días"), r: r.reconstruidas ? t(", {n} de días reconstruidos con GDELT", { n: numero.format(r.reconstruidas) }) : "" }))}
        ${esc(t("Comparado con decir siempre la misma probabilidad, {a}; comparado con fiarse solo del nivel actual de cada país, {b}.", { a: mejor(r.mejora_media), b: mejor(r.mejora_persistencia) }))}
        <span class="detalle-gris">${t("Puntuación de Brier {n} (0 es perfecto).", { n: r.brier.toLocaleString(LOCALE, { minimumFractionDigits: 3, maximumFractionDigits: 3 }) })}</span></p>
        <table class="calibracion"><thead><tr><th>${t("Pronóstico")}</th><th>${t("Probabilidad que da")}</th><th>${t("Empeoró de verdad")}</th><th>${t("Casos")}</th></tr></thead><tbody>
        ${(r.calibracion || []).map((c) => `<tr><td>${t({ alto: "Probable", medio: "Posible", bajo: "Poco probable" }[c.riesgo])}</td><td>${porc(c.dicho)}</td><td>${porc(c.observado)}</td><td>${numero.format(c.muestras)}</td></tr>`).join("")}
        </tbody></table></div>`;
    }
    const mo = estado.modeloAprendido;
    if (mo && mo.muestras) {
      const v = mo.validacion;
      html += `<div class="rendimiento"><p class="resumen"><strong>${t("Pronóstico aprendido")}</strong> `;
      if (mo.activo) {
        html += esc(t("En uso. Se entrena cada día con {n} casos y se valida con los días más recientes, que no ha visto: ahí acierta un {p} más que decir siempre la frecuencia media.", { n: numero.format(mo.muestras), p: pct(Math.round(v.mejora * 100)) })) + `</p>`;
        if (mo.importancia?.length) html += `<p class="detalle-gris">${t("Lo que más pesa:")} ${esc(mo.importancia.slice(0, 4).map((x) => `${tb(x.nombre).toLowerCase()} (${x.peso > 0 ? "↑" : "↓"})`).join(", "))}.</p>`;
      } else {
        html += esc(t("Todavía no se usa: {m}. Mientras, el pronóstico sigue reglas fijas.", { m: tb(mo.motivo || "").toLowerCase() })) + `</p>`;
      }
      html += `</div>`;
    }

    const fuentes = Object.entries(estado.fuentes);
    if (fuentes.length) {
      html += `<h3 class="grupo">${t("Estado de las fuentes")}</h3><ul class="fuentes">` + fuentes.map(([n, fu]) =>
        `<li class="${fu.ok ? "" : "caida"}">${esc(tb(n))}: ${fu.ok ? t("al día") : `${t("sin respuesta")}${fu.ultimo_ok ? t(", datos de {t}", { t: haceCuanto(fu.ultimo_ok) }) : ""}`}</li>`).join("") + "</ul>";
    }
    el.innerHTML = html;
  }

  // Simulación de escenarios: siempre con el aviso de que no tiene validez oficial
  function pintarSimulacion() {
    const el = $("#vista-simulacion");
    const sim = estado.simulacion || {};
    let html = `<div class="aviso-simulacion" role="note"><strong>${t("Esto es una simulación.")}</strong> ${esc(sim.aviso ? tb(sim.aviso) : t("Simulación automática basada en noticias y datos públicos. No tiene ninguna validez oficial."))}</div>`;
    if (!sim.casos?.length) {
      el.innerHTML = html + `<p class="vacio">${t("No hay crisis con datos suficientes para simular ahora mismo.")}</p>`;
      return;
    }
    const nombres = (xs) => lista((xs || []).map((a) => nombrePais(a)));
    const r = sim.resumen || {};
    html += `<p class="resumen">${esc(t("Qué podría pasar en los próximos {d} días en {n}. En el mapa, los países rayados son los que podrían contagiarse.", { d: sim.horizonte_dias || 7, n: plural(sim.casos.length, "crisis abierta", "crisis abiertas") }))}</p>
      <div class="sim-resumen">
        <p><span>${t("Más riesgo de escalada")}</span><strong>${esc(nombres(r.mas_escala))}</strong></p>
        <p><span>${t("Más margen para contenerse")}</span><strong>${esc(nombres(r.mas_contiene))}</strong></p>
      </div>`;

    if (sim.regiones?.length) {
      html += `<h3 class="grupo">${t("Por regiones: que al menos una crisis escale")}</h3>` + sim.regiones.map((g) => `<div class="fila">
        <span class="punto ${g.probabilidad >= 60 ? "rojo" : g.probabilidad >= 35 ? "ambar" : "neutro"}"></span>
        <span class="nombre">${esc(tb(g.region))}<span class="detalle">${esc(nombres(g.paises.slice(0, 4)))}${g.paises.length > 4 ? t(" y {n} más", { n: g.paises.length - 4 }) : ""}</span></span>
        <span class="cifra">≈ ${pct(g.probabilidad)}</span></div>`).join("");
    }

    const ramaTitulo = { escala: t("Escala"), igual: t("Sigue igual"), contiene: t("Se contiene") };
    const detallados = sim.casos.slice(0, sim.detallados || 8);
    const resto = sim.casos.slice(sim.detallados || 8);
    html += `<h3 class="grupo">${t("Las crisis más graves, en detalle")}</h3>`;
    for (const c of detallados) {
      html += `<article class="caso-sim">
        <header><button class="enlace-pais" data-pais="${c.pais}"><span class="punto ${c.nivel}"></span>${esc(nombrePais(c.pais))}</button>
          <span class="etiqueta-sim">${t("Simulado")}</span>${etiquetaConfianza(c.confianza)}</header>
        ${c.escenario ? `<p class="detalle-gris">${esc(t("Escenario principal: {x}.", { x: tb(c.escenario).toLowerCase() }))}</p>` : ""}
        <ul class="ramas">${c.ramas.map((rm) => `<li class="rama rama-${rm.id}">
          <span class="barra" style="--p:${rm.probabilidad}%"></span>
          <span class="rama-cab"><strong>${ramaTitulo[rm.id]}</strong><span>≈ ${pct(rm.probabilidad)} <small>(${rm.intervalo[0]}–${pct(rm.intervalo[1])})</small>, ${esc(tb(rm.palabras))}</span></span>
          <span class="rama-texto">${esc(tb(rm.texto))}</span></li>`).join("")}</ul>
        ${c.factores?.length ? `<p class="sim-linea"><strong>${t("Por qué:")}</strong> ${esc(lista(c.factores.map(tb)))}.</p>` : ""}
        ${c.contagio?.length ? `<p class="sim-linea"><strong>${t("Si escala, podría extenderse a:")}</strong> ${esc(lista(c.contagio.map((v) => `${nombrePais(v.pais)} (≈ ${pct(v.probabilidad)})`)))}.</p>` : ""}
        ${c.espana?.length ? `<p class="sim-linea"><strong>${t("Para España:")}</strong> ${esc(c.espana.map(tb).join(" "))}</p>` : ""}
        ${c.confirman?.length ? `<p class="sim-linea"><strong>${t("Señales de que escala:")}</strong> ${esc(lista(c.confirman.map(tb)).toLowerCase())}.</p>` : ""}
        <p class="sim-linea"><strong>${t("Señales de que se contiene:")}</strong> ${esc(lista(c.desmienten.map(tb)).toLowerCase())}.</p>
      </article>`;
    }
    if (resto.length) {
      html += `<h3 class="grupo">${t("El resto de crisis abiertas")}</h3>
        <div class="sim-tabla-cab"><span></span><span>${t("Escala")}</span><span>${t("Igual")}</span><span>${t("Se contiene")}</span></div>` +
        resto.map((c) => `<button class="fila sim-fila" data-pais="${c.pais}">
          <span class="punto ${c.nivel}"></span>
          <span class="nombre">${esc(nombrePais(c.pais))}<span class="detalle">${esc(c.escenario ? tb(c.escenario) : t(c.nivel !== "verde" ? "Crisis prolongada, sin señales nuevas" : "Sin escenario dominante"))}</span></span>
          ${c.ramas.map((rm) => `<span class="sim-pct sim-${rm.id}" title="${esc(ramaTitulo[rm.id])}: ${rm.intervalo[0]}–${pct(rm.intervalo[1])}">${pct(rm.probabilidad)}</span>`).join("")}
        </button>`).join("");
    }

    const pesos = { alto: sim.pesos?.alto ?? 40, medio: sim.pesos?.medio ?? 25, bajo: sim.pesos?.bajo ?? 10 };
    const metodo = IDIOMA === "en" ? t("SIM_METODO", pesos)
      : `La probabilidad de que una crisis escale parte del ${pesos.alto} % si el pronóstico es que probablemente empeore, del ${pesos.medio} % si es posible y del ${pesos.bajo} % si es poco probable.
      Sube con cada indicador encendido, si la situación empeora en la última semana o se acelera en las últimas 12 horas, si hay vecinos en crisis y si el país ya está en alerta; baja si se frena.
      El rango entre paréntesis es el margen de incertidumbre: más estrecho cuantas más fuentes independientes coinciden.`;
    html += `<h3 class="grupo">${t("Cómo se simula")}</h3><p class="resumen">
      ${metodo}
      ${sim.calibrado ? t("Estas probabilidades ya están ajustadas con el acierto real de los pronósticos anteriores.") : t("Cuando haya suficientes pronósticos comprobados, las probabilidades se ajustarán solas con su acierto real.")}
      ${t("En una semana, lo más frecuente es que una crisis siga como está: por eso «sigue igual» suele ser la rama más probable.")}</p>`;
    el.innerHTML = html;
  }

  function pintarPaises() {
    const el = $("#vista-paises");
    const orden = Object.entries(estado.alertas).map(([a3, a]) => ({ a3, ...a }))
      .sort((a, b) => NIVELES[a.nivel].orden - NIVELES[b.nivel].orden || b.escalada - a.escalada || b.puntuacion - a.puntuacion);
    if (!orden.length) { el.innerHTML = `<p class="vacio">${t("Todavía no hay datos.")}</p>`; return; }
    let html = "", grupo = null;
    for (const p of orden) {
      if (p.nivel !== grupo) { grupo = p.nivel; html += `<h3 class="grupo">${NIVELES[grupo].texto}</h3>`; }
      html += filaPais(p.a3);
    }
    el.innerHTML = html;
  }

  function filaEvento(e, conPais = true) {
    const deGdelt = e.tipo === "conflicto" || e.tipo === "protesta";
    const partes = [];
    if (conPais && e.pais) partes.push(nombrePais(e.pais));
    if (deGdelt) partes.push(t(e.tipo === "conflicto" ? "{n} de ataques o enfrentamientos" : "{n} de protestas", { n: plural(e.menciones, "noticia", "noticias") }));
    else if (e.lugar && !["internet", "aviso", "epidemia", "crisis"].includes(e.tipo)) partes.push(e.lugar);
    return `<a class="fila" href="${esc(e.url || "#")}" target="_blank" rel="noopener">
      <span class="punto ${deGdelt ? "neutro" : e.nivel}"></span>
      <span class="nombre">${esc(tituloEvento(e))}<span class="detalle">${esc(partes.join(", "))}</span></span>
      <span class="cifra">${haceCuanto(e.fecha)}</span>
    </a>`;
  }

  function pintarEventos() {
    const de = (tipo) => estado.eventos.filter((e) => e.tipo === tipo);
    const top = (tipo) => (estado.capas.has(tipo) ? de(tipo).sort((a, b) => b.menciones - a.menciones).slice(0, 15) : []);
    const secciones = [
      [t("Cambios en avisos de viaje esta semana"), de("aviso")],
      [t("Brotes epidémicos (OMS, 30 días)"), estado.capas.has("epidemia") ? de("epidemia") : []],
      [t("Crisis humanitarias abiertas"), de("crisis").filter((e) => e.estado === "alert")],
      [t("Monedas que se hunden frente al dólar (7 días)"), de("economia")],
      [t("Incendios por satélite muy por encima de lo habitual"), de("incendios")],
      [t("Apagones vistos por satélite"), de("apagon")],
      [t("Lluvias extremas medidas por satélite"), de("lluvia")],
      [t("Cortes de internet grandes en 24 horas"), estado.capas.has("internet") ? de("internet").sort((a, b) => b.peso - a.peso) : []],
      [t("Más noticias de ataques o enfrentamientos"), top("conflicto")],
      [t("Más noticias de protestas"), top("protesta")],
      [t("Terremotos y desastres de los últimos 7 días"), estado.eventos.filter((e) => ["terremoto", "desastre"].includes(e.tipo) && estado.capas.has(e.tipo)).slice(0, 100)],
    ];
    const html = secciones.filter(([, xs]) => xs.length).map(([t, xs]) => `<h3 class="grupo">${t}</h3>` + xs.map((e) => filaEvento(e)).join("")).join("");
    $("#vista-eventos").innerHTML = html || `<p class="vacio">${t("No hay eventos en las capas activas.")}</p>`;
  }

  function pintarTitulares() {
    const tit = estado.titulares;
    $("#vista-titulares").innerHTML = tit.length
      ? `<p class="resumen">${t("Noticias en español de las últimas 24 horas sobre ataques, ofensivas, evacuaciones y terremotos.")}</p>` +
        tit.map((n) => `<a class="fila sin-punto" lang="es" href="${esc(n.url)}" target="_blank" rel="noopener">
          <span class="nombre">${esc(n.titulo)}<span class="detalle">${esc(n.medio)}</span></span>
          <span class="cifra">${haceCuanto(n.fecha)}</span></a>`).join("")
      : `<p class="vacio">${t("No hay titulares disponibles ahora mismo.")}</p>`;
  }

  function grafica(serie) {
    if (!serie || serie.length < 2) return "";
    const w = 300, h = 54, max = Math.max(...serie, 1);
    const x = (i) => (i / (serie.length - 1)) * (w - 8) + 4;
    const y = (v) => h - 6 - (v / max) * (h - 14);
    const puntos = serie.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`);
    const u = serie.length - 1;
    return `<figure class="grafica">
      <svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" role="img" aria-label="${t("Puntuación de los últimos {n} días", { n: serie.length })}">
        <path class="area" d="M${x(0)},${h - 6}L${puntos.join("L")}L${x(u)},${h - 6}Z" />
        <path class="linea" d="M${puntos.join("L")}" />
        <circle cx="${x(u)}" cy="${y(serie[u])}" r="3.5" />
      </svg>
      <figcaption>${t("Puntuación de los últimos {n} días", { n: serie.length })}</figcaption>
    </figure>`;
  }

  // Evolución completa del país con el histórico: un punto por día, coloreado por nivel.
  // Pinchar un día abre la foto del mundo de ese día.
  function evolucion(a3) {
    const h = estado.historico;
    const dias = h ? Object.keys(h).sort() : [];
    if (dias.length < 2) return null;
    const serie = dias.map((d) => ({ d, v: h[d][a3]?.[0] ?? 0, n: h[d][a3]?.[1] ?? 0 }));
    const w = 300, hgt = 70, max = Math.max(...serie.map((p) => p.v), 1);
    const x = (i) => (i / (serie.length - 1)) * (w - 10) + 5;
    const y = (v) => hgt - 8 - (v / max) * (hgt - 18);
    const puntos = serie.map((p, i) => `${x(i).toFixed(1)},${y(p.v).toFixed(1)}`);
    const color = ["var(--frontera)", "var(--ambar)", "var(--rojo)"];
    const marcado = estado.dia || dias.at(-1);
    return `<figure class="grafica evolucion">
      <svg viewBox="0 0 ${w} ${hgt}" role="img" aria-label="${esc(t("Evolución desde {d}", { d: fechaDia(dias[0]) }))}">
        <path class="area" d="M${x(0)},${hgt - 8}L${puntos.join("L")}L${x(serie.length - 1)},${hgt - 8}Z" />
        <path class="linea" d="M${puntos.join("L")}" />
        ${serie.map((p, i) => `<circle class="dia${p.d === marcado ? " marcado" : ""}" data-dia="${p.d}" cx="${x(i)}" cy="${y(p.v)}" r="${p.d === marcado ? 4.5 : 3}" fill="${color[p.n]}"><title>${esc(t("{d}: {n} puntos", { d: fechaDia(p.d), n: numero.format(p.v) }))}</title></circle>`).join("")}
      </svg>
      <figcaption>${esc(t("Evolución desde el {d}. Pincha un día para ver el mundo ese día.", { d: fechaLarga.format(new Date(`${dias[0]}T12:00:00Z`)) }))}</figcaption>
    </figure>`;
  }

  function explicar(a) {
    const partes = [];
    const n = (x) => numero.format(x);
    if (a.conflicto) partes.push(t("{n} por hechos violentos", { n: n(a.conflicto) }) + (a.cuota_violencia ? t(" (el {p} % de lo que se cuenta del país)", { p: Math.round(a.cuota_violencia * 100) }) : ""));
    if (a.protestas) partes.push(t("{n} por protestas", { n: n(a.protestas) }));
    if (a.desastres) partes.push(t("{n} por terremotos y desastres", { n: n(a.desastres) }));
    if (a.epidemias) partes.push(t("{n} por brotes epidémicos", { n: n(a.epidemias) }));
    if (a.internet) partes.push(t("{n} por cortes de internet", { n: n(a.internet) }));
    if (a.avisos) partes.push(t("{n} por subir el aviso de viaje", { n: n(a.avisos) }));
    if (a.humanitaria) partes.push(t("{n} por crisis humanitaria", { n: n(a.humanitaria) }));
    if (a.economia) partes.push(t("{n} por la caída de su moneda", { n: n(a.economia) }));
    if (a.incendios) partes.push(t("{n} por incendios detectados por satélite", { n: n(a.incendios) }));
    if (a.apagon) partes.push(t("{n} por apagones vistos por satélite", { n: n(a.apagon) }));
    if (a.lluvias) partes.push(t("{n} por lluvias extremas", { n: n(a.lluvias) }));
    let texto = partes.length ? t(estado.dia ? "La puntuación de ese día suma {x}." : "La puntuación de hoy suma {x}.", { x: lista(partes) }) : "";
    if (a.tendencia === "sube") texto += t(" Está por encima de lo habitual para este país.");
    else if (a.tendencia === "baja") texto += t(" Está por debajo de lo habitual para este país.");
    else if (a.tendencia === "estable") texto += t(" Es parecida a lo habitual para este país.");
    if (a.aviso_viaje) texto += t(" EE. UU. tiene su aviso de viaje en nivel {n} de 4 ({t}).", { n: a.aviso_viaje, t: AVISOS[a.aviso_viaje] });
    if (a.confianza) texto += ` ${CONF_CORTA[a.confianza]}: ${CONFIANZA[a.confianza].toLowerCase()}.`;
    return texto.trim();
  }

  // Gráfica mínima de la luz respecto a lo normal (1 = como siempre)
  function miniSerie(serie) {
    const w = 120, h = 26, max = Math.max(1.2, ...serie.map((s) => s[1]));
    const x = (i) => (i / (serie.length - 1)) * w, y = (v) => h - (v / max) * h;
    const linea = serie.map((s, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(s[1]).toFixed(1)}`).join("");
    return ` <svg class="mini-serie" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" aria-hidden="true"><line x1="0" x2="${w}" y1="${y(1)}" y2="${y(1)}"/><path d="${linea}"/></svg>`;
  }
  const titulo = (t) => String(t).toLowerCase().replace(/(^|[\s-])(\p{L})/gu, (_, a, b) => a + b.toUpperCase());

  function abrirPais(a3, respaldo, centrar = true) {
    estado.elegido = a3;
    const a = estado.alertas[a3];
    const ev = estado.eventos.filter((e) => e.pais === a3);
    let html = `<button class="volver" data-volver>${t("Volver")}</button><div class="ficha">
      <h2>${esc(nombrePais(a3, respaldo))} <button class="estrella" data-mio="${a3}" aria-pressed="${estado.mios.has(a3)}"
        title="${estado.mios.has(a3) ? t("Quitar de mis países") : t("Seguir este país")}">${estado.mios.has(a3) ? t("★ Siguiendo") : t("☆ Seguir")}</button></h2>
      <p class="estado"><span class="punto ${a ? a.nivel : "neutro"}"></span>${a ? NIVELES[a.nivel].texto : t("Sin eventos recientes")}
        ${a?.escalada ? `<span class="empeora">${t("Empeora")}</span>` : ""}${etiquetaConfianza(a?.confianza)}</p>`;
    if (a) {
      if (a.motivos?.length) html += `<ul class="motivos">${a.motivos.map((m) => `<li>${esc(tb(m))}</li>`).join("")}</ul>`;
      html += `<dl class="cifras">
        <div><dt>${estado.dia ? t("Ese día") : t("Hoy")}</dt><dd>${numero.format(a.puntuacion)}</dd></div>
        <div><dt>${t("Media 30 días")}</dt><dd>${a.tendencia === "sin datos" ? "–" : numero.format(a.media)}</dd></div>
        <div><dt>${t("Tendencia")}</dt><dd>${t({ sube: "Sube", baja: "Baja", estable: "Estable" }[a.tendencia] || "–")}</dd></div>
      </dl>${evolucion(a3) ?? grafica(a.serie)}<p class="explicacion">${esc(explicar(a))}</p>`;
    }
    html += `</div>`;
    if (a?.pronostico || a?.escenarios?.length) {
      html += `<h3 class="grupo">${t("Pronóstico y escenarios")}</h3><div class="ficha">`;
      if (a.pronostico) html += `<p class="pronostico riesgo-${a.pronostico.riesgo}"><strong>${esc(tb(a.pronostico.texto))}${a.pronostico.probabilidad != null ? ` (${pct(Math.round(a.pronostico.probabilidad * 100))})` : ""}.</strong>${a.pronostico.probabilidad != null ? ` <span class="detalle-gris">${t("Probabilidad del modelo aprendido de los datos.")}</span>` : ""} <span class="detalle-gris">${t("Estimación automática, sin validez oficial.")}</span>${a.pronostico.pendiente ? t(" Tendencia de la última semana: {n} puntos al día.", { n: (a.pronostico.pendiente > 0 ? "+" : "") + numero.format(a.pronostico.pendiente) }) : ""}</p>`;
      const relevantes = (a.escenarios || []).filter((e) => e.riesgo !== "bajo");
      if (!relevantes.length) html += `<p class="explicacion">${t("Ningún escenario de crisis tiene indicadores suficientes ahora mismo.")}</p>`;
      for (const e of relevantes) {
        html += `<div class="escenario riesgo-${e.riesgo}"><p><strong>${esc(tb(e.estimativo))} ${esc(tb(e.nombre).toLowerCase())}</strong>${e.rebajado ? ` <span class="detalle-gris">${t("(rebajado un grado por señales de desescalada)")}</span>` : ""}</p><ul>${e.indicadores.map((i) =>
          `<li class="${i.activo ? "activo" : ""}"><span aria-hidden="true">${i.activo ? "●" : "○"}</span> ${esc(tb(i.texto))}${i.activo ? "" : `<span class="oculto">${t(" (no se observa)")}</span>`}</li>`).join("")}</ul></div>`;
      }
      if (a.vecinos_mal?.length) html += `<p class="explicacion">${esc(t("Vecinos en alerta o empeorando: {x}.", { x: lista(a.vecinos_mal.map((v) => nombrePais(v))) }))}</p>`;
      html += `</div>`;
    }
    if (a?.elecciones?.length || a?.divisa_caida || a?.incendios_veces || a?.luces?.length || a?.lluvia_extrema?.mm) {
      html += `<h3 class="grupo">${t("Señales tempranas")}</h3><div class="ficha">`;
      if (a.divisa_caida) html += `<p><strong>${t("Su moneda ha perdido un {p} % frente al dólar en 7 días.", { p: Math.round(a.divisa_caida * 100) })}</strong>${t(" Las caídas bruscas suelen adelantarse a protestas o crisis de gobierno.")}</p>`;
      if (a.luces?.length) {
        html += `<p><strong>${t("Luces nocturnas vistas por satélite")}</strong> <span class="detalle-gris">${t("(NASA Black Marble, respecto al mes anterior)")}</span></p><ul class="motivos luces">`
          + a.luces.slice(0, 3).map((x) => `<li class="${x.razon <= 0.5 ? "apagado" : ""}">${esc(x.lugar)}: <strong>${pct(Math.round(x.razon * 100))}</strong> ${t("de lo normal")} <span class="detalle-gris">(${esc(diaMes(x.fecha))})</span>`
            + (x.serie?.length > 2 ? miniSerie(x.serie) : "") + `</li>`).join("") + `</ul>`;
      }
      if (a.lluvia_extrema?.mm) html += `<p><strong>${t("Lluvias extremas: hasta {mm} mm en 3 días sobre unos {km2} km².", { mm: numero.format(a.lluvia_extrema.mm), km2: numero.format(a.lluvia_extrema.km2) })}</strong>${t(" Riesgo de inundaciones (NASA GPM IMERG).")}</p>`;
      if (a.incendios_veces) html += `<p><strong>${t("El satélite detecta {v} veces más incendios de lo habitual.", { v: numero.format(a.incendios_veces) })}</strong>${t(" En zonas de combate suelen delatar bombardeos o frentes activos; también pueden ser quemas agrícolas.")}</p>`;
      if (a.elecciones?.length) html += `<p><strong>${t("Próximas citas electorales:")}</strong></p><ul class="motivos">${a.elecciones.map((x) => `<li>${esc(diaMes(x.fecha))}: ${x.url ? `<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.nombre)}</a>` : esc(x.nombre)}</li>`).join("")}</ul>`;
      html += `</div>`;
    }
    const an = a?.analisis;
    if (an && (an.donde || an.actores || an.contra || an.alternativas || an.desmentiria)) {
      html += `<h3 class="grupo">${t("Análisis")}</h3><div class="ficha analisis">`;
      if (an.donde?.length) html += `<p><strong>${t("Dónde se concentra la violencia:")}</strong> ${esc(an.donde.map(([r, c]) => `${r} (${pct(Math.round(c * 100))})`).join(", "))}.</p>`;
      if (an.actores?.length) html += `<p><strong>${t("Quién contra quién")}</strong> <span class="detalle-gris">${t("(nombres tal como los codifica GDELT, en inglés)")}</span>:</p><ul class="motivos">${an.actores.map(([x, y]) => `<li>${esc(t("{a} contra {b}", { a: titulo(x), b: titulo(y) }))}</li>`).join("")}</ul>`;
      if (an.contra?.length) html += `<p><strong>${t("Señales en contra:")}</strong></p><ul class="motivos contra">${an.contra.map((m) => `<li>${esc(tb(m))}</li>`).join("")}</ul>`;
      if (an.alternativas?.length) html += `<p><strong>${t("Otras explicaciones posibles:")}</strong></p><ul class="motivos">${an.alternativas.map((m) => `<li>${esc(tb(m))}</li>`).join("")}</ul>`;
      if (an.desmentiria?.length) html += `<p><strong>${esc(t("Qué desmentiría «{x}»:", { x: tb(an.hipotesis).toLowerCase() }))}</strong></p><ul class="motivos">${an.desmentiria.map((m) => `<li>${esc(tb(m))}</li>`).join("")}</ul>`;
      html += `</div>`;
    }
    if (a?.exteriores || a?.espana?.length || a?.muertes_ucdp) {
      html += `<h3 class="grupo">${t("España")}</h3><div class="ficha">`;
      if (a.exteriores) {
        html += `<p class="exteriores nivel-ext-${a.exteriores.nivel}"><strong>${esc(t("Exteriores: {x}.", { x: tb(a.exteriores.texto) }))}</strong>
          ${a.exteriores.notas ? `${IDIOMA === "en" ? ` <span class="detalle-gris">(original in Spanish)</span>` : ""} <span lang="es">${esc(a.exteriores.notas.slice(0, 280))}${a.exteriores.notas.length > 280 ? "…" : ""}</span>` : ""}
          ${a.exteriores.actualizacion ? `<span class="detalle-gris">${esc(t(" Actualizado el {d}.", { d: new Date(a.exteriores.actualizacion + "T12:00:00Z").toLocaleDateString(LOCALE, { day: "numeric", month: "long", year: "numeric" }) }))}</span>` : ""}
          ${a.exteriores.url ? ` <a href="${esc(a.exteriores.url)}" target="_blank" rel="noopener">${t("Ver la ficha")}</a>` : ""}</p>`;
      }
      if (a.espana?.length) html += `<ul class="motivos">${a.espana.map((m) => `<li>${esc(tb(m))}</li>`).join("")}</ul>`;
      if (a.muertes_ucdp) html += `<p class="explicacion">${t("{n} en conflictos en los últimos 90 días (UCDP).", { n: plural(a.muertes_ucdp, "muerte verificada", "muertes verificadas") })}</p>`;
      html += `</div>`;
    }
    const analisis = (estado.analisis || []).filter((x) => x.paises?.includes(a3)).slice(0, 5);
    if (analisis.length) {
      html += `<h3 class="grupo">${t("Análisis de expertos")}</h3>` + analisis.map((x) => `<a class="fila sin-punto" lang="es" href="${esc(x.url)}" target="_blank" rel="noopener">
        <span class="nombre">${esc(x.titulo)}<span class="detalle">${esc(x.centro)}</span></span><span class="cifra">${haceCuanto(x.fecha)}</span></a>`).join("");
    }
    const prensa = (estado.titulares || []).filter((t) => t.paises?.includes(a3)).slice(0, 5);
    if (prensa.length) {
      html += `<h3 class="grupo">${t("En la prensa española")}</h3>` + prensa.map((x) => `<a class="fila sin-punto" lang="es" href="${esc(x.url)}" target="_blank" rel="noopener">
        <span class="nombre">${esc(x.titulo)}<span class="detalle">${esc(x.medio)}</span></span><span class="cifra">${haceCuanto(x.fecha)}</span></a>`).join("");
    }
    html += ev.length ? `<h3 class="grupo">${t("Eventos")}</h3>` + ev.map((e) => filaEvento(e, false)).join("") : `<p class="vacio">${t("No hay eventos registrados en este país en los últimos 7 días.")}</p>`;
    $("#vista-pais").innerHTML = html;
    mostrarVista("pais");
    plegar(false);
    ocultarFicha();
    dibujarPaises();
    actualizarEnlace();
    if (centrar) centrarEn(a3);
    if (!estado.historico) cargarHistorico().then(() => { if (estado.elegido === a3) abrirPais(a3, respaldo, false); });
  }

  // El enlace de la página recuerda el día y el país: #dia=2026-10-28&pais=SDN
  function actualizarEnlace() {
    const partes = [];
    if (estado.dia) partes.push(`dia=${estado.dia}`);
    if (estado.elegido) partes.push(`pais=${estado.elegido}`);
    try { history.replaceState(null, "", partes.length ? `#${partes.join("&")}` : location.pathname + location.search); } catch { /* sin historial */ }
  }

  let historicoPedido = null;
  function cargarHistorico() {
    historicoPedido ??= json(DATOS + "historico.json").then((h) => { estado.historico = h; }).catch(() => { estado.historico = {}; });
    return historicoPedido;
  }

  function cerrarPais() {
    estado.elegido = null;
    mostrarVista("parte");
    dibujarPaises();
    actualizarEnlace();
    reanudarLuego();
  }

  function plegar(cerrado) {
    $("#panel").classList.toggle("plegado", cerrado);
    const asa = $("#asa");
    asa.setAttribute("aria-expanded", String(!cerrado));
    asa.textContent = cerrado ? t("Mostrar panel") : t("Ocultar panel");
  }

  // ------------------------------------------------------------ el tiempo

  function ponerVentana(horas) {
    estado.ventanaHoras = horas;
    document.querySelectorAll("[data-ventana]").forEach((b) => b.setAttribute("aria-pressed", String(Number(b.dataset.ventana) === horas)));
    dibujarEventos();
  }

  function reproducir() {
    if (estado.reproduciendo) { pararReproduccion(); return; }
    pararGiro();
    ocultarFicha();
    const boton = $("#reproducir");
    const fin = Date.now();
    let momento = fin - 6 * 24 * HORA;
    boton.setAttribute("aria-pressed", "true");
    boton.textContent = t("Parar");
    estado.reproduciendo = setInterval(() => {
      estado.instante = momento;
      $("#reloj").textContent = mayuscula(fechaCorta.format(new Date(momento)));
      dibujarEventos();
      momento += 2 * HORA;
      if (momento > fin) pararReproduccion();
    }, 140);
  }

  function pararReproduccion() {
    clearInterval(estado.reproduciendo);
    estado.reproduciendo = null;
    estado.instante = null;
    const boton = $("#reproducir");
    boton.setAttribute("aria-pressed", "false");
    boton.textContent = t("Reproducir la semana");
    $("#reloj").textContent = "";
    dibujarEventos();
    reanudarLuego();
  }

  // ------------------------------------------------------------ controles

  document.addEventListener("click", (ev) => {
    const pestana = ev.target.closest("[data-pestana]");
    if (pestana) { mostrarVista(pestana.dataset.pestana); return; }
    const mio = ev.target.closest("[data-mio]");
    if (mio) {
      const a3 = mio.dataset.mio;
      if (estado.mios.has(a3)) estado.mios.delete(a3); else estado.mios.add(a3);
      guardarMios();
      abrirPais(a3, null, false);
      pintarParte();
      return;
    }
    const fila = ev.target.closest("[data-pais]");
    if (fila) { abrirPais(fila.dataset.pais); return; }
    if (ev.target.closest("[data-volver]")) { cerrarPais(); return; }
    if (ev.target.closest("[data-hoy]")) { verDia(null); return; }
    const dia = ev.target.closest("[data-dia]");
    if (dia) { verDia(dia.dataset.dia); return; }
    const modo = ev.target.closest("[data-modo]");
    if (modo) { cambiarModo(modo.dataset.modo); return; }
    if (ev.target.closest("#giro")) { ponerGiro(!giroActivo); return; }
    const z = ev.target.closest("[data-zoom]");
    if (z) {
      pararGiro();
      reanudarLuego();
      const paso = Number(z.dataset.zoom);
      if (paso === 0) {
        rotacion = [...ROTACION_INICIAL];
        svg.transition().duration(500).call(zoom.transform, d3.zoomIdentity);
      } else {
        svg.transition().duration(300).call(zoom.scaleBy, paso > 0 ? 1.6 : 1 / 1.6);
      }
      return;
    }
    const ventana = ev.target.closest("[data-ventana]");
    if (ventana) ponerVentana(Number(ventana.dataset.ventana));
  });

  document.querySelectorAll("[data-capa]").forEach((c) => c.addEventListener("change", () => {
    c.checked ? estado.capas.add(c.dataset.capa) : estado.capas.delete(c.dataset.capa);
    dibujarEventos();
    pintarEventos();
  }));

  $("#reproducir").addEventListener("click", reproducir);
  $("#dia").addEventListener("change", (ev) => verDia(ev.target.value));
  $("#asa").addEventListener("click", () => plegar(!$("#panel").classList.contains("plegado")));
  $("#ver-metodo").addEventListener("click", (ev) => { ev.preventDefault(); $("#metodo").showModal(); });

  $("#buscar").addEventListener("change", (ev) => {
    const texto = ev.target.value.trim().toLowerCase();
    if (!texto) return;
    const nombre = (f) => nombrePais(f.id, f.properties.name).toLowerCase();
    const encontrado = mundo?.features.find((f) => nombre(f) === texto) || mundo?.features.find((f) => nombre(f).startsWith(texto));
    if (encontrado) { abrirPais(encontrado.id, encontrado.properties.name); ev.target.value = ""; ev.target.blur(); }
  });

  let esperaResize;
  addEventListener("resize", () => {
    clearTimeout(esperaResize);
    esperaResize = setTimeout(() => { configurarProyeccion(); aplicarZoom(ultimoZoom); }, 150);
  });
  addEventListener("keydown", (ev) => {
    if (ev.key !== "Escape") return;
    if (!ficha.hidden) ocultarFicha();
    else if (!$("#vista-pais").hidden) cerrarPais();
  });
  addEventListener("hashchange", async () => {
    const d = location.hash.match(/dia=(\d{4}-\d{2}-\d{2})/);
    if ((d?.[1] ?? null) !== estado.dia) await verDia(d?.[1]);
    const m = location.hash.match(/pais=([A-Z]{3})/);
    if (m && m[1] !== estado.elegido) abrirPais(m[1]);
  });

  // ----------------------------------------------------------------- carga

  async function cargarDatos() {
    if (estado.dia) return; // viendo un día pasado: no se refresca
    try {
      const [eventos, alertas] = await Promise.all([json(DATOS + "eventos.json"), json(DATOS + "alertas.json")]);
      estado.eventos = eventos.eventos || [];
      estado.titulares = eventos.titulares || [];
      estado.fuentes = eventos.fuentes || {};
      estado.alertas = alertas.paises || {};
      estado.pasos = alertas.pasos || [];
      estado.parte = alertas.parte || {};
      estado.informe = alertas.informe || {};
      estado.simulacion = alertas.simulacion || {};
      estado.fiabilidad = alertas.fiabilidad || {};
      estado.rendimiento = alertas.rendimiento || {};
      estado.modeloAprendido = alertas.modelo || null;
      estado.analisis = eventos.analisis || [];
      estado.calibrando = alertas.calibrando;
      estado.actualizado = eventos.actualizado;
      const caidas = Object.entries(estado.fuentes).filter(([, f]) => !f.ok).map(([n]) => n);
      $("#actualizado").textContent = estado.actualizado
        ? t("Actualizado {t}", { t: haceCuanto(estado.actualizado) }) + (caidas.length ? t(". Sin respuesta de {x}: se muestran sus últimos datos", { x: lista(caidas.map(tb)) }) : "")
        : t("Esperando la primera actualización");
    } catch (e) {
      console.error(e);
      $("#actualizado").textContent = t("No se han podido cargar los datos. Vuelve a cargar la página en unos minutos.");
    }
    dibujarPaises();
    dibujarEventos();
    pintarParte();
    pintarSimulacion();
    pintarPaises();
    pintarEventos();
    pintarTitulares();
    if (estado.elegido && !$("#vista-pais").hidden) abrirPais(estado.elegido, null, false);
  }

  // ------------------------------------------------------------ histórico

  function pintarTodo() {
    dibujarPaises();
    dibujarEventos();
    pintarParte();
    pintarSimulacion();
    pintarPaises();
    pintarEventos();
    pintarTitulares();
    if (estado.elegido && !$("#vista-pais").hidden) abrirPais(estado.elegido, null, false);
  }

  async function verDia(dia) {
    if (estado.reproduciendo) pararReproduccion();
    const selector = $("#dia");
    if (!dia || dia >= hoy() || !estado.dias.includes(dia)) {
      estado.dia = null;
      estado.instante = null;
      selector.value = "";
      document.body.classList.remove("pasado");
      await cargarDatos();
      actualizarEnlace();
      return;
    }
    try {
      const foto = await json(`${DATOS}archivo/${dia}.json`);
      estado.dia = dia;
      estado.eventos = foto.eventos || [];
      estado.titulares = foto.titulares || [];
      estado.alertas = foto.paises || {};
      estado.pasos = foto.pasos || [];
      estado.parte = foto.parte || {};
      estado.informe = foto.informe || {};
      estado.simulacion = foto.simulacion || {};
      estado.fuentes = {};
      estado.calibrando = false;
      estado.instante = new Date(foto.actualizado).getTime();
      selector.value = dia;
      document.body.classList.add("pasado");
      $("#actualizado").innerHTML = `${esc(t("{d}, foto de las {h}.", { d: fechaDia(dia), h: new Date(foto.actualizado).toLocaleTimeString(LOCALE, { hour: "2-digit", minute: "2-digit" }) }))} <button class="volver-hoy" data-hoy>${t("Volver a hoy")}</button>`;
      pintarTodo();
      actualizarEnlace();
    } catch (e) {
      console.error(e);
      $("#actualizado").textContent = t("No hay foto guardada del {d}.", { d: IDIOMA === "en" ? fechaDia(dia) : fechaDia(dia).toLowerCase() });
    }
  }

  async function cargarIndice() {
    try {
      const { dias } = await json(DATOS + "archivo/indice.json");
      estado.dias = dias || [];
    } catch { estado.dias = []; }
    const selector = $("#dia");
    if (estado.dias.length > 1) {
      selector.min = estado.dias[0];
      selector.max = estado.dias.at(-1);
      $("#historico").hidden = false;
    }
  }

  // Versión del modelo, cambios y errores reconocidos (en el diálogo "Cómo se calcula")
  document.querySelectorAll("[data-anio]").forEach((e) => { e.textContent = String(new Date().getFullYear()); });

  async function cargarModelo() {
    try {
      const m = await json("data/modelo.json");
      $("#modelo").innerHTML = `<h3>${esc(t("Versión del modelo: {v}", { v: m.version }))}</h3><ul>${m.cambios.slice(0, 3).map((c) =>
        `<li><strong>${esc(c.version)}</strong>: ${esc(c.cambios.map(tb).join(". "))}.</li>`).join("")}</ul>
        <h3>${t("Errores reconocidos y corregidos")}</h3><ul>${m.errores.map((e) => `<li>${esc(tb(e.texto))}</li>`).join("")}</ul>`;
    } catch { /* opcional */ }
    document.querySelectorAll(".enlace-rss").forEach((x) => { x.href = DATOS + "avisos.xml"; });
  }

  // Selector de idioma
  window.I18N.traducirHTML();
  document.querySelectorAll("[data-idioma]").forEach((b) => {
    b.setAttribute("aria-pressed", String(b.dataset.idioma === IDIOMA));
    b.addEventListener("click", () => window.I18N.cambiar(b.dataset.idioma));
  });

  (async () => {
    const [geo, paises] = await Promise.all([json("data/mundo.geojson"), json("data/paises.json")]);
    mundo = geo;
    for (const p of paises) estado.paises.set(p.a3, p);
    $("#lista-paises").innerHTML = mundo.features.map((f) => `<option value="${esc(nombrePais(f.id, f.properties.name))}">`).join("");
    configurarProyeccion();
    await Promise.all([cargarDatos(), cargarIndice(), cargarModelo()]);
    const d = location.hash.match(/dia=(\d{4}-\d{2}-\d{2})/);
    if (d) await verDia(d[1]);
    const m = location.hash.match(/pais=([A-Z]{3})/);
    if (m) abrirPais(m[1]);
    else empezarGiro();
    $("#giro").setAttribute("aria-pressed", String(giroActivo));
    $("#giro").title = giroActivo ? t("Parar el giro") : t("Girar el globo");
    setInterval(cargarDatos, 5 * 60 * 1000);
  })();
})();
