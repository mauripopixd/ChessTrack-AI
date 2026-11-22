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

const estado = { token: localStorage.getItem("token"), usuario: null, partida: null, origen: null, ocupado: false };

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
  estado.origen = null;
  history.replaceState(null, "", `/?partida=${id}`);
  mostrar("vista-partida");
  $("error-partida").textContent = "";
  pintar();
}

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

function pintar() {
  const p = estado.partida;
  const filas = filasFEN(p.fen);
  const blancas = p.color === "white";
  const ultima = p.moves.at(-1);
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
      if (pieza) c.classList.add(pieza === pieza.toUpperCase() ? "pieza-blanca" : "pieza-negra");
      if (ultima && (ultima.uci.slice(0, 2) === nombre || ultima.uci.slice(2, 4) === nombre)) c.classList.add("ultima");
      if (estado.origen === nombre) c.classList.add("origen");
      c.textContent = pieza ? PIEZAS[pieza] : "";
      c.setAttribute("aria-label", `${nombre}${pieza ? " " + pieza : ""}`);
      c.dataset.casilla = nombre;
      c.addEventListener("click", () => clicCasilla(nombre, pieza));
      tablero.append(c);
    }
  }
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

function clicCasilla(nombre, pieza) {
  const p = estado.partida;
  if (estado.ocupado || !p.your_turn || p.result !== "*") return;
  const mia = pieza && (pieza === pieza.toUpperCase()) === (p.color === "white");
  if (!estado.origen || mia) {
    estado.origen = mia ? nombre : null;
    return pintar();
  }
  const desde = estado.origen;
  estado.origen = null;
  let uci = desde + nombre;
  const filas = filasFEN(p.fen);
  const movida = filas[8 - Number(desde[1])]["abcdefgh".indexOf(desde[0])];
  if ((movida === "P" && nombre[1] === "8") || (movida === "p" && nombre[1] === "1")) uci += "q";  // corona dama
  jugar(uci);
}

async function turno(ruta, cuerpo) {
  estado.ocupado = true;
  // Mientras responde, la pregunta ya se ve en el chat
  estado.extra = cuerpo.question ? burbuja("user", cuerpo.question) : null;
  $("error-partida").textContent = "";
  pintar();
  try {
    const t = await api(`/coach/games/${estado.partida.id}/${ruta}`, { method: "POST", json: cuerpo });
    estado.partida = await api(`/coach/games/${estado.partida.id}`);
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
    pintar();
  }
}

const jugar = (move) => turno("move", { move });
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

iniciar();
