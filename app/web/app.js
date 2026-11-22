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
  seleccion: null, vista: 0, ocupado: false, animando: false, extra: null,
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
    const b = document.createElement("button");
    b.type = "button";
    b.className = "enlace";
    const fecha = new Date(p.updated_at).toLocaleString();
    const resultado = p.result === "*" ? "en juego" : `${p.result} (${p.termination || ""})`;
    b.textContent = `#${p.id} · ${p.color === "white" ? "blancas" : "negras"} · nivel ${p.level} · ${p.move_count} jugadas · ${resultado} · ${fecha}`;
    b.addEventListener("click", () => abrirPartida(p.id));
    li.append(b);
    lista.append(li);
  }
}

// ------------------------------------------------------------------ partida

async function abrirPartida(id) {
  estado.partida = await api(`/coach/games/${id}`);
  estado.seleccion = null;
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
  const moves = estado.partida.moves;
  return estado.vista === 0 ? FEN_INICIAL : moves[estado.vista - 1].fen_after;
}

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
  return !estado.ocupado && !estado.animando && p.your_turn && p.result === "*" && estado.vista === p.moves.length;
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

function uciDe(desde, hasta) {
  // Si hay varias (coronación), dama; las otras se pueden escribir a mano (e7e8n).
  const opciones = estado.partida.legal_moves.filter((u) => u.slice(0, 4) === desde + hasta);
  return opciones.find((u) => u.endsWith("q")) || opciones[0] || null;
}

// --- clic (también con teclado: Enter/Espacio sobre una casilla) y arrastre con ratón o dedo

function pulsarCasilla(casilla) {
  if (!puedeMover()) return;
  const pieza = piezaEn(estado.partida.fen, casilla);
  if (estado.seleccion && destinos(estado.seleccion).includes(casilla)) {
    const uci = uciDe(estado.seleccion, casilla);
    seleccionar(null);
    return jugar(uci);
  }
  seleccionar(esMia(pieza) && destinos(casilla).length ? casilla : null);
}

const arrastre = { activo: false, desde: null, x: 0, y: 0, fantasma: null, original: null };

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
  Object.assign(arrastre, { activo: false, desde: casilla, x: ev.clientX, y: ev.clientY, original: c.querySelector(".pieza") });
  seleccionar(casilla);
  $("tablero").setPointerCapture(ev.pointerId);
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

function alSoltar(ev) {
  const desde = arrastre.desde;
  arrastre.desde = null;
  if (!desde) return;
  if (desde.startsWith("clic:")) {
    const c = ev.target.closest && ev.target.closest(".casilla");
    if (c) pulsarCasilla(c.dataset.casilla);
    return;
  }
  if (!arrastre.activo) return;  // fue un clic sobre una pieza propia: queda seleccionada
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
    jugar(uciDe(desde, hasta), { yaMovida: true });
  } else {
    arrastre.original.classList.remove("levantada");  // vuelve a su casilla
  }
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

async function animarPendientes({ saltarPrimera = false } = {}) {
  const moves = estado.partida.moves;
  estado.animando = true;
  if (saltarPrimera && estado.vista < moves.length) estado.vista += 1;  // la tuya ya se ve donde la soltaste
  while (estado.vista < moves.length) {
    await animar(fenVista(), moves[estado.vista].uci);
    estado.vista += 1;
  }
  estado.animando = false;
  pintar();
}

function pintar() {
  const p = estado.partida;
  const ultima = estado.vista ? p.moves[estado.vista - 1].uci : null;
  pintarTablero(fenVista(), ultima);
  if (estado.seleccion && puedeMover()) seleccionar(estado.seleccion);
  else estado.seleccion = null;
  pintarEstado();
  pintarJugadas();
  pintarMensajes();
}

function pintarEstado() {
  const p = estado.partida;
  let texto;
  if (p.result !== "*") texto = `Partida terminada: ${p.result} (${p.termination})`;
  else if (estado.ocupado) texto = "El coach está pensando…";
  else texto = p.your_turn ? "Te toca" : "Turno del coach";
  $("estado").textContent = texto;
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
      const s = document.createElement("span");
      s.className = `jugada ${m.by === "user" ? "mia" : "rival"} et-${m.label}`;
      s.textContent = m.san;
      if (m.by === "user" && m.label !== "buena") {
        s.title = `${ETIQUETAS[m.label]}${m.best_move ? " · mejor " + m.best_move : ""}`;
      }
      li.append(s);
    }
    ol.append(li);
  }
  ol.scrollTop = ol.scrollHeight;
}

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
$("tablero").addEventListener("pointerdown", alPulsar);
$("tablero").addEventListener("pointermove", alMover);
$("tablero").addEventListener("pointerup", alSoltar);
$("tablero").addEventListener("pointercancel", alSoltar);
$("tablero").addEventListener("click", alClic);

iniciar();
