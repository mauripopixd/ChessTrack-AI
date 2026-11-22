"""Cómo habla el coach según lo que sabe de ajedrez el usuario.

El LLM escribe siempre las jugadas en SAN ("dxc4", "Nf3"): así el verificador del grafo puede
comprobarlas. Después, para quien no sabe la notación, ESTE código las traduce a palabras con
python-chess sobre las posiciones de la partida ("el peón de d5 se come el peón de c4"). Pedirle
al LLM que lo hiciera él no sería fiable: podría equivocarse de pieza o de casilla, y aquí no.

Niveles (`CoachGame.conocimiento`):
- "none": no sabe ajedrez. Jugadas solo en palabras, prompt sin jerga.
- "basic": sabe mover las piezas. SAN seguida de las palabras entre paréntesis.
- "advanced": como siempre, solo SAN.
"""

import re

import chess

NIVELES = ("none", "basic", "advanced")

# Lo que se añade al prompt del sistema según el nivel ("advanced": nada, el prompt de siempre)
PROMPT_NIVEL = {
    "none": """

Alumno: NO sabe nada de ajedrez (puede que ni sepa cómo se llaman las piezas ni cómo se mueven).
- Escribe las jugadas en SAN igualmente: el sistema las traduce solo a palabras ("el caballo de g1
  va a f3"). No añadas tú la traducción ni expliques la notación.
- Frases cortas y palabras de todos los días. Nada de jerga (clavada, desarrollo, fianchetto,
  enfilada, ventaja posicional…): di la idea con palabras simples.
- Las casillas se nombran con su letra y su número (c4): están escritas en el borde del tablero.
- Una sola idea por respuesta y práctica: qué pieza está en peligro, qué puede comer, qué cuidar.
  Como mucho 80 palabras.
- Nada de números de evaluación: di "vas mejor", "vas peor" o "está igualado".
- Si pregunta cómo se mueve una pieza o qué es algo (jaque, enroque…), explícalo con sencillez.""",
    "basic": """

Alumno: sabe mover las piezas, pero tiene poca experiencia.
- Escribe las jugadas en SAN: el sistema añade entre paréntesis qué pieza va de dónde a dónde.
- La primera vez que uses un término técnico (clavada, desarrollo, columna abierta…), explícalo
  en pocas palabras.
- Nada de números de evaluación: di quién va mejor y por qué.""",
    "advanced": "",
}

_PIEZA = {
    chess.PAWN: "el peón", chess.KNIGHT: "el caballo", chess.BISHOP: "el alfil",
    chess.ROOK: "la torre", chess.QUEEN: "la dama", chess.KING: "el rey",
}  # fmt: skip
_LETRA = {"N": chess.KNIGHT, "B": chess.BISHOP, "R": chess.ROOK, "Q": chess.QUEEN, "K": chess.KING}


def _sin_articulo(tipo: int) -> str:
    return _PIEZA[tipo].split(" ", 1)[1]


def en_palabras(board: chess.Board, move: chess.Move) -> str:
    """'el peón de d5 se come el peón de c4 y da jaque': la jugada `move` en la posición `board`."""
    pieza = board.piece_at(move.from_square)
    desde, hasta = chess.square_name(move.from_square), chess.square_name(move.to_square)
    if board.is_castling(move):
        corto = chess.square_file(move.to_square) > chess.square_file(move.from_square)
        fila = "1" if pieza.color == chess.WHITE else "8"
        rey, torre = ("g", "f") if corto else ("c", "d")
        texto = f"enroque {'corto' if corto else 'largo'}: el rey va a {rey}{fila} y la torre a {torre}{fila}"
    elif board.is_en_passant(move):
        capturado = chess.square_name(
            chess.square(chess.square_file(move.to_square), chess.square_rank(move.from_square))
        )
        texto = f"el peón de {desde} se come al paso el peón de {capturado} y queda en {hasta}"
    elif capturada := board.piece_at(move.to_square):
        texto = f"{_PIEZA[pieza.piece_type]} de {desde} se come {_PIEZA[capturada.piece_type]} de {hasta}"
    else:
        texto = f"{_PIEZA[pieza.piece_type]} de {desde} va a {hasta}"
    if move.promotion:
        texto += f" y se convierte en {_sin_articulo(move.promotion)}"
    tras = board.copy(stack=False)
    tras.push(move)
    if tras.is_checkmate():
        texto += " y da jaque mate"
    elif tras.is_check():
        texto += " y da jaque"
    return texto


def _san_suelta(san: str) -> str:
    """Traducción sin tablero, cuando la jugada no encaja en ninguna posición de la partida
    (una variante que el LLM escribió de memoria, por ejemplo). Menos precisa, pero legible."""
    jaque = " y da jaque mate" if san.endswith("#") else " y da jaque" if san.endswith("+") else ""
    s = san.rstrip("+#")
    if s.replace("0", "O") in ("O-O", "O-O-O"):
        return ("enroque corto" if s.count("-") == 1 else "enroque largo") + jaque
    corona = ""
    if (m := re.search(r"=?([QRBN])$", s)) and s[0] not in _LETRA:  # coronación de peón ("e8=Q")
        corona = f" y se convierte en {_sin_articulo(_LETRA[m.group(1)])}"
        s = s[: m.start()]
    destino = s[-2:]
    if s[0] in _LETRA:
        pieza = _PIEZA[_LETRA[s[0]]]
        texto = f"{pieza} se come lo que hay en {destino}" if "x" in s else f"{pieza} va a {destino}"
    elif "x" in s:
        texto = f"el peón de la columna {s[0]} se come lo que hay en {destino}"
    else:
        texto = f"el peón va a {destino}"
    return texto + corona + jaque


# Una jugada en SAN, con su número delante si lo lleva ("12.", "12...", "12. Nf3").
_SAN = re.compile(
    r"(?<![\w/\-])(?:(\d+)\.(\.\.)?\s?)?"
    r"(O-O-O|O-O|0-0-0|0-0|[KQRBN][a-h]?[1-8]?x?[a-h][1-8]|[a-h]x[a-h][1-8](?:=?[QRBN])?|[a-h][1-8](?:=?[QRBN])?)"
    r"([+#])?(?![\w\-])"
)
# Un peón que avanza ("e4") se escribe igual que una casilla. Solo se toma como jugada si la
# palabra anterior es de jugar, si lleva número o si va dentro de una línea de jugadas;
# "la casilla e4" o "en e4" se quedan como están.
_ANTES_DE_JUGADA = {
    "jugada", "jugadas", "jugar", "juega", "juegas", "jugaste", "jugó", "jugaría", "jugarías", "jugando",
    "juego", "mueve", "mueves", "moviste", "movió", "avanza", "avanzar", "avanzando", "responde",
    "respondió", "respondería", "responder", "tras", "después", "luego", "seguido", "amenaza", "prepara",
    "preparar", "era", "sería", "fue", "con", "por", "o", "mejor", "contestar", "contesta", "como",
}  # fmt: skip
_SEPARA_LINEA = re.compile(r"^[\s,;→\-–y]*$|^[\s,;]*(y\s+)?(luego|después)?[\s,;]*$")


def _es_peon_que_avanza(san: str) -> bool:
    return bool(re.fullmatch(r"[a-h][1-8](=?[QRBN])?", san))


def _palabra_anterior(texto: str, inicio: int) -> str:
    previo = re.sub(r"[*«»\"'“”(:¿?¡!]", " ", texto[max(0, inicio - 30) : inicio])
    palabras = previo.split()
    return palabras[-1].lower() if palabras else ""


def adaptar(texto: str, board: chess.Board, conocimiento: str) -> str:
    """El texto del coach con sus jugadas en SAN adaptadas al nivel (ver el docstring)."""
    if conocimiento == "advanced" or not texto:
        return texto
    # Posiciones de la partida, de la actual hacia atrás: la jugada puede ser de ahora, la que
    # hizo el usuario hace un momento o la mejor que había entonces.
    posiciones = [board.copy(stack=False)]
    b = board.copy()
    while b.move_stack:
        b.pop()
        posiciones.append(b.copy(stack=False))
    partes, pos, anterior = [], 0, None  # anterior = (posición tras la jugada previa, dónde acabó)
    tras_texto = []  # posiciones tras las jugadas ya nombradas ("si juegas exd5, responde Nxd5")
    for m in _SAN.finditer(texto):
        numero, puntos, san, jaque = m.groups()
        en_linea = anterior is not None and _SEPARA_LINEA.match(texto[anterior[1] : m.start()])
        if _es_peon_que_avanza(san) and not (
            numero or en_linea or _palabra_anterior(texto, m.start()) in _ANTES_DE_JUGADA
        ):
            continue  # es una casilla
        candidatas = ([anterior[0]] if en_linea else []) + posiciones[:1] + tras_texto[::-1] + posiciones[1:]
        if numero:  # "12...Nf3": la posición de esa jugada en esta partida, si se llegó a jugar
            ply = (int(numero) - 1) * 2 + (1 if puntos else 0)
            if ply < len(posiciones):
                candidatas.insert(0, posiciones[len(posiciones) - 1 - ply])
        palabras, anterior = None, None
        for c in candidatas:
            try:
                move = c.parse_san(san.replace("0", "O"))
            except ValueError:
                continue
            palabras = en_palabras(c, move)
            tras = c.copy(stack=False)
            tras.push(move)
            anterior = (tras, m.end())
            tras_texto.append(tras)
            break
        if palabras is None:
            palabras = _san_suelta(san + (jaque or ""))
        if conocimiento == "basic":
            nuevo = f"{m.group(0)} ({palabras})"
        else:
            entre_marcas = texto[m.start() - 1 : m.start()] in ("*", "«", '"', "(", "“")
            nuevo = palabras if entre_marcas else f"«{palabras}»"
        hueco = texto[pos : m.start()]
        if conocimiento == "none" and en_linea and not hueco.strip():
            hueco = "; después, "  # "1.e4 e5 2.Nf3": que se lea como una secuencia
        partes += [hueco, nuevo]
        pos = m.end()
    partes.append(texto[pos:])
    return "".join(partes)
