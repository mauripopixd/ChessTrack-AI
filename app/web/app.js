// ChessTrack AI · interfaz web mínima: sin frameworks ni dependencias, solo la API.
// Todo el texto que llega del servidor (sobre todo el del LLM) se inserta como texto, nunca
// como HTML: así una respuesta con <script> no se ejecuta (XSS).
"use strict";

// Mismo glifo relleno para los dos bandos (el color lo pone el CSS); ︎ pide la versión de
// texto: sin él, Windows dibuja ♟ como emoji.
const GLIFOS = { k: "♚", q: "♛", r: "♜", b: "♝", n: "♞", p: "♟" };
const PIEZAS = Object.fromEntries(
  Object.entries(GLIFOS).flatMap(([c, g]) => [[c, g + "︎"], [c.toUpperCase(), g + "︎"]]),
);
const ETIQUETAS = { buena: "buena", imprecision: "imprecisión", error: "error", error_grave: "error grave" };
const $ = (id) => document.getElementById(id);

const estado = {
  token: localStorage.getItem("token"), usuario: null, partida: null,
  seleccion: null, vista: 0, revision: null, ocupado: false, animando: false, extra: null,
};

// ------------------------------------------------------------------ API

async function api(ruta, { method = "GET", json, form } = {}) {
  const headers = {};
  let body;
  if (estado.token) headers.Authorization = `Bearer ${estado.token}`;
  if (json !== undefined) { headers["Content-Type"] = "application/json"; body = JSON.stringify(json); }
  if (form !== undefined) body = new URLSearchParams(form);
  const r = await fetch(ruta, { method, headers, body });
  if (r.status === 401 && estado.token) { salir(); throw new Error("Tu sesión caducó: entra de nuevo"); }
  if (r.status === 204) return null;
  const datos = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(mensajeError(datos, r.status));
  return datos;
}

function mensajeError(datos, status) {
  const d = datos.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d) && d.length) return d.map((e) => e.msg).join("; ");
  return `Error ${status}`;
}

// ------------------------------------------------------------------ vistas

function mostrar(vista) {
  for (const v of ["vista-acceso", "vista-partidas", "vista-partida"]) $(v).hidden = v !== vista;
  $("nav-usuario").hidden = vista === "vista-acceso";
}

async function iniciar() {
  if (!estado.token) return mostrar("vista-acceso");
  try {
    estado.usuario = await api("/users/me");
    $("nombre-usuario").textContent = estado.usuario.username;
    const id = Number(new URLSearchParams(location.search).get("partida"));
    if (id) await abrirPartida(id); else await verPartidas();
  } catch (e) {
    mostrar("vista-acceso");
    $("error-acceso").textContent = e.message;
  }
}

function salir() {
  localStorage.removeItem("token");
  estado.token = null;
  history.replaceState(null, "", "/");
  mostrar("vista-acceso");
}

// ------------------------------------------------------------------ acceso

function pestana(registro) {
  $("form-entrar").hidden = registro;
  $("form-registro").hidden = !registro;
  $("tab-entrar").classList.toggle("activa", !registro);
  $("tab-registro").classList.toggle("activa", registro);
  $("tab-entrar").setAttribute("aria-selected", String(!registro));
  $("tab-registro").setAttribute("aria-selected", String(registro));
  $("error-acceso").textContent = "";
}

async function entrar(username, password) {
  const t = await api("/auth/login", { method: "POST", form: { username, password } });
  estado.token = t.access_token;
  localStorage.setItem("token", t.access_token);
  await iniciar();
}

// ------------------------------------------------------------------ lista de partidas

async function verPartidas() {
  history.replaceState(null, "", "/");
  mostrar("vista-partidas");
  const pagina = await api("/coach/games?limit=50");
  const lista = $("lista-partidas");
  lista.replaceChildren();
  $("sin-partidas").hidden = pagina.items.length > 0;
  for (const p of pagina.items) {
    const li = document.createElement("li");
    li.className = "fila-partida";
    const b = document.createElement("button");
    b.type = "button";
    b.className = "enlace";
    const fecha = new Date(p.updated_at).toLocaleString();
    const { corto } = veredicto(p);
    b.textContent = `#${p.id} · ${p.color === "white" ? "blancas" : "negras"} · nivel ${p.level} · ${p.move_count} jugadas · ${fecha}`;
    b.addEventListener("click", () => abrirPartida(p.id));
    const etiqueta = document.createElement("span");
    etiqueta.className = `resultado-partida ${corto.clase}`;
    etiqueta.textContent = corto.texto;
    const borrar = document.createElement("button");
    borrar.type = "button";
    borrar.className = "borrar";
    borrar.textContent = "🗑";
    borrar.title = "Borrar partida";
    borrar.setAttribute("aria-label", `Borrar la partida #${p.id}`);
    borrar.addEventListener("click", () => borrarPartida(p.id));
    li.append(b, etiqueta, borrar);
    lista.append(li);
  }
}

async function borrarPartida(id) {
  if (!confirm(`¿Borrar la partida #${id} y su chat? No se puede deshacer.`)) return;
  try {
    await api(`/coach/games/${id}`, { method: "DELETE" });
    await verPartidas();
  } catch (e) { alert(e.message); }
}

// ------------------------------------------------------------------ resultado

const MOTIVOS = {
  checkmate: "jaque mate",
  stalemate: "rey ahogado",
  insufficient_material: "material insuficiente",
  seventyfive_moves: "regla de las 75 jugadas",
  fivefold_repetition: "quíntuple repetición",
  fifty_moves: "regla de las 50 jugadas",
  threefold_repetition: "triple repetición",
  agreement: "tablas acordadas",
};

function veredicto(p) {
  // Quién ganó, en palabras, desde el punto de vista del usuario
  if (p.result === "*") return { corto: { texto: "en juego", clase: "en-juego" } };
  const tablas = p.result === "1/2-1/2";
  const ganoBlanco = p.result === "1-0";
  const gane = !tablas && ganoBlanco === (p.color === "white");
  const quien = tablas ? "Tablas" : ganoBlanco ? "Ganan las blancas" : "Ganan las negras";
  const tuyo = tablas ? "Tablas" : gane ? "Ganaste" : "Perdiste";
  return {
    corto: { texto: tuyo.toLowerCase(), clase: tablas ? "tablas" : gane ? "ganada" : "perdida" },
    resultado: `${p.result} · ${quien}`,
    detalle: `${MOTIVOS[p.termination] || p.termination || ""} · ${tuyo}`,
    clase: tablas ? "tablas" : gane ? "ganada" : "perdida",
  };
}

// ------------------------------------------------------------------ partida

async function abrirPartida(id) {
  estado.partida = await api(`/coach/games/${id}`);
  estado.seleccion = null;
  estado.revision = null;
  history.replaceState(null, "", `/?partida=${id}`);
  mostrar("vista-partida");
  $("error-partida").textContent = "";
  // Partida recién creada con negras: se ve cómo el coach hace su primera jugada.
  const nueva = estado.partida.moves.length === 1 && estado.partida.moves[0].by === "coach";
  estado.vista = nueva ? 0 : estado.partida.moves.length;
  pintar();
  if (nueva) await animarPendientes();
}

// ------------------------------------------------------------------ tablero

const FEN_INICIAL = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";
const DURACION = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 420;

function filasFEN(fen) {
  // "rnbqkbnr/pppppppp/8/..." → 8 filas (de la 8 a la 1) de 8 casillas ("" = vacía)
  return fen.split(" ")[0].split("/").map((fila) => {
    const casillas = [];
    for (const c of fila) {
      if (/\d/.test(c)) for (let i = 0; i < Number(c); i++) casillas.push("");
      else casillas.push(c);
    }
    return casillas;
  });
}

const nombreCasilla = (col, fila) => "abcdefgh"[col] + (8 - fila);
const piezaEn = (fen, casilla) => filasFEN(fen)[8 - Number(casilla[1])]["abcdefgh".indexOf(casilla[0])];
const esMia = (pieza) => pieza && (pieza === pieza.toUpperCase()) === (estado.partida.color === "white");
const casillaEl = (nombre) => $("tablero").querySelector(`[data-casilla="${nombre}"]`);

// Posición que se está enseñando: la de la jugada `estado.vista` (puede ir por detrás de la
// partida mientras se animan las últimas jugadas).
function fenVista() {
  const n = plyMostrada();
  return n === 0 ? FEN_INICIAL : estado.partida.moves[n - 1].fen_after;
}

// Jugadas que se ven en el tablero: las de la revisión o, si no, las ya animadas
const plyMostrada = () => (estado.revision ?? estado.vista);

function pintarTablero(fen, ultimaUci) {
  const filas = filasFEN(fen);
  const blancas = estado.partida.color === "white";
  const tablero = $("tablero");
  tablero.replaceChildren();
  for (let i = 0; i < 8; i++) {
    for (let j = 0; j < 8; j++) {
      const fila = blancas ? i : 7 - i;
      const col = blancas ? j : 7 - j;
      const nombre = nombreCasilla(col, fila);
      const pieza = filas[fila][col];
      const c = document.createElement("button");
      c.type = "button";
      c.className = `casilla ${(fila + col) % 2 ? "oscura" : "clara"}`;
      if (ultimaUci && (ultimaUci.slice(0, 2) === nombre || ultimaUci.slice(2, 4) === nombre)) c.classList.add("ultima");
      c.dataset.casilla = nombre;
      c.setAttribute("aria-label", `${nombre}${pieza ? " " + pieza : ""}`);
      if (pieza) {
        const s = document.createElement("span");
        s.className = `pieza ${pieza === pieza.toUpperCase() ? "pieza-blanca" : "pieza-negra"}`;
        s.textContent = PIEZAS[pieza];
        c.append(s);
      }
      tablero.append(c);
    }
  }
}

function puedeMover() {
  const p = estado.partida;
  return !estado.ocupado && !estado.animando && !estado.eligiendo && estado.revision === null && p.your_turn && p.result === "*" && estado.vista === p.moves.length;
}

function destinos(desde) {
  return estado.partida.legal_moves.filter((u) => u.startsWith(desde)).map((u) => u.slice(2, 4));
}

function seleccionar(casilla) {
  estado.seleccion = casilla;
  for (const c of $("tablero").children) c.classList.remove("origen", "destino", "captura");
  if (!casilla) return;
  casillaEl(casilla).classList.add("origen");
  for (const d of destinos(casilla)) {
    const el = casillaEl(d);
    el.classList.add(el.querySelector(".pieza") || esPasoCaptura(casilla, d) ? "captura" : "destino");
  }
}

function esPasoCaptura(desde, hasta) {
  // Captura al paso: un peón que cambia de columna hacia una casilla vacía
  const pieza = piezaEn(estado.partida.fen, desde);
  return pieza && pieza.toLowerCase() === "p" && desde[0] !== hasta[0];
}

const NOMBRES_PIEZA = { q: "dama", r: "torre", b: "alfil", n: "caballo" };

// Jugada UCI para ir de `desde` a `hasta`. Si el peón corona, pregunta con qué pieza
// (null si se cancela).
async function uciDe(desde, hasta) {
  const opciones = estado.partida.legal_moves.filter((u) => u.slice(0, 4) === desde + hasta);
  if (opciones.length <= 1) return opciones[0] || null;
  const letra = await elegirCoronacion(hasta, opciones.map((u) => u[4]));
  return letra ? desde + hasta + letra : null;
}

function elegirCoronacion(hasta, letras) {
  // Columna con las piezas posibles sobre la casilla de coronación (siempre en el borde de
  // arriba: el tablero se ve desde tu lado). Clic fuera o Escape cancela.
  estado.eligiendo = true;
  const tablero = $("tablero");
  const caja = tablero.getBoundingClientRect();
  const r = casillaEl(hasta).getBoundingClientRect();
  const blancas = estado.partida.color === "white";
  const velo = document.createElement("div");
  velo.className = "velo";
  const menu = document.createElement("div");
  menu.className = "coronacion";
  menu.setAttribute("role", "dialog");
  menu.setAttribute("aria-label", "Elige la pieza de la coronación");
  Object.assign(menu.style, { left: `${r.left - caja.left}px`, top: `${r.top - caja.top}px`, width: `${r.width}px` });
  return new Promise((resolver) => {
    const tecla = (ev) => { if (ev.key === "Escape") cerrar(null); };
    const cerrar = (letra) => {
      velo.remove();
      menu.remove();
      document.removeEventListener("keydown", tecla);
      estado.eligiendo = false;
      resolver(letra);
    };
    for (const l of ["q", "r", "b", "n"].filter((x) => letras.includes(x))) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = `opcion pieza ${blancas ? "pieza-blanca" : "pieza-negra"}`;
      b.textContent = PIEZAS[blancas ? l.toUpperCase() : l];
      b.title = NOMBRES_PIEZA[l];
      b.setAttribute("aria-label", NOMBRES_PIEZA[l]);
      b.style.height = `${r.height}px`;
      b.addEventListener("click", () => cerrar(l));
      menu.append(b);
    }
    // Que el tablero no trate estos clics como jugadas
    velo.addEventListener("pointerdown", (ev) => { ev.stopPropagation(); cerrar(null); });
    menu.addEventListener("pointerdown", (ev) => ev.stopPropagation());
    document.addEventListener("keydown", tecla);
    tablero.append(velo, menu);
    menu.querySelector("button").focus();
  });
}

// --- clic (también con teclado: Enter/Espacio sobre una casilla) y arrastre con ratón o dedo

async function pulsarCasilla(casilla) {
  if (!puedeMover()) return;
  const pieza = piezaEn(estado.partida.fen, casilla);
  if (estado.seleccion && destinos(estado.seleccion).includes(casilla)) {
    const desde = estado.seleccion;
    seleccionar(null);
    const uci = await uciDe(desde, casilla);
    if (uci) jugar(uci);
    return;
  }
  if (casilla === estado.seleccion) return seleccionar(null);  // segundo clic: se suelta
  seleccionar(esMia(pieza) && destinos(casilla).length ? casilla : null);
}

const arrastre = { activo: false, desde: null, x: 0, y: 0, fantasma: null, original: null, yaElegida: false };

function alPulsar(ev) {
  const c = ev.target.closest(".casilla");
  if (!c || ev.button > 0) return;
  const casilla = c.dataset.casilla;
  const pieza = piezaEn(estado.partida.fen, casilla);
  if (!puedeMover() || !esMia(pieza) || !destinos(casilla).length) {
    arrastre.desde = null;
    if (estado.seleccion) arrastre.desde = "clic:" + casilla;  // clic en un destino o fuera
    return;
  }
  ev.preventDefault();
  Object.assign(arrastre, {
    activo: false, desde: casilla, x: ev.clientX, y: ev.clientY, original: c.querySelector(".pieza"),
    yaElegida: estado.seleccion === casilla,  // si era la elegida y no se arrastra, se suelta
  });
  seleccionar(casilla);
  try {
    $("tablero").setPointerCapture(ev.pointerId);  // el dedo puede salir del tablero sin perder el arrastre
  } catch { /* sin captura, el arrastre funciona igual mientras siga sobre el tablero */ }
}

function alMover(ev) {
  if (!arrastre.desde || arrastre.desde.startsWith("clic:")) return;
  if (!arrastre.activo) {
    if (Math.hypot(ev.clientX - arrastre.x, ev.clientY - arrastre.y) < 5) return;
    arrastre.activo = true;
    const f = arrastre.original.cloneNode(true);
    f.classList.add("fantasma");
    const tam = casillaEl(arrastre.desde).getBoundingClientRect().width;
    f.style.width = f.style.height = `${tam}px`;
    document.body.append(f);
    arrastre.fantasma = f;
    arrastre.original.classList.add("levantada");
  }
  const tam = arrastre.fantasma.offsetWidth;
  arrastre.fantasma.style.transform = `translate(${ev.clientX - tam / 2}px, ${ev.clientY - tam / 2}px)`;
}

async function alSoltar(ev) {
  const desde = arrastre.desde;
  arrastre.desde = null;
  if (!desde) return;
  if (desde.startsWith("clic:")) {
    const c = ev.target.closest && ev.target.closest(".casilla");
    if (c) pulsarCasilla(c.dataset.casilla);
    return;
  }
  if (!arrastre.activo) {
    // Clic sin arrastrar: elige la pieza o, si ya estaba elegida, la suelta
    if (arrastre.yaElegida) seleccionar(null);
    return;
  }
  arrastre.activo = false;
  arrastre.fantasma.remove();
  const bajo = document.elementFromPoint(ev.clientX, ev.clientY);
  const destino = bajo && bajo.closest && bajo.closest("#tablero .casilla");
  const hasta = destino && destino.dataset.casilla;
  if (hasta && destinos(desde).includes(hasta)) {
    // Se deja la pieza donde la soltaste mientras el servidor responde
    arrastre.original.classList.remove("levantada");
    destino.querySelector(".pieza")?.remove();
    destino.append(arrastre.original);
    seleccionar(null);
    const uci = await uciDe(desde, hasta);
    if (uci) {
      sonarJugada(estado.partida.fen, uci);
      jugar(uci, { yaMovida: true });
    }
    else pintar();  // coronación cancelada: el peón vuelve a su casilla
  } else {
    arrastre.original.classList.remove("levantada");  // vuelve a su casilla
  }
}

function cancelarArrastre() {
  if (arrastre.activo) {
    arrastre.fantasma.remove();
    arrastre.original.classList.remove("levantada");  // vuelve a su casilla
  }
  Object.assign(arrastre, { activo: false, desde: null });
}

function alClicDerecho(ev) {
  ev.preventDefault();
  if (estado.eligiendo) return;  // con el menú de coronación abierto, se cancela con clic izquierdo fuera
  cancelarArrastre();
  seleccionar(null);
}

function alClic(ev) {
  // Solo teclado (detail === 0): con ratón o dedo ya lo gestionan los eventos pointer
  const c = ev.target.closest(".casilla");
  if (c && ev.detail === 0) pulsarCasilla(c.dataset.casilla);
}

// --- animación: la pieza se desliza de su casilla a la nueva y la capturada se desvanece

function animar(fenAntes, uci) {
  pintarTablero(fenAntes, null);
  if (!DURACION) return Promise.resolve();
  const desde = uci.slice(0, 2);
  const hasta = uci.slice(2, 4);
  const movimientos = [[desde, hasta]];
  const pieza = piezaEn(fenAntes, desde);
  if (pieza.toLowerCase() === "k" && Math.abs("abcdefgh".indexOf(desde[0]) - "abcdefgh".indexOf(hasta[0])) === 2) {
    const fila = desde[1];
    movimientos.push(hasta[0] === "g" ? ["h" + fila, "f" + fila] : ["a" + fila, "d" + fila]);  // enroque: la torre también
  }
  // Pieza capturada: la del destino o, al paso, la que está al lado
  let capturada = casillaEl(hasta).querySelector(".pieza");
  if (!capturada && pieza.toLowerCase() === "p" && desde[0] !== hasta[0]) {
    capturada = casillaEl(hasta[0] + desde[1]).querySelector(".pieza");
  }
  const caja = $("tablero").getBoundingClientRect();
  const pos = (nombre) => {
    const r = casillaEl(nombre).getBoundingClientRect();
    return { x: r.left - caja.left, y: r.top - caja.top, tam: r.width };
  };
  const fantasmas = movimientos.map(([a, b]) => {
    const original = casillaEl(a).querySelector(".pieza");
    const f = original.cloneNode(true);
    const p0 = pos(a);
    const p1 = pos(b);
    f.classList.add("deslizando");
    Object.assign(f.style, { width: `${p0.tam}px`, height: `${p0.tam}px`, transform: `translate(${p0.x}px, ${p0.y}px)` });
    original.style.visibility = "hidden";
    $("tablero").append(f);
    return { f, destino: `translate(${p1.x}px, ${p1.y}px)` };
  });
  return new Promise((resolver) => {
    requestAnimationFrame(() => requestAnimationFrame(() => {
      for (const { f, destino } of fantasmas) f.style.transform = destino;
      if (capturada) capturada.classList.add("capturada");
      setTimeout(resolver, DURACION + 30);
    }));
  });
}

// ------------------------------------------------------------------ sonido
// Sintetizado con Web Audio: sin archivos que descargar (y sin tocar la CSP). Un "toc" de
// madera al mover (ruido filtrado + un tono grave que cae), más fuerte al capturar, dos notas
// para el jaque y un pequeño acorde al terminar.

const sonido = { ctx: null, activo: localStorage.getItem("sonido") !== "off" };

function ctxAudio() {
  if (!sonido.ctx) sonido.ctx = new (window.AudioContext || window.webkitAudioContext)();
  if (sonido.ctx.state === "suspended") sonido.ctx.resume();
  return sonido.ctx;
}

function golpe({ frecuencia, duracion, volumen, ruido }) {
  const ctx = ctxAudio();
  const t = ctx.currentTime;
  const muestras = Math.floor(ctx.sampleRate * duracion);
  const buf = ctx.createBuffer(1, muestras, ctx.sampleRate);
  const datos = buf.getChannelData(0);
  for (let i = 0; i < muestras; i++) datos[i] = (Math.random() * 2 - 1) * (1 - i / muestras) ** 4;
  const fuente = ctx.createBufferSource();
  fuente.buffer = buf;
  const filtro = ctx.createBiquadFilter();
  filtro.type = "bandpass";
  filtro.frequency.value = frecuencia * 6;
  const g1 = ctx.createGain();
  g1.gain.value = volumen * ruido;
  fuente.connect(filtro).connect(g1).connect(ctx.destination);
  fuente.start(t);
  const osc = ctx.createOscillator();
  osc.frequency.setValueAtTime(frecuencia, t);
  osc.frequency.exponentialRampToValueAtTime(frecuencia * 0.55, t + duracion);
  const g2 = ctx.createGain();
  g2.gain.setValueAtTime(volumen, t);
  g2.gain.exponentialRampToValueAtTime(0.001, t + duracion);
  osc.connect(g2).connect(ctx.destination);
  osc.start(t);
  osc.stop(t + duracion + 0.02);
}

function notas(frecuencias, duracion, volumen = 0.12) {
  const ctx = ctxAudio();
  frecuencias.forEach((f, i) => {
    const t = ctx.currentTime + i * duracion * 0.8;
    const osc = ctx.createOscillator();
    osc.type = "triangle";
    osc.frequency.value = f;
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(volumen, t + 0.01);
    g.gain.exponentialRampToValueAtTime(0.0001, t + duracion);
    osc.connect(g).connect(ctx.destination);
    osc.start(t);
    osc.stop(t + duracion + 0.02);
  });
}

const SONIDOS = {
  mover: () => golpe({ frecuencia: 230, duracion: 0.08, volumen: 0.35, ruido: 0.5 }),
  capturar: () => golpe({ frecuencia: 150, duracion: 0.13, volumen: 0.55, ruido: 1 }),
  jaque: () => notas([880, 698], 0.11),
  final: () => notas([523, 659, 784], 0.22, 0.1),
};

function sonar(tipo) {
  if (!sonido.activo) return;
  try { SONIDOS[tipo](); } catch { /* sin audio (navegador sin Web Audio): seguimos en silencio */ }
}

function sonarJugada(fenAntes, uci, san = "") {
  const pieza = piezaEn(fenAntes, uci.slice(0, 2));
  const captura = !!piezaEn(fenAntes, uci.slice(2, 4))
    || (pieza && pieza.toLowerCase() === "p" && uci[0] !== uci[2]);  // también al paso
  sonar(captura ? "capturar" : "mover");
  if (san.endsWith("+")) setTimeout(() => sonar("jaque"), 120);
}

function pintarBotonSonido() {
  const b = $("sonido");
  b.textContent = sonido.activo ? "🔊" : "🔇";
  b.title = sonido.activo ? "Silenciar los sonidos" : "Activar los sonidos";
  b.setAttribute("aria-label", b.title);
  b.setAttribute("aria-pressed", String(!sonido.activo));
}

function alternarSonido() {
  sonido.activo = !sonido.activo;
  localStorage.setItem("sonido", sonido.activo ? "on" : "off");
  pintarBotonSonido();
  if (sonido.activo) sonar("mover");
}

async function animarPendientes({ saltarPrimera = false } = {}) {
  const moves = estado.partida.moves;
  estado.animando = true;
  if (saltarPrimera && estado.vista < moves.length) estado.vista += 1;  // la tuya ya se ve donde la soltaste
  while (estado.vista < moves.length) {
    const jugada = moves[estado.vista];
    const antes = fenVista();
    setTimeout(() => sonarJugada(antes, jugada.uci, jugada.san), DURACION);
    await animar(antes, jugada.uci);
    estado.vista += 1;
  }
  estado.animando = false;
  pintar();
  if (estado.partida.result !== "*") setTimeout(() => sonar("final"), 250);
}

function pintar() {
  const p = estado.partida;
  const n = plyMostrada();
  const ultima = n ? p.moves[n - 1].uci : null;
  pintarTablero(fenVista(), ultima);
  if (estado.seleccion && puedeMover()) seleccionar(estado.seleccion);
  else estado.seleccion = null;
  pintarEstado();
  pintarJugadas();
  pintarMensajes();
}

function pintarMarcador() {
  const p = estado.partida;
  const m = $("marcador");
  // El marcador sale cuando termina, y no a mitad de animar la última jugada
  m.hidden = p.result === "*" || estado.animando;
  if (!m.hidden) {
    const v = veredicto(p);
    m.className = `marcador ${v.clase}`;
    $("marcador-resultado").textContent = v.resultado;
    $("marcador-detalle").textContent = v.detalle;
  }
  $("oferta-tablas").hidden = p.draw_offer !== "coach" || p.result !== "*" || estado.animando;
  $("ofrecer-tablas").disabled = p.result !== "*" || estado.ocupado || estado.animando;
}

function pintarEstado() {
  pintarMarcador();
  const p = estado.partida;
  let texto;
  if (p.result !== "*") texto = "Partida terminada";
  else if (estado.ocupado) texto = "El coach está pensando…";
  else texto = p.your_turn ? "Te toca" : "Turno del coach";
  $("estado").textContent = texto;
  // Aviso de revisión, con botón para volver a la partida
  const aviso = $("aviso-revision");
  aviso.hidden = estado.revision === null;
  if (estado.revision !== null) {
    const n = estado.revision;
    $("texto-revision").textContent = n === 0
      ? "Viendo la posición inicial"
      : `Viendo la posición tras ${Math.ceil(n / 2)}.${n % 2 ? "" : ".."} ${p.moves[n - 1].san}`;
  }
  const total = p.moves.length;
  const mostrada = plyMostrada();
  $("nav-inicio").disabled = $("nav-atras").disabled = mostrada === 0 || estado.animando;
  $("nav-adelante").disabled = $("nav-final").disabled = estado.revision === null || estado.animando;
  if (total === 0) $("nav-inicio").disabled = $("nav-atras").disabled = true;
  for (const f of ["form-jugada", "form-pregunta"]) {
    for (const el of $(f).elements) el.disabled = estado.ocupado;
  }
}

function pintarJugadas() {
  const ol = $("jugadas");
  ol.replaceChildren();
  const moves = estado.partida.moves;
  for (let i = 0; i < moves.length; i += 2) {
    const li = document.createElement("li");
    for (const m of moves.slice(i, i + 2)) {
      const s = document.createElement("button");
      s.type = "button";
      s.className = `jugada ${m.by === "user" ? "mia" : "rival"} et-${m.label}`;
      if (estado.revision === m.ply) s.classList.add("activa");
      s.addEventListener("click", () => irA(m.ply));
      s.textContent = m.san;
      if (m.by === "user" && m.label !== "buena") {
        s.title = `${ETIQUETAS[m.label]}${m.best_move ? " · mejor " + m.best_move : ""}`;
      }
      li.append(s);
    }
    ol.append(li);
  }
  if (estado.partida.result !== "*" && !estado.animando) {
    const fin = document.createElement("li");
    fin.className = "resultado-final";
    fin.textContent = estado.partida.result;
    ol.append(fin);
  }
  const activa = ol.querySelector(".activa");
  if (activa) activa.scrollIntoView({ block: "nearest" });
  else ol.scrollTop = ol.scrollHeight;
}

// --- revisar jugadas pasadas: clic en la lista, botones ⏮ ◀ ▶ ⏭ o flechas ← →

function irA(n) {
  // n = jugadas hechas en la posición a mostrar (0 = inicial). La última = volver a la partida.
  if (estado.animando || !estado.partida) return;
  const total = estado.partida.moves.length;
  n = Math.max(0, Math.min(n, total));
  estado.revision = n === total ? null : n;
  estado.seleccion = null;
  pintar();
}

const pasos = {
  "nav-inicio": () => irA(0),
  "nav-atras": () => irA(plyMostrada() - 1),
  "nav-adelante": () => irA(plyMostrada() + 1),
  "nav-final": () => irA(Infinity),
};

function textoConNegritas(contenedor, texto) {
  // Solo **negritas**, construidas con nodos de texto: nada del LLM se interpreta como HTML.
  texto.split(/(\*\*[^*]+\*\*)/).forEach((trozo) => {
    if (trozo.startsWith("**") && trozo.endsWith("**")) {
      const b = document.createElement("strong");
      b.textContent = trozo.slice(2, -2);
      contenedor.append(b);
    } else if (trozo) {
      contenedor.append(document.createTextNode(trozo));
    }
  });
}

function fuente(texto) {
  // "[n] título — https://… (licencia)": enlace solo si la URL es https
  const div = document.createElement("div");
  div.className = "fuente";
  const m = texto.match(/^(\[\d+\]) (.+?) — (https:\/\/\S+) \((.+)\)$/);
  if (!m) { div.textContent = texto; return div; }
  const a = document.createElement("a");
  a.href = m[3];
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  a.textContent = m[2];
  div.append(`${m[1]} `, a, ` (${m[4]})`);
  return div;
}

function burbuja(rol, texto, { fuentes = [], nota = null, modelo = null } = {}) {
  const div = document.createElement("div");
  div.className = `mensaje ${rol}`;
  textoConNegritas(div, texto);
  for (const f of fuentes) div.append(fuente(f));
  if (modelo) {
    const m = document.createElement("div");
    m.className = "modelo";
    m.textContent = modelo;
    div.append(m);
  }
  if (nota) {
    const n = document.createElement("div");
    n.className = "nota";
    n.textContent = nota;
    div.append(n);
  }
  return div;
}

function pintarMensajes() {
  const caja = $("mensajes");
  caja.replaceChildren();
  const msgs = estado.partida.messages;
  if (!msgs.length) {
    caja.append(burbuja("coach", "Juega cuando quieras. Si cometes un error te lo comento, y puedes preguntarme lo que quieras sobre la partida."));
  }
  for (const m of msgs) caja.append(burbuja(m.role, m.content, { modelo: m.role === "coach" ? m.model : null }));
  if (estado.extra) caja.append(estado.extra);
  caja.scrollTop = caja.scrollHeight;
}

// ------------------------------------------------------------------ jugar y preguntar

async function turno(ruta, cuerpo, { yaMovida = false } = {}) {
  estado.revision = null;  // al jugar o preguntar, de vuelta a la posición actual
  estado.ocupado = true;
  // Mientras responde, la pregunta ya se ve en el chat
  estado.extra = cuerpo.question ? burbuja("user", cuerpo.question) : null;
  $("error-partida").textContent = "";
  if (yaMovida) pintarEstado(); else pintar();
  let animarDespues = false;
  try {
    const t = await api(`/coach/games/${estado.partida.id}/${ruta}`, { method: "POST", json: cuerpo });
    estado.partida = await api(`/coach/games/${estado.partida.id}`);
    animarDespues = estado.vista < estado.partida.moves.length;
    estado.extra = null;  // la pregunta ya viene en el chat guardado
    if (t.note) estado.extra = burbuja("coach", t.note);
    // Las fuentes no se guardan en el chat: se enseñan bajo la última respuesta.
    if (t.answer && t.sources.length) {
      const ultima = estado.partida.messages.at(-1);
      estado.partida.messages = estado.partida.messages.slice(0, -1);
      estado.extra = burbuja("coach", ultima.content, { fuentes: t.sources, modelo: ultima.model });
    }
  } catch (e) {
    estado.extra = null;
    $("error-partida").textContent = e.message;
  } finally {
    estado.ocupado = false;
  }
  if (animarDespues) {
    pintarJugadas();
    pintarMensajes();
    await animarPendientes({ saltarPrimera: yaMovida });
  } else {
    pintar();  // también deshace una jugada arrastrada que el servidor rechazó
  }
}

async function ofrecerTablas() {
  const p = estado.partida;
  if (p.result !== "*" || estado.ocupado) return;
  const aceptando = p.draw_offer === "coach";
  if (!aceptando && !confirm("¿Ofrecer tablas al coach?")) return;
  estado.ocupado = true;
  estado.revision = null;
  pintar();
  try {
    const r = await api(`/coach/games/${p.id}/draw`, { method: "POST" });
    estado.partida = await api(`/coach/games/${p.id}`);
    estado.extra = burbuja("coach", r.message, { nota: aceptando ? null : (r.accepted ? "Partida terminada en tablas" : "Oferta rechazada") });
    if (r.accepted) sonar("final");
  } catch (e) {
    $("error-partida").textContent = e.message;
  } finally {
    estado.ocupado = false;
    pintar();
  }
}

async function rechazarTablas() {
  try {
    await api(`/coach/games/${estado.partida.id}/draw/decline`, { method: "POST" });
    estado.partida.draw_offer = null;
    pintar();
  } catch (e) { $("error-partida").textContent = e.message; }
}

const jugar = (move, opciones) => turno("move", { move }, opciones);
const preguntar = (question) => turno("ask", { question });

// ------------------------------------------------------------------ eventos

$("tab-entrar").addEventListener("click", () => pestana(false));
$("tab-registro").addEventListener("click", () => pestana(true));
$("form-entrar").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const f = new FormData(ev.target);
  try { await entrar(f.get("username"), f.get("password")); } catch (e) { $("error-acceso").textContent = e.message; }
});
$("form-registro").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const f = Object.fromEntries(new FormData(ev.target));
  try {
    await api("/auth/register", { method: "POST", json: f });
    await entrar(f.username, f.password);
  } catch (e) { $("error-acceso").textContent = e.message; }
});
$("form-nueva").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const f = new FormData(ev.target);
  try {
    const p = await api("/coach/games", { method: "POST", json: { color: f.get("color"), level: Number(f.get("level")) } });
    await abrirPartida(p.id);
  } catch (e) { alert(e.message); }
});
$("form-nueva").elements.level.addEventListener("input", (ev) => { $("nivel-valor").textContent = ev.target.value; });
$("form-jugada").addEventListener("submit", (ev) => {
  ev.preventDefault();
  const v = ev.target.elements.move.value.trim();
  if (v) { ev.target.reset(); jugar(v); }
});
$("form-pregunta").addEventListener("submit", (ev) => {
  ev.preventDefault();
  const v = ev.target.elements.question.value.trim();
  if (v) { ev.target.reset(); preguntar(v); }
});
$("btn-partidas").addEventListener("click", () => verPartidas().catch((e) => alert(e.message)));
$("btn-salir").addEventListener("click", salir);
for (const [id, accion] of Object.entries(pasos)) $(id).addEventListener("click", accion);
$("volver-partida").addEventListener("click", () => irA(Infinity));
$("ofrecer-tablas").addEventListener("click", ofrecerTablas);
$("sonido").addEventListener("click", alternarSonido);
pintarBotonSonido();
// Los navegadores solo dejan sonar audio tras un gesto del usuario: se prepara en el primero
document.addEventListener("pointerdown", () => { if (sonido.activo) ctxAudio(); }, { once: true });
$("aceptar-tablas").addEventListener("click", ofrecerTablas);
$("rechazar-tablas").addEventListener("click", rechazarTablas);
document.addEventListener("keydown", (ev) => {
  // Flechas para revisar, salvo si se está escribiendo en un campo
  if ($("vista-partida").hidden || ev.target.closest("input, textarea, select")) return;
  if (ev.key === "Escape" && estado.seleccion && !estado.eligiendo) {
    cancelarArrastre();
    seleccionar(null);
  } else if (ev.key === "ArrowLeft") pasos["nav-atras"]();
  else if (ev.key === "ArrowRight") pasos["nav-adelante"]();
  else if (ev.key === "Home") pasos["nav-inicio"]();
  else if (ev.key === "End") pasos["nav-final"]();
  else return;
  ev.preventDefault();
});
$("tablero").addEventListener("pointerdown", alPulsar);
$("tablero").addEventListener("pointermove", alMover);
$("tablero").addEventListener("pointerup", alSoltar);
$("tablero").addEventListener("pointercancel", alSoltar);
$("tablero").addEventListener("click", alClic);
$("tablero").addEventListener("contextmenu", alClicDerecho);

iniciar();
