/* atalaya: pinta el mapa a partir de los JSON que genera scripts/actualizar.py */
(() => {
  "use strict";

  // ------------------------------------------------------------ constantes

  const NIVELES = {
    rojo: { texto: "Alerta", orden: 0 },
    ambar: { texto: "Vigilar", orden: 1 },
    verde: { texto: "Actividad sin alerta", orden: 2 },
  };
  const CONFIANZA = {
    alta: "Coinciden varios tipos de fuente independientes",
    media: "Lo confirma una fuente oficial, técnica o sanitaria",
    baja: "Solo lo recoge la prensa",
  };
  const AVISOS = { 1: "precauciones normales", 2: "más precaución", 3: "reconsiderar el viaje", 4: "no viajar" };
  // Capa del mapa en la que se pinta cada tipo de evento (los que no tienen capa solo salen en el panel)
  const CAPA = { conflicto: "conflicto", protesta: "protesta", terremoto: "terremoto", desastre: "desastre",
    epidemia: "epidemia", internet: "internet", censura: "internet" };
  const HORA = 3600 * 1000;
  const ROTACION_INICIAL = [-10, -25, 0];

  // En GitHub Pages los datos vienen de la rama `datos`; en local, de la carpeta data/
  const local = ["localhost", "127.0.0.1", ""].includes(location.hostname);
  const DATOS = local ? "data/" : document.querySelector('meta[name="atalaya-datos"]').content;
  const reducirMovimiento = matchMedia("(prefers-reduced-motion: reduce)").matches;

  const nombresRegion = new Intl.DisplayNames(["es"], { type: "region" });
  const relativo = new Intl.RelativeTimeFormat("es", { numeric: "auto" });
  const numero = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 1 });
  const fechaCorta = new Intl.DateTimeFormat("es-ES", { weekday: "long", day: "numeric", hour: "2-digit", minute: "2-digit" });

  const estado = {
    eventos: [], titulares: [], alertas: {}, pasos: [], parte: {}, fuentes: {}, calibrando: true, actualizado: null,
    paises: new Map(), capas: new Set(["conflicto", "protesta", "terremoto", "desastre", "epidemia", "internet", "pasos"]),
    elegido: null, modo: "globo", ventanaHoras: 168, reproduciendo: null, instante: null,
    dia: null, dias: [], historico: null, informe: {}, fiabilidad: {}, analisis: [], simulacion: {},
  };
  const fechaLarga = new Intl.DateTimeFormat("es-ES", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  const fechaDia = (d) => mayuscula(fechaLarga.format(new Date(`${d}T12:00:00Z`)));
  const hoy = () => new Date().toISOString().slice(0, 10);

  const $ = (sel) => document.querySelector(sel);
  const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const mayuscula = (t) => (t ? t.charAt(0).toUpperCase() + t.slice(1) : t);
  const plural = (n, s, p) => `${numero.format(n)} ${n === 1 ? s : p}`;
  const lista = (xs) => (xs.length > 1 ? `${xs.slice(0, -1).join(", ")} y ${xs.at(-1)}` : xs[0] || "");

  function nombrePais(a3, respaldo) {
    const p = estado.paises.get(a3);
    if (p?.a2) {
      try { return nombresRegion.of(p.a2); } catch { /* código sin nombre en español */ }
    }
    return respaldo || p?.nombres?.[0] || a3;
  }

  const fechaHora = new Intl.DateTimeFormat("es-ES", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
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
        let texto = a ? `${NIVELES[a.nivel].texto}${a.escalada ? ", empeora" : ""}${a.motivos?.length ? `<br>${esc(a.motivos.join(". "))}` : ""}` : "Sin eventos recientes";
        const sim = estado.simulacion?.contagio?.[f.id];
        if (sim && document.body.classList.contains("simulando")) texto += `<br>Simulación: ${sim} % de contagio en 7 días (sin validez oficial)`;
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
      .on("mousemove", (ev, d) => mostrarInfo(ev, `<strong>${esc(d.nombre)}</strong><span>${esc(d.porque)}<br>${plural(d.hechos, "hecho violento", "hechos violentos")} en la zona en 24 horas</span>`))
      .on("mouseleave", ocultarInfo)
      .on("click", (ev, d) => { ev.stopPropagation(); abrirFichaPaso(ev, d); });
    p.select("text").text((d) => d.nombre);
    redibujar();
  }

  function tituloEvento(e) {
    return e.tipo === "conflicto" || e.tipo === "protesta" ? e.lugar.split(",")[0] : e.titulo;
  }

  function detalleEvento(e) {
    const partes = [];
    if (e.pais && !["aviso"].includes(e.tipo)) partes.push(nombrePais(e.pais));
    if (e.tipo === "conflicto") partes.push(`${plural(e.menciones, "noticia", "noticias")} de ataques o enfrentamientos`);
    else if (e.tipo === "protesta") partes.push(`${plural(e.menciones, "noticia", "noticias")} de protestas`);
    else if (e.lugar && !["internet", "aviso", "epidemia", "crisis"].includes(e.tipo)) partes.push(e.lugar);
    partes.push(`${e.fuente}, ${haceCuanto(e.fecha)}`);
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
    ficha.innerHTML = `<button class="cerrar" aria-label="Cerrar">×</button>
      <h3>${esc(tituloEvento(e))}</h3>
      <p class="meta">${esc(detalleEvento(e))}</p>
      ${e.tipo === "conflicto" || e.tipo === "protesta" ? `<p class="meta">Lo recoge la prensa: es una señal, no un hecho verificado.</p>` : ""}
      ${enlaces.length ? `<ul>${enlaces.map((u) => `<li><a href="${esc(u)}" target="_blank" rel="noopener">${esc(dominio(u))}</a></li>`).join("")}</ul>` : ""}
      ${e.pais ? `<div class="acciones"><button class="principal" data-pais="${e.pais}">Ver ${esc(nombrePais(e.pais))}</button></div>` : ""}`;
    colocarFicha(ev);
  }

  function abrirFichaPaso(ev, p) {
    ficha.innerHTML = `<button class="cerrar" aria-label="Cerrar">×</button>
      <h3>${esc(p.nombre)}</h3>
      <p class="meta">${esc(p.porque)}.</p>
      <p>${p.hechos ? `${plural(p.hechos, "hecho violento", "hechos violentos")} en la zona en las últimas 24 horas.` : "Sin hechos violentos en la zona en las últimas 24 horas."}
      ${p.nivel !== "verde" ? " Si sigue así, puede afectar al transporte marítimo y a los precios de la energía." : ""}</p>`;
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
    if (reducirMovimiento || estado.modo !== "globo" || girando) return;
    let previo = performance.now();
    girando = d3.timer((ahora) => {
      rotacion = [rotacion[0] + (ahora - previo) * 0.004, rotacion[1], 0];
      previo = ahora;
      proyeccion.rotate(rotacion);
      redibujar();
    });
  }
  function pararGiro() { if (girando) { girando.stop(); girando = null; } }

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

  const etiquetaConfianza = (c) => (c ? `<span class="etiqueta-conf conf-${c}" title="${esc(CONFIANZA[c])}">Confianza ${c}</span>` : "");

  function filaPais(a3, nota) {
    const p = estado.alertas[a3];
    if (!p) return "";
    return `<button class="fila" data-pais="${a3}">
      <span class="punto ${p.nivel}"></span>
      <span class="nombre">${esc(nombrePais(a3))}${etiquetaConfianza(p.confianza)}<span class="detalle">${esc(mayuscula(resumenPais(p, a3)))}</span></span>
      <span class="cifra ${p.escalada ? "sube" : ""}">${esc(nota ?? (p.escalada ? "Empeora" : p.tendencia === "baja" ? "Mejora" : ""))}</span>
    </button>`;
  }

  function resumenPais(p, a3) {
    if (p.motivos?.length) return p.motivos.join(". ");
    const partes = [];
    const ev = estado.eventos.filter((e) => e.pais === a3);
    if (p.hechos_violentos) partes.push(plural(p.hechos_violentos, "hecho violento", "hechos violentos"));
    if (p.protestas_n) partes.push(plural(p.protestas_n, "protesta", "protestas"));
    const terremotos = ev.filter((e) => e.tipo === "terremoto").length;
    if (terremotos) partes.push(plural(terremotos, "terremoto", "terremotos"));
    if (ev.some((e) => e.tipo === "epidemia")) partes.push("brote epidémico");
    if (p.internet) partes.push("corte de internet");
    return partes.join(", ") || "Sin eventos en las últimas 48 horas";
  }

  // Informe diario, con la estructura de un parte de inteligencia: primero la conclusión,
  // después los juicios que la sostienen, qué vigilar y lo que afecta a España
  function pintarParte() {
    const el = $("#vista-parte");
    const paises = Object.entries(estado.alertas);
    if (!paises.length) {
      el.innerHTML = `<p class="vacio">Todavía no hay datos. La primera actualización automática los descargará en unos minutos.</p>`;
      return;
    }
    const inf = estado.informe || {};
    const cuenta = (n) => paises.filter(([, p]) => p.nivel === n).length;
    const { suben = [], bajan = [] } = estado.parte;
    const c = inf.conclusion || {};
    let html = `<p class="seccion-informe">Conclusión principal</p>
      <h2 class="titular-parte">${c.pais ? `${esc(nombrePais(c.pais))}: ${esc((c.texto || "").toLowerCase())}` : esc(c.texto || "Sin crisis nuevas destacables")}</h2>
      <p class="resumen"><strong>${cuenta("rojo")}</strong> ${cuenta("rojo") === 1 ? "país" : "países"} en alerta y <strong>${cuenta("ambar")}</strong> para vigilar.
      ${suben.length || bajan.length ? ` Desde ayer, ${lista([suben.length && `${plural(suben.length, "sube", "suben")} de nivel`, bajan.length && `${plural(bajan.length, "baja", "bajan")}`].filter(Boolean))}.` : ""}
      ${estado.calibrando ? " El histórico aún es corto: la comparación con lo habitual de cada país empieza a contar cuando hay una semana de datos." : ""}</p>`;

    if (inf.juicios?.length) {
      html += `<h3 class="grupo">Juicios clave</h3>` + inf.juicios.map((j) => `<button class="fila juicio" data-pais="${j.pais}">
        <span class="punto ${j.nivel}"></span>
        <span class="nombre">${esc(nombrePais(j.pais))}${etiquetaConfianza(j.confianza)}
          <span class="detalle"><strong>${esc(j.escenario || j.pronostico || "")}</strong>${j.porque?.length ? `. ${esc(j.porque.join(". "))}.` : ""}</span>
          ${j.escenario && j.pronostico ? `<span class="detalle">${esc(j.pronostico)}.</span>` : ""}</span>
        <span class="cifra"></span></button>`).join("");
    }
    if (inf.vigilar?.length) {
      html += `<h3 class="grupo">Qué vigilar en las próximas 72 horas</h3>` + inf.vigilar.map((v) => `<button class="fila sin-punto" data-pais="${v.pais}">
        <span class="nombre">${esc(nombrePais(v.pais))}: ${esc(v.escenario.toLowerCase())}
          <span class="detalle">${v.si_aparece?.length ? `Subiría si aparece: ${esc(v.si_aparece.join(" o ").toLowerCase())}.` : ""}</span></span>
        <span class="cifra"></span></button>`).join("");
    }
    if (inf.espana?.length) {
      html += `<h3 class="grupo">Interés para España</h3>` + inf.espana.map((e) => e.pais ? `<button class="fila" data-pais="${e.pais}">
        <span class="punto ${e.nivel}"></span>
        <span class="nombre">${esc(nombrePais(e.pais))}<span class="detalle">${esc(e.por.join(". "))}</span></span>
        <span class="cifra"></span></button>` : `<div class="fila"><span class="punto ${e.nivel}"></span>
        <span class="nombre">${esc(e.nombre)}<span class="detalle">${esc(e.por.join(". "))}</span></span><span class="cifra"></span></div>`).join("");
    }
    if (inf.regiones?.length) {
      html += `<h3 class="grupo">Regiones con más tensión</h3>` + inf.regiones.map((r) => `<div class="fila">
        <span class="punto ${r.nivel === "verde" ? "neutro" : r.nivel}"></span>
        <span class="nombre">${esc(r.region)}<span class="detalle">${esc(lista([
          r.rojo.length && `en alerta: ${lista(r.rojo.map((a) => nombrePais(a)))}`,
          r.ambar.length && `para vigilar: ${lista(r.ambar.map((a) => nombrePais(a)))}`,
          r.empeoran.length && `empeoran: ${lista(r.empeoran.map((a) => nombrePais(a)))}`].filter(Boolean)))}</span></span>
        <span class="cifra"></span></div>`).join("");
    }

    const pasos = [...estado.pasos].sort((a, b) => b.hechos - a.hechos);
    if (pasos.length) {
      html += `<h3 class="grupo">Rutas marítimas estratégicas</h3>` + pasos.map((p) => `<div class="fila">
        <span class="punto ${p.nivel === "verde" ? "neutro" : p.nivel}"></span>
        <span class="nombre">${esc(p.nombre)}<span class="detalle">${esc(p.porque)}</span></span>
        <span class="cifra ${p.nivel !== "verde" ? "sube" : ""}">${p.hechos ? plural(p.hechos, "hecho", "hechos") : "Sin hechos"}</span></div>`).join("");
    }

    const f = estado.fiabilidad || {};
    html += `<h3 class="grupo">Acierto de los pronósticos</h3><p class="resumen">${f.alto?.total
      ? `De ${plural(f.alto.total, "pronóstico", "pronósticos")} de empeoramiento probable en los últimos 30 días, se cumplieron ${f.alto.aciertos} (${Math.round(100 * f.alto.aciertos / f.alto.total)} %).${f.bajo?.total ? ` De los poco probables, empeoró el ${Math.round(100 * f.bajo.aciertos / f.bajo.total)} %.` : ""}`
      : "Se medirá cuando haya más de una semana de histórico: cada pronóstico se compara con lo que pasó en los 7 días siguientes."}</p>`;

    const fuentes = Object.entries(estado.fuentes);
    if (fuentes.length) {
      html += `<h3 class="grupo">Estado de las fuentes</h3><ul class="fuentes">` + fuentes.map(([n, fu]) =>
        `<li class="${fu.ok ? "" : "caida"}">${esc(n)}: ${fu.ok ? "al día" : `sin respuesta${fu.ultimo_ok ? `, datos de ${haceCuanto(fu.ultimo_ok)}` : ""}`}</li>`).join("") + "</ul>";
    }
    el.innerHTML = html;
  }

  // Simulación de escenarios: siempre con el aviso de que no tiene validez oficial
  function pintarSimulacion() {
    const el = $("#vista-simulacion");
    const sim = estado.simulacion || {};
    let html = `<div class="aviso-simulacion" role="note"><strong>Esto es una simulación.</strong> ${esc(sim.aviso || "Simulación automática basada en noticias y datos públicos. No tiene ninguna validez oficial.")}</div>`;
    if (!sim.casos?.length) {
      el.innerHTML = html + `<p class="vacio">No hay crisis con datos suficientes para simular ahora mismo.</p>`;
      return;
    }
    const nombres = (xs) => lista((xs || []).map((a) => nombrePais(a)));
    const r = sim.resumen || {};
    html += `<p class="resumen">Qué podría pasar en los próximos ${sim.horizonte_dias || 7} días en ${plural(sim.casos.length, "crisis abierta", "crisis abiertas")}. En el mapa, los países rayados son los que podrían contagiarse.</p>
      <div class="sim-resumen">
        <p><span>Más riesgo de escalada</span><strong>${esc(nombres(r.mas_escala))}</strong></p>
        <p><span>Más margen para contenerse</span><strong>${esc(nombres(r.mas_contiene))}</strong></p>
      </div>`;

    if (sim.regiones?.length) {
      html += `<h3 class="grupo">Por regiones: que al menos una crisis escale</h3>` + sim.regiones.map((g) => `<div class="fila">
        <span class="punto ${g.probabilidad >= 60 ? "rojo" : g.probabilidad >= 35 ? "ambar" : "neutro"}"></span>
        <span class="nombre">${esc(g.region)}<span class="detalle">${esc(nombres(g.paises.slice(0, 4)))}${g.paises.length > 4 ? ` y ${g.paises.length - 4} más` : ""}</span></span>
        <span class="cifra">≈ ${g.probabilidad} %</span></div>`).join("");
    }

    const ramaTitulo = { escala: "Escala", igual: "Sigue igual", contiene: "Se contiene" };
    const detallados = sim.casos.slice(0, sim.detallados || 8);
    const resto = sim.casos.slice(sim.detallados || 8);
    html += `<h3 class="grupo">Las crisis más graves, en detalle</h3>`;
    for (const c of detallados) {
      html += `<article class="caso-sim">
        <header><button class="enlace-pais" data-pais="${c.pais}"><span class="punto ${c.nivel}"></span>${esc(nombrePais(c.pais))}</button>
          <span class="etiqueta-sim">Simulado</span>${etiquetaConfianza(c.confianza)}</header>
        ${c.escenario ? `<p class="detalle-gris">Escenario principal: ${esc(c.escenario.toLowerCase())}.</p>` : ""}
        <ul class="ramas">${c.ramas.map((rm) => `<li class="rama rama-${rm.id}">
          <span class="barra" style="--p:${rm.probabilidad}%"></span>
          <span class="rama-cab"><strong>${ramaTitulo[rm.id]}</strong><span>≈ ${rm.probabilidad} % <small>(${rm.intervalo[0]}–${rm.intervalo[1]} %)</small>, ${esc(rm.palabras)}</span></span>
          <span class="rama-texto">${esc(rm.texto)}</span></li>`).join("")}</ul>
        ${c.factores?.length ? `<p class="sim-linea"><strong>Por qué:</strong> ${esc(lista(c.factores))}.</p>` : ""}
        ${c.contagio?.length ? `<p class="sim-linea"><strong>Si escala, podría extenderse a:</strong> ${esc(lista(c.contagio.map((v) => `${nombrePais(v.pais)} (≈ ${v.probabilidad} %)`)))}.</p>` : ""}
        ${c.espana?.length ? `<p class="sim-linea"><strong>Para España:</strong> ${esc(c.espana.join(" "))}</p>` : ""}
        ${c.confirman?.length ? `<p class="sim-linea"><strong>Señales de que escala:</strong> ${esc(lista(c.confirman).toLowerCase())}.</p>` : ""}
        <p class="sim-linea"><strong>Señales de que se contiene:</strong> ${esc(lista(c.desmienten).toLowerCase())}.</p>
      </article>`;
    }
    if (resto.length) {
      html += `<h3 class="grupo">El resto de crisis abiertas</h3>
        <div class="sim-tabla-cab"><span></span><span>Escala</span><span>Igual</span><span>Se contiene</span></div>` +
        resto.map((c) => `<button class="fila sim-fila" data-pais="${c.pais}">
          <span class="punto ${c.nivel}"></span>
          <span class="nombre">${esc(nombrePais(c.pais))}<span class="detalle">${esc(c.escenario || (c.nivel !== "verde" ? "Crisis prolongada, sin señales nuevas" : "Sin escenario dominante"))}</span></span>
          ${c.ramas.map((rm) => `<span class="sim-pct sim-${rm.id}" title="${esc(ramaTitulo[rm.id])}: ${rm.intervalo[0]}–${rm.intervalo[1]} %">${rm.probabilidad} %</span>`).join("")}
        </button>`).join("");
    }

    html += `<h3 class="grupo">Cómo se simula</h3><p class="resumen">
      La probabilidad de que una crisis escale parte del ${sim.pesos?.alto ?? 40} % si el pronóstico es que probablemente empeore, del ${sim.pesos?.medio ?? 25} % si es posible y del ${sim.pesos?.bajo ?? 10} % si es poco probable.
      Sube con cada indicador encendido, si la situación empeora en la última semana o se acelera en las últimas 12 horas, si hay vecinos en crisis y si el país ya está en alerta; baja si se frena.
      El rango entre paréntesis es el margen de incertidumbre: más estrecho cuantas más fuentes independientes coinciden.
      ${sim.calibrado ? "Estas probabilidades ya están ajustadas con el acierto real de los pronósticos anteriores." : "Cuando haya suficientes pronósticos comprobados, las probabilidades se ajustarán solas con su acierto real."}
      En una semana, lo más frecuente es que una crisis siga como está: por eso «sigue igual» suele ser la rama más probable.</p>`;
    el.innerHTML = html;
  }

  function pintarPaises() {
    const el = $("#vista-paises");
    const orden = Object.entries(estado.alertas).map(([a3, a]) => ({ a3, ...a }))
      .sort((a, b) => NIVELES[a.nivel].orden - NIVELES[b.nivel].orden || b.escalada - a.escalada || b.puntuacion - a.puntuacion);
    if (!orden.length) { el.innerHTML = `<p class="vacio">Todavía no hay datos.</p>`; return; }
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
    if (deGdelt) partes.push(`${plural(e.menciones, "noticia", "noticias")} de ${e.tipo === "conflicto" ? "ataques o enfrentamientos" : "protestas"}`);
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
      ["Cambios en avisos de viaje esta semana", de("aviso")],
      ["Brotes epidémicos (OMS, 30 días)", estado.capas.has("epidemia") ? de("epidemia") : []],
      ["Crisis humanitarias abiertas", de("crisis").filter((e) => e.estado === "alert")],
      ["Cortes de internet grandes en 24 horas", estado.capas.has("internet") ? de("internet").sort((a, b) => b.peso - a.peso) : []],
      ["Más noticias de ataques o enfrentamientos", top("conflicto")],
      ["Más noticias de protestas", top("protesta")],
      ["Terremotos y desastres de los últimos 7 días", estado.eventos.filter((e) => ["terremoto", "desastre"].includes(e.tipo) && estado.capas.has(e.tipo)).slice(0, 100)],
    ];
    const html = secciones.filter(([, xs]) => xs.length).map(([t, xs]) => `<h3 class="grupo">${t}</h3>` + xs.map((e) => filaEvento(e)).join("")).join("");
    $("#vista-eventos").innerHTML = html || `<p class="vacio">No hay eventos en las capas activas.</p>`;
  }

  function pintarTitulares() {
    const t = estado.titulares;
    $("#vista-titulares").innerHTML = t.length
      ? `<p class="resumen">Noticias en español de las últimas 24 horas sobre ataques, ofensivas, evacuaciones y terremotos.</p>` +
        t.map((n) => `<a class="fila sin-punto" href="${esc(n.url)}" target="_blank" rel="noopener">
          <span class="nombre">${esc(n.titulo)}<span class="detalle">${esc(n.medio)}</span></span>
          <span class="cifra">${haceCuanto(n.fecha)}</span></a>`).join("")
      : `<p class="vacio">No hay titulares disponibles ahora mismo.</p>`;
  }

  function grafica(serie) {
    if (!serie || serie.length < 2) return "";
    const w = 300, h = 54, max = Math.max(...serie, 1);
    const x = (i) => (i / (serie.length - 1)) * (w - 8) + 4;
    const y = (v) => h - 6 - (v / max) * (h - 14);
    const puntos = serie.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`);
    const u = serie.length - 1;
    return `<figure class="grafica">
      <svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" role="img" aria-label="Puntuación de los últimos ${serie.length} días">
        <path class="area" d="M${x(0)},${h - 6}L${puntos.join("L")}L${x(u)},${h - 6}Z" />
        <path class="linea" d="M${puntos.join("L")}" />
        <circle cx="${x(u)}" cy="${y(serie[u])}" r="3.5" />
      </svg>
      <figcaption>Puntuación de los últimos ${serie.length} días</figcaption>
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
      <svg viewBox="0 0 ${w} ${hgt}" role="img" aria-label="Evolución desde ${fechaDia(dias[0])}">
        <path class="area" d="M${x(0)},${hgt - 8}L${puntos.join("L")}L${x(serie.length - 1)},${hgt - 8}Z" />
        <path class="linea" d="M${puntos.join("L")}" />
        ${serie.map((p, i) => `<circle class="dia${p.d === marcado ? " marcado" : ""}" data-dia="${p.d}" cx="${x(i)}" cy="${y(p.v)}" r="${p.d === marcado ? 4.5 : 3}" fill="${color[p.n]}"><title>${esc(fechaDia(p.d))}: ${numero.format(p.v)} puntos</title></circle>`).join("")}
      </svg>
      <figcaption>Evolución desde el ${esc(fechaLarga.format(new Date(`${dias[0]}T12:00:00Z`)))}. Pincha un día para ver el mundo ese día.</figcaption>
    </figure>`;
  }

  function explicar(a) {
    const partes = [];
    if (a.conflicto) partes.push(`${numero.format(a.conflicto)} por hechos violentos${a.cuota_violencia ? ` (el ${Math.round(a.cuota_violencia * 100)} % de lo que se cuenta del país)` : ""}`);
    if (a.protestas) partes.push(`${numero.format(a.protestas)} por protestas`);
    if (a.desastres) partes.push(`${numero.format(a.desastres)} por terremotos y desastres`);
    if (a.epidemias) partes.push(`${numero.format(a.epidemias)} por brotes epidémicos`);
    if (a.internet) partes.push(`${numero.format(a.internet)} por cortes de internet`);
    if (a.avisos) partes.push(`${numero.format(a.avisos)} por subir el aviso de viaje`);
    if (a.humanitaria) partes.push(`${numero.format(a.humanitaria)} por crisis humanitaria`);
    let t = partes.length ? `La puntuación ${estado.dia ? "de ese día" : "de hoy"} suma ${lista(partes)}.` : "";
    if (a.tendencia === "sube") t += " Está por encima de lo habitual para este país.";
    else if (a.tendencia === "baja") t += " Está por debajo de lo habitual para este país.";
    else if (a.tendencia === "estable") t += " Es parecida a lo habitual para este país.";
    if (a.aviso_viaje) t += ` EE. UU. tiene su aviso de viaje en nivel ${a.aviso_viaje} de 4 (${AVISOS[a.aviso_viaje]}).`;
    if (a.confianza) t += ` Confianza ${a.confianza}: ${CONFIANZA[a.confianza].toLowerCase()}.`;
    return t.trim();
  }

  function abrirPais(a3, respaldo, centrar = true) {
    estado.elegido = a3;
    const a = estado.alertas[a3];
    const ev = estado.eventos.filter((e) => e.pais === a3);
    let html = `<button class="volver" data-volver>Volver</button><div class="ficha">
      <h2>${esc(nombrePais(a3, respaldo))}</h2>
      <p class="estado"><span class="punto ${a ? a.nivel : "neutro"}"></span>${a ? NIVELES[a.nivel].texto : "Sin eventos recientes"}
        ${a?.escalada ? `<span class="empeora">Empeora</span>` : ""}${etiquetaConfianza(a?.confianza)}</p>`;
    if (a) {
      if (a.motivos?.length) html += `<ul class="motivos">${a.motivos.map((m) => `<li>${esc(m)}</li>`).join("")}</ul>`;
      html += `<dl class="cifras">
        <div><dt>${estado.dia ? "Ese día" : "Hoy"}</dt><dd>${numero.format(a.puntuacion)}</dd></div>
        <div><dt>Media 30 días</dt><dd>${a.tendencia === "sin datos" ? "–" : numero.format(a.media)}</dd></div>
        <div><dt>Tendencia</dt><dd>${{ sube: "Sube", baja: "Baja", estable: "Estable" }[a.tendencia] || "–"}</dd></div>
      </dl>${evolucion(a3) ?? grafica(a.serie)}<p class="explicacion">${esc(explicar(a))}</p>`;
    }
    html += `</div>`;
    if (a?.pronostico || a?.escenarios?.length) {
      html += `<h3 class="grupo">Pronóstico y escenarios</h3><div class="ficha">`;
      if (a.pronostico) html += `<p class="pronostico riesgo-${a.pronostico.riesgo}"><strong>${esc(a.pronostico.texto)}.</strong> <span class="detalle-gris">Estimación automática, sin validez oficial.</span>${a.pronostico.pendiente ? ` Tendencia de la última semana: ${a.pronostico.pendiente > 0 ? "+" : ""}${numero.format(a.pronostico.pendiente)} puntos al día.` : ""}</p>`;
      const relevantes = (a.escenarios || []).filter((e) => e.riesgo !== "bajo");
      if (!relevantes.length) html += `<p class="explicacion">Ningún escenario de crisis tiene indicadores suficientes ahora mismo.</p>`;
      for (const e of relevantes) {
        html += `<div class="escenario riesgo-${e.riesgo}"><p><strong>${esc(e.estimativo)} ${esc(e.nombre.toLowerCase())}</strong></p><ul>${e.indicadores.map((i) =>
          `<li class="${i.activo ? "activo" : ""}"><span aria-hidden="true">${i.activo ? "●" : "○"}</span> ${esc(i.texto)}${i.activo ? "" : `<span class="oculto"> (no se observa)</span>`}</li>`).join("")}</ul></div>`;
      }
      if (a.vecinos_mal?.length) html += `<p class="explicacion">Vecinos en alerta o empeorando: ${esc(lista(a.vecinos_mal.map((v) => nombrePais(v))))}.</p>`;
      html += `</div>`;
    }
    if (a?.exteriores || a?.espana?.length || a?.muertes_ucdp) {
      html += `<h3 class="grupo">España</h3><div class="ficha">`;
      if (a.exteriores) {
        html += `<p class="exteriores nivel-ext-${a.exteriores.nivel}"><strong>Exteriores: ${esc(a.exteriores.texto)}.</strong>
          ${a.exteriores.notas ? ` ${esc(a.exteriores.notas.slice(0, 280))}${a.exteriores.notas.length > 280 ? "…" : ""}` : ""}
          ${a.exteriores.actualizacion ? `<span class="detalle-gris"> Actualizado el ${esc(new Date(a.exteriores.actualizacion + "T12:00:00Z").toLocaleDateString("es-ES", { day: "numeric", month: "long", year: "numeric" }))}.</span>` : ""}
          ${a.exteriores.url ? ` <a href="${esc(a.exteriores.url)}" target="_blank" rel="noopener">Ver la ficha</a>` : ""}</p>`;
      }
      if (a.espana?.length) html += `<ul class="motivos">${a.espana.map((m) => `<li>${esc(m)}</li>`).join("")}</ul>`;
      if (a.muertes_ucdp) html += `<p class="explicacion">${plural(a.muertes_ucdp, "muerte verificada", "muertes verificadas")} en conflictos en los últimos 90 días (UCDP).</p>`;
      html += `</div>`;
    }
    const analisis = (estado.analisis || []).filter((x) => x.paises?.includes(a3)).slice(0, 5);
    if (analisis.length) {
      html += `<h3 class="grupo">Análisis de expertos</h3>` + analisis.map((x) => `<a class="fila sin-punto" href="${esc(x.url)}" target="_blank" rel="noopener">
        <span class="nombre">${esc(x.titulo)}<span class="detalle">${esc(x.centro)}</span></span><span class="cifra">${haceCuanto(x.fecha)}</span></a>`).join("");
    }
    const prensa = (estado.titulares || []).filter((t) => t.paises?.includes(a3)).slice(0, 5);
    if (prensa.length) {
      html += `<h3 class="grupo">En la prensa española</h3>` + prensa.map((t) => `<a class="fila sin-punto" href="${esc(t.url)}" target="_blank" rel="noopener">
        <span class="nombre">${esc(t.titulo)}<span class="detalle">${esc(t.medio)}</span></span><span class="cifra">${haceCuanto(t.fecha)}</span></a>`).join("");
    }
    html += ev.length ? `<h3 class="grupo">Eventos</h3>` + ev.map((e) => filaEvento(e, false)).join("") : `<p class="vacio">No hay eventos registrados en este país en los últimos 7 días.</p>`;
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
  }

  function plegar(cerrado) {
    $("#panel").classList.toggle("plegado", cerrado);
    const asa = $("#asa");
    asa.setAttribute("aria-expanded", String(!cerrado));
    asa.textContent = cerrado ? "Mostrar panel" : "Ocultar panel";
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
    let t = fin - 6 * 24 * HORA;
    boton.setAttribute("aria-pressed", "true");
    boton.textContent = "Parar";
    estado.reproduciendo = setInterval(() => {
      estado.instante = t;
      $("#reloj").textContent = mayuscula(fechaCorta.format(new Date(t)));
      dibujarEventos();
      t += 2 * HORA;
      if (t > fin) pararReproduccion();
    }, 140);
  }

  function pararReproduccion() {
    clearInterval(estado.reproduciendo);
    estado.reproduciendo = null;
    estado.instante = null;
    const boton = $("#reproducir");
    boton.setAttribute("aria-pressed", "false");
    boton.textContent = "Reproducir la semana";
    $("#reloj").textContent = "";
    dibujarEventos();
  }

  // ------------------------------------------------------------ controles

  document.addEventListener("click", (ev) => {
    const pestana = ev.target.closest("[data-pestana]");
    if (pestana) { mostrarVista(pestana.dataset.pestana); return; }
    const fila = ev.target.closest("[data-pais]");
    if (fila) { abrirPais(fila.dataset.pais); return; }
    if (ev.target.closest("[data-volver]")) { cerrarPais(); return; }
    if (ev.target.closest("[data-hoy]")) { verDia(null); return; }
    const dia = ev.target.closest("[data-dia]");
    if (dia) { verDia(dia.dataset.dia); return; }
    const modo = ev.target.closest("[data-modo]");
    if (modo) { cambiarModo(modo.dataset.modo); return; }
    const z = ev.target.closest("[data-zoom]");
    if (z) {
      pararGiro();
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
      estado.analisis = eventos.analisis || [];
      estado.calibrando = alertas.calibrando;
      estado.actualizado = eventos.actualizado;
      const caidas = Object.entries(estado.fuentes).filter(([, f]) => !f.ok).map(([n]) => n);
      $("#actualizado").textContent = estado.actualizado
        ? `Actualizado ${haceCuanto(estado.actualizado)}${caidas.length ? `. Sin respuesta de ${lista(caidas)}: se muestran sus últimos datos` : ""}`
        : "Esperando la primera actualización";
    } catch (e) {
      console.error(e);
      $("#actualizado").textContent = "No se han podido cargar los datos. Vuelve a cargar la página en unos minutos.";
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
      $("#actualizado").innerHTML = `${esc(fechaDia(dia))}, foto de las ${new Date(foto.actualizado).toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" })}. <button class="volver-hoy" data-hoy>Volver a hoy</button>`;
      pintarTodo();
      actualizarEnlace();
    } catch (e) {
      console.error(e);
      $("#actualizado").textContent = `No hay foto guardada del ${fechaDia(dia).toLowerCase()}.`;
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

  (async () => {
    const [geo, paises] = await Promise.all([json("data/mundo.geojson"), json("data/paises.json")]);
    mundo = geo;
    for (const p of paises) estado.paises.set(p.a3, p);
    $("#lista-paises").innerHTML = mundo.features.map((f) => `<option value="${esc(nombrePais(f.id, f.properties.name))}">`).join("");
    configurarProyeccion();
    await Promise.all([cargarDatos(), cargarIndice()]);
    const d = location.hash.match(/dia=(\d{4}-\d{2}-\d{2})/);
    if (d) await verDia(d[1]);
    const m = location.hash.match(/pais=([A-Z]{3})/);
    if (m) abrirPais(m[1]);
    else empezarGiro();
    setInterval(cargarDatos, 5 * 60 * 1000);
  })();
})();
