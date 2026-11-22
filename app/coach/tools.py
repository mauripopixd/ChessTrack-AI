"""Herramientas que el LLM del coach puede llamar.

Todas leen la partida (CoachGame) por closure: el LLM NUNCA les pasa una FEN ni jugadas.
Probado: al copiar una FEN como argumento, gpt-oss la estropeó ("…b KQ? Wait"). Así el
modelo solo decide QUÉ consultar; los datos salen exactos del tablero.

Devuelven texto breve en español: es lo que el modelo lee para explicar.
"""

import threading
from collections.abc import Callable
from contextlib import AbstractContextManager, contextmanager

import chess
import chess.engine
from langchain_core.tools import BaseTool, tool

from app.analysis import MATE_CP, win_probability
from app.coach.game import CoachGame, MoveReport
from app.ml.features import move_features

MotorFn = Callable[[], AbstractContextManager[chess.engine.SimpleEngine]]
PIEZA = {
    chess.PAWN: "peón",
    chess.KNIGHT: "caballo",
    chess.BISHOP: "alfil",
    chess.ROOK: "torre",
    chess.QUEEN: "dama",
    chess.KING: "rey",
}
VALOR = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 100}
ETIQUETA = {"buena": "buena", "imprecision": "imprecisión", "error": "error", "error_grave": "error grave"}


def _color(c: bool) -> str:
    return "blancas" if c == chess.WHITE else "negras"


def _eval_texto(cp_blancas: int, perspectiva: bool) -> str:
    """Evaluación legible desde el punto de vista de `perspectiva` (el usuario)."""
    cp = cp_blancas if perspectiva == chess.WHITE else -cp_blancas
    if abs(cp) >= MATE_CP - 100:
        return "tú das mate pronto" if cp > 0 else "el rival da mate pronto"
    prob = win_probability(cp)
    if abs(cp) < 50:
        quien = "igualada"
    elif abs(cp) < 150:
        quien = "ventaja ligera " + ("tuya" if cp > 0 else "del rival")
    elif abs(cp) < 400:
        quien = "ventaja clara " + ("tuya" if cp > 0 else "del rival")
    else:
        quien = "ventaja decisiva " + ("tuya" if cp > 0 else "del rival")
    return f"{cp / 100:+.1f} peones para ti ({quien}; probabilidad de ganar {prob:.0f} %)"


def describir(board: chess.Board, move: chess.Move) -> str:
    """'exd5 (peón de e4 captura peón en d5, jaque)': lo que el LLM necesita para no inventar."""
    pieza = board.piece_at(move.from_square)
    san = board.san(move)
    if board.is_castling(move):
        return f"{san} (enroque {'corto' if chess.square_file(move.to_square) == 6 else 'largo'})"
    desde, hasta = chess.square_name(move.from_square), chess.square_name(move.to_square)
    texto = f"{PIEZA[pieza.piece_type]} de {desde} "
    if board.is_en_passant(move):
        texto += f"captura al paso en {hasta}"
    elif capturada := board.piece_at(move.to_square):
        texto += f"captura {PIEZA[capturada.piece_type]} en {hasta}"
    else:
        texto += f"va a {hasta}"
    if move.promotion:
        texto += f" y corona {PIEZA[move.promotion]}"
    if board.gives_check(move):
        texto += ", jaque" if not san.endswith("#") else ", jaque mate"
    return f"{san} ({texto})"


def describir_linea(board: chess.Board, sans: list[str], n: int = 3) -> str:
    """Las primeras `n` jugadas de una línea en SAN, cada una descrita."""
    b, partes = board.copy(), []
    for san in sans[:n]:
        try:
            m = b.parse_san(san)
        except ValueError:
            break
        partes.append(describir(b, m))
        b.push(m)
    return "; ".join(partes) or "-"


def colgando(board: chess.Board, color: bool) -> list[str]:
    """Piezas de `color` que el rival puede ganar: atacadas sin defensa o por una pieza de menos valor."""
    res = []
    for casilla, pieza in board.piece_map().items():
        if pieza.color != color or pieza.piece_type == chess.KING:
            continue
        atacantes = board.attackers(not color, casilla)
        if not atacantes:
            continue
        menor = min(VALOR[board.piece_type_at(a)] for a in atacantes)
        if not board.attackers(color, casilla):
            res.append(f"{PIEZA[pieza.piece_type]} en {chess.square_name(casilla)} (sin defensa)")
        elif menor < VALOR[pieza.piece_type]:
            res.append(
                f"{PIEZA[pieza.piece_type]} en {chess.square_name(casilla)} (la ataca algo de menos valor)"
            )
    return res


def _tablero_antes(game: CoachGame, r: MoveReport) -> chess.Board:
    """Posición justo antes de la jugada `r` (para calcular sus variables)."""
    b = game.board.root()  # posición inicial de la partida, sin jugadas
    for m in game.board.move_stack[: r.ply - 1]:
        b.push(m)
    return b


def _san_linea_tools(board: chess.Board, moves: list[chess.Move]) -> list[str]:
    b, sans = board.copy(), []
    for m in moves:
        sans.append(b.san(m))
        b.push(m)
    return sans


def _en_serie(motor: MotorFn) -> MotorFn:
    """ToolNode ejecuta en paralelo las herramientas que el LLM pide a la vez. Si comparten un
    mismo Stockfish (el CLI), una orden cancelaría la otra: se usan de una en una."""
    candado = threading.Lock()

    @contextmanager
    def motor_en_serie():
        with candado, motor() as eng:
            yield eng

    return motor_en_serie


def _jugadas_numeradas(game: CoachGame) -> str:
    b = game.board.root()
    partes = []
    for i, m in enumerate(game.board.move_stack):
        if i % 2 == 0:
            partes.append(f"{i // 2 + 1}.")
        partes.append(b.san(m))
        b.push(m)
    return " ".join(partes) or "(ninguna)"


def make_tools(game: CoachGame, motor: MotorFn, classifier=None, retriever=None) -> list[BaseTool]:
    """Las herramientas del LLM; `tools[i].func` sigue siendo la función Python normal."""
    usuario = game.user_color
    motor = _en_serie(motor)

    def analisis_ultima_jugada() -> str:
        r = game.last_user_report
        if r is None:
            return "Todavía no has hecho ninguna jugada."
        antes = _tablero_antes(game, r)
        jugada = chess.Move.from_uci(r.uci)
        f = move_features(antes, jugada, r.ply)
        despues = antes.copy()
        despues.push(jugada)
        texto = (
            f"Tu jugada {describir(antes, jugada)}, jugada {(r.ply + 1) // 2}: {ETIQUETA[r.label]}.\n"
            f"Antes: {_eval_texto(r.eval_before, usuario)}. Después: {_eval_texto(r.eval_after, usuario)}.\n"
        )
        if r.best_san and r.best_san != r.san:
            texto += f"Mejor era: {describir_linea(antes, r.best_line or [r.best_san], 1)}.\n"
        if r.label != "buena" and not despues.is_game_over():
            with motor() as eng:
                info = eng.analyse(despues, chess.engine.Limit(depth=12))
            pv = _san_linea_tools(despues, (info.get("pv") or [])[:3])
            if pv:
                texto += f"Respuesta más fuerte del rival: {describir_linea(despues, pv)}.\n"
        motivos = colgando(despues, usuario)
        if f["rival_mate_in_1"]:
            motivos.insert(0, "permite mate en una jugada")
        if f["free_capture_missed"]:
            motivos.append("no aprovechó una pieza rival sin defensa")
        texto += "Tras tu jugada queda en peligro: " + ("; ".join(motivos) if motivos else "nada")
        if classifier is not None:
            prob = classifier.error_probs([f])[0]
            texto += (
                f"\nEl clasificador de errores (sin motor) le da {prob:.0%} de probabilidad de ser error."
            )
        return texto

    @tool
    def estado_partida() -> str:
        """Estado de la partida: jugadas hechas, turno, material, nivel del coach y resultado."""
        b = game.board
        mat = {c: sum(v * len(b.pieces(p, c)) for p, v in zip(range(1, 6), (1, 3, 3, 5, 9), strict=True))
               for c in (chess.WHITE, chess.BLACK)}  # fmt: skip
        diff = mat[usuario] - mat[not usuario]
        texto = (
            f"Juegas con {_color(usuario)}; el coach con {_color(not usuario)} (nivel {game.level}/20).\n"
            f"Jugadas: {_jugadas_numeradas(game)}\n"
        )
        if b.move_stack:
            previa = b.copy()
            ultima = previa.pop()
            quien = "tú" if previa.turn == usuario else "el coach"
            texto += f"Última jugada ({quien}): {describir(previa, ultima)}\n"
        peligro = colgando(b, usuario)
        ganables = colgando(b, not usuario)
        ultimo = game.reports[-1] if game.reports else None
        if ultimo and ultimo.ply == b.ply():  # la evaluación guardada es de esta misma posición
            texto += f"Evaluación actual (Stockfish): {_eval_texto(ultimo.eval_after, usuario)}\n"
        texto += f"Piezas del coach que puedes ganar: {'; '.join(ganables) if ganables else 'ninguna'}\n"
        texto += (
            f"Turno: {'tuyo' if game.user_to_move else 'del coach' if not b.is_game_over() else 'ninguno'}"
            f"{' · jaque' if b.is_check() else ''}\n"
            f"Material: {'+' if diff > 0 else ''}{diff} para ti\n"
            f"Tus piezas en peligro: {'; '.join(peligro) if peligro else 'ninguna'}\n"
            f"Resultado: {game.result() or 'en juego'}"
        )
        return texto

    @tool
    def evaluar_posicion() -> str:
        """Evalúa la posición actual con Stockfish: quién va mejor y las 3 mejores jugadas."""
        b = game.board
        if b.is_game_over():
            return f"La partida terminó: {game.result()}"
        with motor() as eng:
            infos = eng.analyse(b, chess.engine.Limit(depth=14), multipv=3)
        lineas = []
        for i, info in enumerate(infos, start=1):
            pv = info.get("pv") or []
            copia, sans = b.copy(), []
            for m in pv[:5]:
                sans.append(copia.san(m))
                copia.push(m)
            cp = info["score"].white().score(mate_score=MATE_CP)
            lineas.append(f"{i}. {' '.join(sans)} → {_eval_texto(cp, usuario)}")
        turno = "Te toca a ti" if b.turn == usuario else "Le toca al coach"
        return f"{turno} ({_color(b.turn)}). Mejores continuaciones:\n" + "\n".join(lineas)

    @tool
    def analizar_mi_ultima_jugada() -> str:
        """Última jugada del usuario: calidad, qué dejó en peligro, la mejor alternativa y la
        respuesta más fuerte del rival."""
        return analisis_ultima_jugada()

    @tool
    def explicar_jugada_del_coach() -> str:
        """Qué hizo y qué amenaza la última jugada del coach (el motor)."""
        r = game.last_coach_report
        if r is None:
            return "El coach todavía no ha jugado."
        b = game.board
        previa = _tablero_antes(game, r)
        texto = (
            f"El coach jugó {describir(previa, chess.Move.from_uci(r.uci))}. "
            f"Evaluación ahora: {_eval_texto(r.eval_after, usuario)}.\n"
        )
        if not b.is_game_over():
            with motor() as eng:
                info = eng.analyse(b, chess.engine.Limit(depth=12))
            pv = _san_linea_tools(b, (info.get("pv") or [])[:2])
            if pv:
                texto += f"Tu mejor respuesta ahora: {describir_linea(b, pv, 1)}.\n"
        amenazas = colgando(b, usuario)
        texto += "Tus piezas en peligro: " + ("; ".join(amenazas) if amenazas else "ninguna")
        if b.is_check():
            texto += "\nEstás en jaque."
        return texto

    @tool
    def mis_errores() -> str:
        """Todas las imprecisiones y errores del usuario en la partida, del peor al menos grave."""
        malas = [r for r in game.reports if r.by == "user" and r.label != "buena"]
        if not malas:
            return "Ninguna imprecisión ni error por ahora: todas tus jugadas fueron buenas."
        malas.sort(key=lambda r: r.win_drop, reverse=True)
        return "Tus jugadas peores, de más a menos grave (caída de tu probabilidad de ganar):\n" + "\n".join(
            f"- Jugada {(r.ply + 1) // 2}. {r.san}: {ETIQUETA[r.label]}, −{r.win_drop:.0f} puntos "
            f"(de {_eval_texto(r.eval_before, usuario)} a {_eval_texto(r.eval_after, usuario)}); "
            f"mejor era {r.best_san or '-'}"
            for r in malas[:6]
        )

    @tool
    def buscar_teoria(consulta: str = "") -> str:
        """Busca teoría de aperturas (Wikibooks y Lichess) para citarla con [n] y su enlace.
        Sin consulta, busca la apertura de esta partida por sus primeras jugadas."""
        if retriever is None:
            return "La teoría de aperturas no está disponible ahora."
        if not consulta.strip():
            primeras = _jugadas_numeradas(game).split()[:15]
            consulta = "opening " + " ".join(primeras)
        hits = retriever.search(consulta, k=4)
        if not hits:
            return "No encontré teoría sobre eso."
        return "\n\n".join(
            f"[{i}] {h.title} — {h.url} ({h.license})\n{h.text[:600]}" for i, h in enumerate(hits, start=1)
        )

    return [
        estado_partida,
        evaluar_posicion,
        analizar_mi_ultima_jugada,
        explicar_jugada_del_coach,
        mis_errores,
        buscar_teoria,
    ]
