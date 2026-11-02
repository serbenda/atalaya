/* atalaya: pinta el mapa a partir de los JSON que genera scripts/actualizar.py */
(() => {
  "use strict";

  const NIVELES = {
    rojo: { texto: "Alerta", orden: 0 },
    ambar: { texto: "Vigilar", orden: 1 },
    verde: { texto: "Lo habitual", orden: 2 },
  };
  const AVISOS = { 1: "precauciones normales", 2: "más precaución", 3: "reconsiderar el viaje", 4: "no viajar" };
  // En GitHub Pages los datos vienen de la rama `datos`; en local, de la carpeta data/
  const local = ["localhost", "127.0.0.1", ""].includes(location.hostname);
  const DATOS = local ? "data/" : document.querySelector('meta[name="atalaya-datos"]').content;
  const nombresRegion = new Intl.DisplayNames(["es"], { type: "region" });
  const relativo = new Intl.RelativeTimeFormat("es", { numeric: "auto" });
  const numero = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 1 });

  const estado = {
    eventos: [], titulares: [], alertas: {}, calibrando: true, actualizado: null,
    paises: new Map(), capas: new Set(["conflicto", "protesta", "terremoto", "desastre", "internet"]), elegido: null,
  };

  const $ = (sel) => document.querySelector(sel);
  const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function nombrePais(a3, respaldo) {
    const p = estado.paises.get(a3);
    if (p?.a2) {
      try { return nombresRegion.of(p.a2); } catch { /* código sin nombre en español */ }
    }
    return respaldo || p?.nombres?.[0] || a3;
  }

  function haceCuanto(iso) {
    const seg = (new Date(iso) - Date.now()) / 1000;
    const pasos = [[60, "second"], [60, "minute"], [24, "hour"], [7, "day"]];
    let v = seg;
    for (const [n, u] of pasos) {
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
  const capaMundo = svg.append("g");
  const proyeccion = d3.geoNaturalEarth1();
  const ruta = d3.geoPath(proyeccion);
  let mundo = null;
  let zoomActual = d3.zoomIdentity;
  let escalaMarcadores = 1; // los marcadores encogen con el mapa en pantallas pequeñas

  const zoom = d3.zoom().scaleExtent([1, 12]).on("zoom", (ev) => {
    zoomActual = ev.transform;
    capaMundo.attr("transform", ev.transform);
    capaMundo.selectAll(".marcador").attr("transform", (d) => marcadorTransform(d));
  });
  svg.call(zoom).on("dblclick.zoom", null);

  function marcadorTransform(d) {
    const [x, y] = proyeccion([d.lon, d.lat]);
    return `translate(${x},${y}) scale(${1 / zoomActual.k})`;
  }

  function encajar() {
    const { width, height } = contenedor.getBoundingClientRect();
    const movil = width < 760;
    // Deja sitio al panel lateral en escritorio y al inferior en móvil
    const ancho = movil ? width : width - Math.min(380, width * 0.4) - 32;
    const alto = movil ? height * 0.54 : height;
    proyeccion.fitExtent([[16, movil ? 90 : 40], [ancho - 16, alto - (movil ? 10 : 60)]], { type: "Sphere" });
    escalaMarcadores = Math.max(0.5, Math.min(1, proyeccion.scale() / 200));
    svg.attr("viewBox", `0 0 ${width} ${height}`);
    dibujar();
  }

  function dibujar() {
    if (!mundo) return;
    capaMundo.selectAll("*").remove();
    capaMundo.append("path").attr("class", "esfera").attr("d", ruta({ type: "Sphere" }));
    capaMundo.append("path").attr("class", "reticula").attr("d", ruta(d3.geoGraticule10()));

    capaMundo.append("g").selectAll("path").data(mundo.features).join("path")
      .attr("class", (f) => ["pais", estado.alertas[f.id]?.nivel, f.id === estado.elegido ? "elegido" : ""].join(" "))
      .attr("d", ruta)
      .on("click", (ev, f) => abrirPais(f.id, f.properties.name))
      .on("mousemove", (ev, f) => {
        const a = estado.alertas[f.id];
        mostrarGlobo(ev, `<strong>${esc(nombrePais(f.id, f.properties.name))}</strong><span>${a ? NIVELES[a.nivel].texto : "Sin eventos recientes"}</span>`);
      })
      .on("mouseleave", ocultarGlobo);

    const visibles = estado.eventos.filter((e) => estado.capas.has(e.tipo));
    // Los grandes debajo para que no tapen a los pequeños
    visibles.sort((a, b) => radio(b) - radio(a));
    capaMundo.append("g").selectAll(".marcador").data(visibles, (d) => d.id).join((enter) =>
      enter.append("path")
        .attr("class", (d) => `marcador ${d.tipo}`)
        .attr("d", (d) => forma(d))
        .attr("transform", (d) => marcadorTransform(d))
        .on("mousemove", (ev, d) => mostrarGlobo(ev, `<strong>${esc(d.titulo)}</strong><span>${esc(d.lugar)}${d.menciones ? `<br>${d.menciones} noticias en 24 horas` : ""}<br>${esc(d.fuente)}, ${haceCuanto(d.fecha)}</span>`))
        .on("mouseleave", ocultarGlobo)
        .on("click", (ev, d) => { if (d.url) window.open(d.url, "_blank", "noopener"); }));
  }

  function radio(d) {
    return radioBase(d) * escalaMarcadores;
  }

  function radioBase(d) {
    if (d.tipo === "terremoto") return 2 + Math.max((d.magnitud || 4.5) - 4.5, 0) * 3.2;
    if (d.tipo === "conflicto" || d.tipo === "protesta") return Math.min(16, 2 + Math.sqrt(d.menciones || 1) * 0.6);
    if (d.tipo === "internet") return 7;
    return d.nivel === "rojo" ? 8 : d.nivel === "ambar" ? 6.5 : 5;
  }

  function forma(d) {
    const r = radio(d);
    if (d.tipo === "desastre") return `M0,${-r}L${r * 0.9},${r * 0.6}L${-r * 0.9},${r * 0.6}Z`;
    if (d.tipo === "protesta") { const l = r * 0.8; return `M${-l},${-l}H${l}V${l}H${-l}Z`; }
    if (d.tipo === "internet") return `M0,${-r}L${r},0L0,${r}L${-r},0Z`;
    return `M${-r},0a${r},${r} 0 1,0 ${2 * r},0a${r},${r} 0 1,0 ${-2 * r},0`;
  }

  const globo = $("#globo");
  function mostrarGlobo(ev, html) {
    globo.innerHTML = html;
    globo.hidden = false;
    const caja = contenedor.getBoundingClientRect();
    const x = Math.min(ev.clientX - caja.left + 14, caja.width - globo.offsetWidth - 8);
    globo.style.left = `${x}px`;
    globo.style.top = `${ev.clientY - caja.top + 14}px`;
  }
  function ocultarGlobo() { globo.hidden = true; }

  function centrarEn(a3) {
    const f = mundo?.features.find((x) => x.id === a3);
    if (!f) return;
    const [[x0, y0], [x1, y1]] = ruta.bounds(f);
    const { width, height } = contenedor.getBoundingClientRect();
    const movil = width < 760;
    const ancho = movil ? width : width - 412;
    const alto = movil ? height * 0.54 : height;
    const k = Math.min(5, 0.6 / Math.max((x1 - x0) / ancho, (y1 - y0) / alto));
    const t = d3.zoomIdentity.translate(ancho / 2, alto / 2).scale(Math.max(k, 1)).translate(-(x0 + x1) / 2, -(y0 + y1) / 2);
    const reducir = matchMedia("(prefers-reduced-motion: reduce)").matches;
    (reducir ? svg : svg.transition().duration(700)).call(zoom.transform, t);
  }

  // ----------------------------------------------------------------- panel

  const vistas = ["paises", "eventos", "titulares", "pais"];
  function mostrarVista(nombre) {
    for (const v of vistas) $(`#vista-${v}`).hidden = v !== nombre;
    document.querySelectorAll(".pestanas button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.pestana === nombre)));
  }

  function pintarPaises() {
    const lista = Object.entries(estado.alertas)
      .map(([a3, a]) => ({ a3, ...a }))
      .sort((a, b) => NIVELES[a.nivel].orden - NIVELES[b.nivel].orden || b.puntuacion - a.puntuacion);
    const el = $("#vista-paises");
    if (!lista.length) {
      el.innerHTML = `<p class="vacio">Todavía no hay datos. La primera actualización automática los descargará en unos minutos.</p>`;
      return;
    }
    const cuenta = (n) => lista.filter((p) => p.nivel === n).length;
    let html = `<p class="resumen"><strong>${cuenta("rojo")}</strong> en alerta y <strong>${cuenta("ambar")}</strong> para vigilar${estado.calibrando ? ". El histórico aún es corto: de momento solo cuentan los valores absolutos" : ""}.</p>`;
    // Lo que más se está calentando: varios días subiendo o muy por encima de lo habitual
    const suben = lista.filter((p) => p.nivel !== "rojo" && (p.dias_subiendo >= 2 || p.z >= 1.5))
      .sort((a, b) => (b.dias_subiendo - a.dias_subiendo) || (b.z - a.z)).slice(0, 5);
    if (suben.length) {
      html += `<h3 class="grupo">Qué se está calentando</h3>`;
      for (const p of suben) html += filaPais(p, p.dias_subiendo >= 2 ? `${p.dias_subiendo} días subiendo` : "Inusual");
    }
    let grupo = null;
    for (const p of lista) {
      if (p.nivel !== grupo) {
        grupo = p.nivel;
        html += `<h3 class="grupo">${NIVELES[grupo].texto}</h3>`;
      }
      html += filaPais(p);
    }
    el.innerHTML = html;
  }

  function filaPais(p, nota) {
    const sube = p.tendencia === "sube";
    const cifra = nota || (sube ? "Sube" : p.tendencia === "baja" ? "Baja" : "");
    return `<button class="fila" data-pais="${p.a3}">
      <span class="punto ${p.nivel}"></span>
      <span class="nombre">${esc(nombrePais(p.a3))}<span class="detalle">${resumenPais(p)}</span></span>
      <span class="cifra ${sube || nota ? "sube" : ""}">${esc(cifra)}</span>
    </button>`;
  }

  function resumenPais(p) {
    const partes = [];
    const ev = estado.eventos.filter((e) => e.pais === p.a3);
    const terremotos = ev.filter((e) => e.tipo === "terremoto").length;
    const desastres = ev.filter((e) => e.tipo === "desastre").length;
    const plural = (n, s, pl) => `${n} ${n === 1 ? s : pl}`;
    if (p.hechos_violentos) partes.push(plural(p.hechos_violentos, "hecho violento", "hechos violentos"));
    if (p.protestas_n) partes.push(plural(p.protestas_n, "protesta", "protestas"));
    if (p.internet) partes.push("corte de internet");
    if (p.avisos) partes.push("sube el aviso de viaje");
    if (terremotos) partes.push(`${terremotos} terremoto${terremotos === 1 ? "" : "s"}`);
    if (desastres) partes.push(`${desastres} desastre${desastres === 1 ? "" : "s"}`);
    const texto = partes.join(", ") || "Sin eventos en las últimas 48 horas";
    return esc(texto.charAt(0).toUpperCase() + texto.slice(1));
  }

  function filaEvento(e, conPais = true) {
    const deGdelt = ["conflicto", "protesta"].includes(e.tipo);
    // En GDELT el lugar es lo importante ("Kharkiv, Kharkivs'ka Oblast', Ukraine"): va como título
    const titulo = deGdelt ? e.lugar.split(",")[0] : e.titulo;
    const partes = [];
    if (conPais && e.pais) partes.push(nombrePais(e.pais));
    if (deGdelt) partes.push(`${e.menciones} noticias de ${e.tipo === "conflicto" ? "ataques o enfrentamientos" : "protestas"}`);
    else if (e.lugar && !["internet", "aviso"].includes(e.tipo)) partes.push(e.lugar);
    return `<a class="fila" href="${esc(e.url || "#")}" target="_blank" rel="noopener">
      <span class="punto ${deGdelt ? "neutro" : e.nivel}"></span>
      <span class="nombre">${esc(titulo)}<span class="detalle">${esc(partes.join(", "))}</span></span>
      <span class="cifra">${haceCuanto(e.fecha)}</span>
    </a>`;
  }

  function pintarEventos() {
    const lista = estado.eventos.filter((e) => estado.capas.has(e.tipo) && ["terremoto", "desastre"].includes(e.tipo)).slice(0, 120);
    const top = (tipo) => estado.capas.has(tipo) ? estado.eventos.filter((e) => e.tipo === tipo)
      .sort((a, b) => b.menciones - a.menciones).slice(0, 20) : [];
    const conflictos = top("conflicto");
    const protestas = top("protesta");
    const cortes = estado.capas.has("internet") ? estado.eventos.filter((e) => e.tipo === "internet").sort((a, b) => b.peso - a.peso) : [];
    const avisos = estado.eventos.filter((e) => e.tipo === "aviso");
    let html = "";
    if (avisos.length) html += `<h3 class="grupo">Cambios en avisos de viaje esta semana</h3>` + avisos.map((e) => filaEvento(e)).join("");
    if (cortes.length) html += `<h3 class="grupo">Cortes de internet en las últimas 24 horas</h3>` + cortes.map((e) => filaEvento(e)).join("");
    if (conflictos.length) html += `<h3 class="grupo">Lugares con más noticias de ataques o enfrentamientos</h3>` + conflictos.map((e) => filaEvento(e)).join("");
    if (protestas.length) html += `<h3 class="grupo">Lugares con más noticias de protestas</h3>` + protestas.map((e) => filaEvento(e)).join("");
    if (lista.length) html += `<h3 class="grupo">Terremotos y desastres de los últimos 7 días</h3>` + lista.map((e) => filaEvento(e)).join("");
    $("#vista-eventos").innerHTML = html || `<p class="vacio">No hay eventos en las capas activas.</p>`;
  }

  function pintarTitulares() {
    const t = estado.titulares;
    $("#vista-titulares").innerHTML = t.length
      ? `<p class="resumen">Noticias en español de las últimas 24 horas sobre ataques, bombardeos y enfrentamientos.</p>` +
        t.map((n) => `<a class="fila sin-punto" href="${esc(n.url)}" target="_blank" rel="noopener">
          <span class="nombre">${esc(n.titulo)}<span class="detalle">${esc(n.medio)}</span></span>
          <span class="cifra">${haceCuanto(n.fecha)}</span></a>`).join("")
      : `<p class="vacio">No hay titulares disponibles ahora mismo.</p>`;
  }

  function abrirPais(a3, respaldo, centrar = true) {
    estado.elegido = a3;
    const a = estado.alertas[a3];
    const ev = estado.eventos.filter((e) => e.pais === a3);
    const nivel = a ? NIVELES[a.nivel].texto : "Sin eventos recientes";
    let html = `<button class="volver" data-volver>Volver a la lista</button><div class="ficha">
      <h2>${esc(nombrePais(a3, respaldo))}</h2>
      <p class="estado"><span class="punto ${a ? a.nivel : "neutro"}"></span>${nivel}</p>`;
    if (a) {
      html += `<dl class="cifras">
        <div><dt>Hoy</dt><dd>${numero.format(a.puntuacion)}</dd></div>
        <div><dt>Media 30 días</dt><dd>${a.tendencia === "sin datos" ? "–" : numero.format(a.media)}</dd></div>
        <div><dt>Tendencia</dt><dd>${{ sube: "Sube", baja: "Baja", estable: "Estable" }[a.tendencia] || "–"}</dd></div>
      </dl>
      ${grafica(a.serie)}
      <p class="explicacion">${explicar(a)}</p>`;
    }
    html += `</div>`;
    html += ev.length ? `<h3 class="grupo">Eventos</h3>` + ev.map((e) => filaEvento(e, false)).join("") : `<p class="vacio">No hay eventos registrados en este país en los últimos 7 días.</p>`;
    $("#vista-pais").innerHTML = html;
    mostrarVista("pais");
    plegar(false);
    dibujar();
    if (centrar) centrarEn(a3);
  }

  // Mini gráfica de los últimos 30 días; el último punto es hoy
  function grafica(serie) {
    if (!serie || serie.length < 2) return "";
    const w = 300, h = 54, max = Math.max(...serie, 1);
    const x = (i) => (i / (serie.length - 1)) * (w - 8) + 4;
    const y = (v) => h - 6 - (v / max) * (h - 14);
    const linea = serie.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
    const u = serie.length - 1;
    return `<figure class="grafica">
      <svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Puntuación de los últimos ${serie.length} días">
        <path d="${linea}" />
        <circle cx="${x(u)}" cy="${y(serie[u])}" r="3.5" />
      </svg>
      <figcaption>Últimos ${serie.length} días</figcaption>
    </figure>`;
  }

  function explicar(a) {
    const partes = [];
    if (a.conflicto) partes.push(`${numero.format(a.conflicto)} por hechos violentos${a.cuota_violencia ? ` (${Math.round(a.cuota_violencia * 100)} % de lo que se cuenta del país)` : ""}`);
    if (a.protestas) partes.push(`${numero.format(a.protestas)} por protestas`);
    if (a.desastres) partes.push(`${numero.format(a.desastres)} por terremotos y desastres`);
    if (a.internet) partes.push(`${numero.format(a.internet)} por cortes de internet`);
    if (a.avisos) partes.push(`${numero.format(a.avisos)} por subir el aviso de viaje`);
    const lista = partes.length > 1 ? `${partes.slice(0, -1).join(", ")} y ${partes.at(-1)}` : partes[0];
    let t = partes.length ? `La puntuación de hoy suma ${lista}.` : "";
    if (a.dias_subiendo >= 2) t += ` Lleva ${a.dias_subiendo} días seguidos subiendo.`;
    if (a.tendencia === "sube") t += " Está claramente por encima de lo habitual para este país.";
    else if (a.tendencia === "baja") t += " Está por debajo de lo habitual para este país.";
    else if (a.tendencia === "estable") t += " Es parecida a lo habitual para este país.";
    if (a.aviso_viaje) t += ` EE. UU. tiene su aviso de viaje en nivel ${a.aviso_viaje} de 4 (${AVISOS[a.aviso_viaje]}).`;
    return t;
  }

  function plegar(cerrado) {
    $("#panel").classList.toggle("plegado", cerrado);
    const asa = $("#asa");
    asa.setAttribute("aria-expanded", String(!cerrado));
    asa.textContent = cerrado ? "Mostrar panel" : "Ocultar panel";
  }

  // --------------------------------------------------------------- eventos

  document.addEventListener("click", (ev) => {
    const pestana = ev.target.closest("[data-pestana]");
    if (pestana) { mostrarVista(pestana.dataset.pestana); return; }
    const fila = ev.target.closest("[data-pais]");
    if (fila) { abrirPais(fila.dataset.pais); return; }
    if (ev.target.closest("[data-volver]")) {
      estado.elegido = null;
      mostrarVista("paises");
      dibujar();
      svg.transition().duration(500).call(zoom.transform, d3.zoomIdentity);
    }
  });

  document.querySelectorAll("[data-capa]").forEach((c) => c.addEventListener("change", () => {
    c.checked ? estado.capas.add(c.dataset.capa) : estado.capas.delete(c.dataset.capa);
    dibujar();
    pintarEventos();
  }));

  $("#asa").addEventListener("click", () => plegar(!$("#panel").classList.contains("plegado")));
  $("#ver-metodo").addEventListener("click", (ev) => { ev.preventDefault(); $("#metodo").showModal(); });
  addEventListener("resize", () => { clearTimeout(encajar.t); encajar.t = setTimeout(encajar, 150); });
  addEventListener("keydown", (ev) => { if (ev.key === "Escape" && !$("#vista-pais").hidden) document.querySelector("[data-volver]")?.click(); });

  // ----------------------------------------------------------------- carga

  async function cargarDatos() {
    try {
      const [eventos, alertas] = await Promise.all([json(DATOS + "eventos.json"), json(DATOS + "alertas.json")]);
      estado.eventos = eventos.eventos || [];
      estado.titulares = eventos.titulares || [];
      estado.alertas = alertas.paises || {};
      estado.calibrando = alertas.calibrando;
      estado.actualizado = eventos.actualizado;
      const caidas = Object.entries(eventos.fuentes || {}).filter(([, f]) => !f.ok).map(([n]) => n);
      if (caidas.length > 1) caidas.splice(-2, 2, `${caidas.at(-2)} y ${caidas.at(-1)}`);
      $("#actualizado").textContent = estado.actualizado
        ? `Actualizado ${haceCuanto(estado.actualizado)}${caidas.length ? `. Sin respuesta de ${caidas.join(", ")}: se muestran sus últimos datos` : ""}`
        : "Esperando la primera actualización";
    } catch (e) {
      console.error(e);
      $("#actualizado").textContent = "No se han podido cargar los datos. Recarga la página en unos minutos.";
    }
    pintarPaises();
    pintarEventos();
    pintarTitulares();
    dibujar();
    if (estado.elegido && !$("#vista-pais").hidden) abrirPais(estado.elegido, null, false);
  }

  (async () => {
    const [geo, paises] = await Promise.all([json("data/mundo.geojson"), json("data/paises.json")]);
    mundo = geo;
    for (const p of paises) estado.paises.set(p.a3, p);
    encajar();
    await cargarDatos();
    setInterval(cargarDatos, 5 * 60 * 1000);
  })();
})();
