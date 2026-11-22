"""Evaluación de jugadas con Stockfish (Etapa 3; la base de las etiquetas de la Etapa 4).

Para cada jugada se compara la posición ANTES (con la mejor jugada posible, según el
motor) y DESPUÉS de la jugada real:

- Evaluación en **centipeones** (cp, 100 = un peón de ventaja) desde el punto de vista
  de blancas. Los mates se convierten a ±MATE_CP para poder hacer cuentas.
- **cp_loss**: centipeones que pierde quien mueve. Es la medida clásica (ACPL = media por partida).
- **Probabilidad de ganar** (0-100) con una sigmoide sobre los cp. Perder 100 cp con la
  partida igualada importa mucho; perderlos ganando por +900 casi nada. La caída de esa
  probabilidad decide la etiqueta.
"""

import math
import os
import shutil
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

import chess
import chess.engine

MATE_CP = 10_000  # un mate "vale" más que cualquier ventaja material
CP_LOSS_MAX = 1_000  # tope para que un mate fallado no domine las medias

# Caída de probabilidad de ganar (puntos de 0-100) a partir de la cual una jugada es…
UMBRALES = (("error_grave", 20.0), ("error", 10.0), ("imprecision", 5.0))
ETIQUETAS = ("buena", "imprecision", "error", "error_grave")

# Constante de la sigmoide que usa Lichess para pasar de cp a probabilidad de ganar.
_K = 0.00368208


_VALOR = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 100}


def _mayor_en_peligro(board: chess.Board, color: bool) -> int:
    """Valor de la pieza de `color` más valiosa que el rival puede ganar: atacada y sin
    defensa, o atacada por una pieza de menos valor."""
    peor = 0
    for casilla, pieza in board.piece_map().items():
        if pieza.color != color or pieza.piece_type == chess.KING:
            continue
        atacantes = board.attackers(not color, casilla)
        if not atacantes:
            continue
        valor = _VALOR[pieza.piece_type]
        menor = min(_VALOR[board.piece_type_at(a)] for a in atacantes)
        if not board.attackers(color, casilla) or menor < valor:
            peor = max(peor, valor)
    return peor


def es_brillante(
    board: chess.Board, move: chess.Move, eval_antes_mover: int, win_antes: float, win_despues: float,
    win_drop: float,
) -> bool:  # fmt: skip
    """Jugada brillante (!!): la mejor o casi (no pierde probabilidad) y además SACRIFICA
    material (deja en peligro una pieza de al menos 3 que antes no lo estaba y que vale más que
    lo que captura), sin que la posición quede peor. Si no hay mate a la vista, tampoco cuenta
    si ya se ganaba de todas formas (> 97 %): ahí cualquier entrega da igual. Con mate a la vista
    sí: es justo el sacrificio de dama que lleva al mate."""
    if win_drop > 2 or win_despues < 50:
        return False
    if abs(eval_antes_mover) < MATE_CP - 100 and win_antes > 97:
        return False
    color = board.turn
    despues = board.copy(stack=False)
    despues.push(move)
    capturada = 1 if board.is_en_passant(move) else _VALOR.get(board.piece_type_at(move.to_square), 0)
    riesgo = _mayor_en_peligro(despues, color)
    return riesgo >= 3 and riesgo > _mayor_en_peligro(board, color) and riesgo > capturada


def win_probability(cp: int) -> float:
    """Probabilidad de ganar (0-100) de quien tiene `cp` centipeones de ventaja.
    0 cp → 50; +300 → ~75; -300 → ~25; ±MATE_CP → ~100/~0."""
    return 50 + 50 * (2 / (1 + math.exp(-_K * cp)) - 1)


def classify(win_drop: float) -> str:
    for etiqueta, umbral in UMBRALES:
        if win_drop >= umbral:
            return etiqueta
    return "buena"


@dataclass(frozen=True, slots=True)
class MoveEval:
    ply: int
    mover: str  # "white" o "black"
    san: str
    uci: str
    best_uci: str | None  # mejor jugada según el motor en la posición previa
    eval_before: int  # cp, punto de vista de blancas
    eval_after: int
    cp_loss: int  # punto de vista de quien mueve, 0..CP_LOSS_MAX
    win_before: float  # punto de vista de quien mueve, 0-100
    win_after: float
    win_drop: float
    label: str
    brilliant: bool = False  # sacrificio que además es la mejor jugada (!!)

    def to_dict(self) -> dict:
        return asdict(self)


def _evaluate(engine: chess.engine.SimpleEngine, board: chess.Board, limit: chess.engine.Limit):
    """(cp desde blancas, mejor jugada). Las posiciones terminadas se evalúan sin el motor."""
    if board.is_checkmate():
        # Le toca al que está mateado: gana el otro.
        return (-MATE_CP if board.turn == chess.WHITE else MATE_CP), None
    if board.is_game_over(claim_draw=False):
        return 0, None  # ahogado, material insuficiente…
    info = engine.analyse(board, limit)
    cp = info["score"].white().score(mate_score=MATE_CP)
    pv = info.get("pv") or [None]
    return cp, (pv[0].uci() if pv[0] else None)


def analyze_moves(
    moves: Sequence[str],
    engine: chess.engine.SimpleEngine,
    limit: chess.engine.Limit,
    initial_fen: str = chess.STARTING_FEN,
) -> list[MoveEval]:
    """Evalúa cada jugada (en UCI). Analiza N+1 posiciones: la evaluación tras una jugada
    es la evaluación previa de la siguiente, así que no se repite trabajo."""
    board = chess.Board(initial_fen)
    eval_antes, mejor = _evaluate(engine, board, limit)
    resultado = []
    for ply, uci in enumerate(moves, start=1):
        move = chess.Move.from_uci(uci)
        mover = chess.WHITE if board.turn == chess.WHITE else chess.BLACK
        san = board.san(move)
        antes_board = board.copy(stack=False)
        board.push(move)
        eval_despues, siguiente_mejor = _evaluate(engine, board, limit)

        signo = 1 if mover == chess.WHITE else -1  # pasar de "blancas" a "quien mueve"
        antes_m, despues_m = signo * eval_antes, signo * eval_despues
        win_antes, win_despues = win_probability(antes_m), win_probability(despues_m)
        caida = max(0.0, win_antes - win_despues)
        resultado.append(
            MoveEval(
                ply=ply,
                mover="white" if mover == chess.WHITE else "black",
                san=san,
                uci=uci,
                best_uci=mejor,
                eval_before=eval_antes,
                eval_after=eval_despues,
                cp_loss=min(CP_LOSS_MAX, max(0, antes_m - despues_m)),
                win_before=round(win_antes, 2),
                win_after=round(win_despues, 2),
                win_drop=round(caida, 2),
                label=classify(caida),
                brilliant=es_brillante(antes_board, move, antes_m, win_antes, win_despues, caida),
            )
        )
        eval_antes, mejor = eval_despues, siguiente_mejor
    return resultado


def find_stockfish() -> str | None:
    """Ruta del ejecutable: STOCKFISH_PATH, el PATH, o donde lo deja `winget` en Windows."""
    if ruta := os.environ.get("STOCKFISH_PATH"):
        return ruta
    if ruta := shutil.which("stockfish"):
        return ruta
    winget = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    encontrados = sorted(winget.glob("Stockfish.Stockfish_*/stockfish/stockfish*.exe"))
    return str(encontrados[-1]) if encontrados else None
