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
const ETIQUETAS = {
  brillante: "brillante", buena: "buena", imprecision: "imprecisión", error: "error", error_grave: "error grave",
};
// La "etiqueta" que se enseña: brillante (!!) manda sobre buena
const calidad = (m) => (m.brilliant ? "brillante" : m.label);
const $ = (id) => document.getElementById(id);

const estado = {
  token: localStorage.getItem("token"), usuario: null, partida: null,
  seleccion: null, premove: null, vista: 0, revision: null, ocupado: false, animando: false, extra: null,
};

// ------------------------------------------------------------------ API

async function api(ruta, { method = "GET", json, form, multipart } = {}) {
  const headers = {};
  let body;
  if (estado.token) headers.Authorization = `Bearer ${estado.token}`;
  if (json !== undefined) { headers["Content-Type"] = "application/json"; body = JSON.stringify(json); }
  if (form !== undefined) body = new URLSearchParams(form);
  if (multipart !== undefined) body = multipart;  // FormData: el navegador pone el Content-Type
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
  for (const v of ["vista-acceso", "vista-partidas", "vista-partida", "vista-analisis"]) $(v).hidden = v !== vista;
  $("nav-usuario").hidden = vista === "vista-acceso";
}

async function iniciar() {
  if (!estado.token) return mostrar("vista-acceso");
  try {
    estado.usuario = await api("/users/me");
    $("nombre-usuario").textContent = estado.usuario.username;
    const params = new URLSearchParams(location.search);
    const id = Number(params.get("partida"));
    const pgn = Number(params.get("analisis"));
    if (id) await abrirPartida(id);
    else if (pgn) await abrirAnalisis(pgn);
    else await verPartidas();
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
  await listarPgn();
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
  resignation: "abandono",
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
  estado.premove = null;
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
const claseMia = () => (estado.partida.color === "white" ? "pieza-blanca" : "pieza-negra");
const piezaMiaVisible = (casilla) => !!casillaEl(casilla)?.querySelector(`.pieza.${claseMia()}`);

// Elegir una pieza se puede siempre que la partida siga y no se esté revisando: también en el
// turno del coach. Sus casillas posibles salen cuando te toca (antes no se saben).
function puedeElegir() {
  const p = estado.partida;
  return p && p.result === "*" && estado.revision === null && !estado.eligiendo;
}
const casillaEl = (nombre) => $("tablero").querySelector(`[data-casilla="${nombre}"]`);

// Posición que se está enseñando: la de la jugada `estado.vista` (puede ir por detrás de la
// partida mientras se animan las últimas jugadas).
function fenVista() {
  const n = plyMostrada();
  return n === 0 ? FEN_INICIAL : estado.partida.moves[n - 1].fen_after;
}

// Jugadas que se ven en el tablero: las de la revisión o, si no, las ya animadas
const plyMostrada = () => (estado.revision ?? estado.vista);

// Insignia de la calidad de la jugada, sobre su casilla de destino (como en chess.com)
const INSIGNIAS = { brillante: "!!", buena: "✓", imprecision: "?!", error: "?", error_grave: "??" };

function pintarTablero(fen, ultimaUci, {
  el = $("tablero"), blancas = estado.partida.color === "white", etiqueta = null,
} = {}) {
  const filas = filasFEN(fen);
  const tablero = el;
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
      if (etiqueta && ultimaUci && ultimaUci.slice(2, 4) === nombre && INSIGNIAS[etiqueta]) {
        const i = document.createElement("span");
        i.className = `insignia et-${etiqueta}`;
        i.textContent = INSIGNIAS[etiqueta];
        i.title = ETIQUETAS[etiqueta];
        c.append(i);
        c.setAttribute("aria-label", `${c.getAttribute("aria-label")}, jugada ${ETIQUETAS[etiqueta]}`);
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
  if (!puedeMover()) return;  // turno del coach: solo queda resaltada
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
  if (!puedeMover()) {
    // Turno del coach: elegir pieza y, con una elegida, marcar la premove
    if (!puedeElegir()) return;
    if (casilla === estado.seleccion) return seleccionar(null);
    if (estado.seleccion && !piezaMiaVisible(casilla)) return fijarPremove(estado.seleccion, casilla);
    if (piezaMiaVisible(casilla)) seleccionar(casilla);
    return;
  }
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
  const premove = !puedeMover();
  if (premove && !(puedeElegir() && piezaMiaVisible(casilla))) {
    arrastre.desde = puedeElegir() ? "clic:" + casilla : null;  // se resuelve al soltar
    return;
  }
  if (!premove && (!esMia(pieza) || !destinos(casilla).length)) {
    arrastre.desde = null;
    if (estado.seleccion) arrastre.desde = "clic:" + casilla;  // clic en un destino o fuera
    return;
  }
  ev.preventDefault();
  Object.assign(arrastre, {
    activo: false, desde: casilla, x: ev.clientX, y: ev.clientY, original: c.querySelector(".pieza"),
    yaElegida: estado.seleccion === casilla,  // si era la elegida y no se arrastra, se suelta
    premove,
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
  if (arrastre.premove) {
    arrastre.original.classList.remove("levantada");  // la pieza no se mueve hasta tu turno
    if (hasta && hasta !== desde) fijarPremove(desde, hasta);
    return;
  }
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

// --- premove: tu jugada marcada durante el turno del coach, que se hace sola al llegar el tuyo

function fijarPremove(desde, hasta) {
  estado.premove = { desde, hasta };
  seleccionar(null);
  marcarPremove();
}

function marcarPremove() {
  for (const c of $("tablero").children) c.classList.remove("premove");
  if (!estado.premove) return;
  casillaEl(estado.premove.desde)?.classList.add("premove");
  casillaEl(estado.premove.hasta)?.classList.add("premove");
}

function cancelarPremove() {
  estado.premove = null;
  marcarPremove();
}

function ejecutarPremove() {
  // Se llama al terminar de animar la jugada del coach: si sigue siendo legal, se juega
  const pm = estado.premove;
  estado.premove = null;
  marcarPremove();
  if (!pm || !puedeMover()) return;
  const opciones = estado.partida.legal_moves.filter((u) => u.slice(0, 4) === pm.desde + pm.hasta);
  const uci = opciones.find((u) => u.endsWith("q")) || opciones[0];  // coronando, dama (como en Lichess)
  if (!uci) {
    $("error-partida").textContent = `La premove ${pm.desde}-${pm.hasta} ya no era legal y se canceló.`;
    return;
  }
  sonarJugada(estado.partida.fen, uci);
  jugar(uci);
}

function alClicDerecho(ev) {
  ev.preventDefault();
  if (estado.eligiendo) return;  // con el menú de coronación abierto, se cancela con clic izquierdo fuera
  cancelarArrastre();
  seleccionar(null);
  cancelarPremove();
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
  pintarTablero(fenVista(), ultima, { etiqueta: n ? calidad(p.moves[n - 1]) : null });
  // La pieza elegida sigue elegida si sigue ahí (si el coach la capturó, se suelta)
  if (estado.seleccion && puedeElegir() && piezaMiaVisible(estado.seleccion)) seleccionar(estado.seleccion);
  else estado.seleccion = null;
  marcarPremove();
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
  $("rendirse").disabled = p.result !== "*" || estado.ocupado || estado.animando;
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
      s.className = `jugada ${m.by === "user" ? "mia" : "rival"} et-${calidad(m)}`;
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
  if (estado.premove) {
    if (estado.partida.result !== "*") cancelarPremove();
    else ejecutarPremove();
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

async function nuevaPartida(color) {
  // Revancha desde el marcador: mismo nivel del coach, el color que elijas
  for (const id of ["nueva-blancas", "nueva-negras"]) $(id).disabled = true;
  try {
    const p = await api("/coach/games", { method: "POST", json: { color, level: estado.partida.level } });
    estado.extra = null;
    await abrirPartida(p.id);
  } catch (e) {
    $("error-partida").textContent = e.message;
  } finally {
    for (const id of ["nueva-blancas", "nueva-negras"]) $(id).disabled = false;
  }
}

async function rendirse() {
  const p = estado.partida;
  if (p.result !== "*" || estado.ocupado) return;
  if (!confirm("¿Seguro que te rindes? La partida terminará y la gana el coach.")) return;
  estado.ocupado = true;
  try {
    estado.partida = await api(`/coach/games/${p.id}/resign`, { method: "POST" });
    estado.revision = null;
    estado.extra = burbuja("coach", "Buena partida. Si quieres, revisa las jugadas o empieza otra.");
    sonar("final");
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

// ------------------------------------------------------------------ partidas PGN y su análisis
// Tus partidas de chess.com, Lichess… (un .pgn con una o varias): se suben con POST /games y
// se analizan con Stockfish y el clasificador (POST /games/{id}/analysis, Etapas 1 y 4).

const analisis = { id: null, juego: null, jugadas: [], datos: null, ply: 0, fenInicial: FEN_INICIAL };

async function subirPgn(ev) {
  ev.preventDefault();
  const f = ev.target;
  const archivo = f.elements.file.files[0];
  if (!archivo) return;
  const cuerpo = new FormData();
  cuerpo.append("file", archivo);
  const jugador = f.elements.player.value.trim();
  if (jugador) cuerpo.append("player", jugador);
  const boton = f.querySelector("button[type=submit]");
  boton.disabled = true;
  $("resultado-pgn").textContent = "Subiendo…";
  try {
    const r = await api("/games", { method: "POST", multipart: cuerpo });
    const partes = [`${r.created.length} nueva${r.created.length === 1 ? "" : "s"}`];
    if (r.duplicates.length) partes.push(`${r.duplicates.length} ya estaba${r.duplicates.length === 1 ? "" : "n"}`);
    if (r.errors.length) partes.push(`${r.errors.length} con errores`);
    $("resultado-pgn").textContent = partes.join(" · ");
    f.reset();
    await listarPgn();
  } catch (e) {
    $("resultado-pgn").textContent = e.message;
  } finally {
    boton.disabled = false;
  }
}

async function listarPgn() {
  const pagina = await api("/games?limit=50");
  const lista = $("lista-pgn");
  lista.replaceChildren();
  $("sin-pgn").hidden = pagina.items.length > 0;
  for (const g of pagina.items) {
    const li = document.createElement("li");
    li.className = "fila-partida";
    const b = document.createElement("button");
    b.type = "button";
    b.className = "enlace";
    const fecha = g.played_at ? new Date(g.played_at).toLocaleDateString() : "sin fecha";
    const tu = g.user_color ? ` · tú con ${g.user_color === "white" ? "blancas" : "negras"}` : "";
    b.textContent = `${g.white || "?"} – ${g.black || "?"} · ${g.result} · ${fecha} · ${Math.ceil(g.move_count / 2)} jugadas${tu}`;
    b.title = "Analizar con Stockfish";
    b.addEventListener("click", () => abrirAnalisis(g.id));
    const borrar = document.createElement("button");
    borrar.type = "button";
    borrar.className = "borrar";
    borrar.textContent = "🗑";
    borrar.setAttribute("aria-label", `Borrar la partida ${g.white} – ${g.black}`);
    borrar.addEventListener("click", async () => {
      if (!confirm("¿Borrar esta partida y su análisis?")) return;
      try { await api(`/games/${g.id}`, { method: "DELETE" }); await listarPgn(); } catch (e) { alert(e.message); }
    });
    li.append(b, borrar);
    lista.append(li);
  }
}

async function abrirAnalisis(id) {
  mostrar("vista-analisis");
  history.replaceState(null, "", `/?analisis=${id}`);
  Object.assign(analisis, { id, juego: null, jugadas: [], datos: null, ply: 0 });
  $("titulo-analisis").textContent = "Analizando con Stockfish… (unos segundos)";
  $("tablero-analisis").replaceChildren();
  $("resumen-analisis").replaceChildren();
  $("jugadas-analisis").replaceChildren();
  $("detalle-jugada").textContent = "";
  try {
    const [juego, jugadas] = await Promise.all([api(`/games/${id}`), api(`/games/${id}/moves`)]);
    // Partidas que empiezan desde una posición ([FEN "..."] en el PGN, p. ej. un problema)
    const fen = juego.pgn.match(/\[FEN "([^"]+)"\]/);
    Object.assign(analisis, { juego, jugadas, fenInicial: fen ? fen[1] : FEN_INICIAL });
    // Si ya estaba analizada, el servidor responde al momento con lo guardado
    analisis.datos = await api(`/games/${id}/analysis`, { method: "POST" });
    $("titulo-analisis").textContent = `${juego.white || "?"} – ${juego.black || "?"} · ${juego.result}`;
    pintarResumen();
    pintarAnalisis();
  } catch (e) {
    $("titulo-analisis").textContent = `No se pudo analizar: ${e.message}`;
  }
}

const evalTexto = (cp) => {
  if (Math.abs(cp) >= 9000) return cp > 0 ? "mate para las blancas" : "mate para las negras";
  return `${cp >= 0 ? "+" : ""}${(cp / 100).toFixed(1)}`;
};

function irAnalisis(ply) {
  if (!analisis.datos) return;
  analisis.ply = Math.max(0, Math.min(ply, analisis.jugadas.length));
  pintarAnalisis();
}

function pintarAnalisis() {
  const { juego, jugadas, datos, ply } = analisis;
  const fen = ply === 0 ? analisis.fenInicial : jugadas[ply - 1].fen_after;
  pintarTablero(fen, ply ? jugadas[ply - 1].uci : null, {
    el: $("tablero-analisis"),
    blancas: juego.user_color !== "black",
    etiqueta: ply ? calidad(datos.moves[ply - 1]) : null,
  });
  const detalle = $("detalle-jugada");
  if (ply === 0) {
    detalle.textContent = "Posición inicial. Usa ◀ ▶, las flechas o un clic en una jugada.";
  } else {
    const m = datos.moves[ply - 1];
    let t = `${m.move_number}${m.mover === "white" ? "." : "..."} ${m.san}: ${ETIQUETAS[calidad(m)]}`;
    if (m.brilliant) t += " (sacrificio que es la mejor jugada)";
    t += ` · evaluación ${evalTexto(m.eval_after)} (antes ${evalTexto(m.eval_before)})`;
    if (m.label !== "buena" && m.best_move) t += ` · mejor era ${m.best_move}`;
    if (m.error_prob !== null) t += ` · el clasificador le da ${Math.round(m.error_prob * 100)} % de ser error`;
    detalle.textContent = t;
  }
  const ol = $("jugadas-analisis");
  ol.replaceChildren();
  for (let i = 0; i < datos.moves.length; i += 2) {
    const li = document.createElement("li");
    for (const m of datos.moves.slice(i, i + 2)) {
      const b = document.createElement("button");
      b.type = "button";
      // Las tuyas con su etiqueta; si no se sabe tu color, todas
      const tuya = m.is_user !== false;
      b.className = `jugada ${tuya ? "mia" : "rival"} et-${calidad(m)}`;
      if (m.ply === ply) b.classList.add("activa");
      b.textContent = m.san;
      b.addEventListener("click", () => irAnalisis(m.ply));
      li.append(b);
    }
    ol.append(li);
  }
  ol.querySelector(".activa")?.scrollIntoView({ block: "nearest" });
}

function pintarResumen() {
  const { summary, model } = analisis.datos;
  const caja = $("resumen-analisis");
  caja.replaceChildren();
  const quien = summary.user_color
    ? `Tus jugadas (${summary.user_color === "white" ? "blancas" : "negras"})`
    : "Todas las jugadas (no se sabe con qué color jugaste: indica tu nombre al subir el PGN)";
  const p = document.createElement("p");
  p.className = "sub";
  p.textContent = `${quien}: ${summary.moves_analyzed} · pérdida media ${summary.acpl ?? "-"} centipeones`;
  const etiquetas = document.createElement("p");
  etiquetas.textContent = Object.entries(summary.labels)
    .map(([k, n]) => `${ETIQUETAS[k]}: ${n}`).join(" · ");
  caja.append(p, etiquetas);
  const brillantes = analisis.datos.moves.filter((m) => m.brilliant && m.is_user !== false);
  if (brillantes.length) {
    const b = document.createElement("p");
    b.className = "brillantes";
    b.textContent = `Jugadas brillantes (!!): ${brillantes.map((m) => `${m.move_number}. ${m.san}`).join(", ")}`;
    caja.append(b);
  }
  if (summary.errors.length) {
    const titulo = document.createElement("p");
    titulo.textContent = "Errores (clic para verlos en el tablero):";
    const ul = document.createElement("ul");
    ul.className = "lista";
    for (const e of summary.errors) {
      const li = document.createElement("li");
      const b = document.createElement("button");
      b.type = "button";
      b.className = `enlace et-${e.label}`;
      b.textContent = `${e.move_number}. ${e.san}: ${ETIQUETAS[e.label]}${e.best_move ? ` (mejor ${e.best_move})` : ""}`;
      b.addEventListener("click", () => irAnalisis(e.ply));
      li.append(b);
      ul.append(li);
    }
    caja.append(titulo, ul);
  } else {
    const ok = document.createElement("p");
    ok.textContent = "Sin errores: ¡bien jugada!";
    caja.append(ok);
  }
  if (model) {
    const m = document.createElement("p");
    m.className = "sub";
    m.textContent = `Clasificador (Etapa 4): marcó ${model.model_flags} jugadas; ${model.both} coinciden con los errores de Stockfish.`;
    caja.append(m);
  }
}

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
$("form-pgn").addEventListener("submit", subirPgn);
$("an-inicio").addEventListener("click", () => irAnalisis(0));
$("an-atras").addEventListener("click", () => irAnalisis(analisis.ply - 1));
$("an-adelante").addEventListener("click", () => irAnalisis(analisis.ply + 1));
$("an-final").addEventListener("click", () => irAnalisis(Infinity));
for (const [id, accion] of Object.entries(pasos)) $(id).addEventListener("click", accion);
$("volver-partida").addEventListener("click", () => irA(Infinity));
$("ofrecer-tablas").addEventListener("click", ofrecerTablas);
$("rendirse").addEventListener("click", rendirse);
$("sonido").addEventListener("click", alternarSonido);
$("nueva-blancas").addEventListener("click", () => nuevaPartida("white"));
$("nueva-negras").addEventListener("click", () => nuevaPartida("black"));
pintarBotonSonido();
// Los navegadores solo dejan sonar audio tras un gesto del usuario: se prepara en el primero
document.addEventListener("pointerdown", () => { if (sonido.activo) ctxAudio(); }, { once: true });
$("aceptar-tablas").addEventListener("click", ofrecerTablas);
$("rechazar-tablas").addEventListener("click", rechazarTablas);
document.addEventListener("keydown", (ev) => {
  // Flechas para revisar, salvo si se está escribiendo en un campo
  if (ev.target.closest("input, textarea, select")) return;
  if (!$("vista-analisis").hidden) {
    const ir = { ArrowLeft: -1, ArrowRight: 1 }[ev.key];
    if (ir) irAnalisis(analisis.ply + ir);
    else if (ev.key === "Home") irAnalisis(0);
    else if (ev.key === "End") irAnalisis(Infinity);
    else return;
    ev.preventDefault();
    return;
  }
  if ($("vista-partida").hidden) return;
  if (ev.key === "Escape" && (estado.seleccion || estado.premove) && !estado.eligiendo) {
    cancelarArrastre();
    seleccionar(null);
    cancelarPremove();
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
