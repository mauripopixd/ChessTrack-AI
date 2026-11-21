"""Tablero + jugada como tensor para la red (Etapa 4, PR 2). Solo numpy: sin PyTorch.

Una jugada → array uint8 de forma (26, 8, 8):

    0-5    mis piezas ANTES   (peón, caballo, alfil, torre, dama, rey)
    6-11   piezas del rival ANTES
    12-17  mis piezas DESPUÉS
    18-23  piezas del rival DESPUÉS
    24     casilla de origen
    25     casilla de destino

"Mis" = de quien mueve. El tablero se ve siempre desde su lado (si mueven negras se
gira verticalmente): la red aprende una sola vez "dejar una pieza colgando", en vez de
una vez para cada color.

uint8 y no float32: 457.000 jugadas × 26 × 64 ocupan 760 MB en vez de 3 GB.
"""

from collections.abc import Sequence

import chess
import numpy as np

N_PLANOS = 26


def _orientar(casilla: chess.Square, quien_mueve: chess.Color) -> tuple[int, int]:
    if quien_mueve == chess.BLACK:
        casilla = chess.square_mirror(casilla)
    return chess.square_rank(casilla), chess.square_file(casilla)


def _piezas(board: chess.Board, quien_mueve: chess.Color, salida: np.ndarray, base: int) -> None:
    for casilla, pieza in board.piece_map().items():
        plano = base + (0 if pieza.color == quien_mueve else 6) + pieza.piece_type - 1
        fila, columna = _orientar(casilla, quien_mueve)
        salida[plano, fila, columna] = 1


def encode_move(board: chess.Board, move: chess.Move) -> np.ndarray:
    """Tensor (26, 8, 8) de `move` jugada en `board` (que no se modifica)."""
    quien = board.turn
    x = np.zeros((N_PLANOS, 8, 8), dtype=np.uint8)
    _piezas(board, quien, x, base=0)
    board.push(move)
    try:
        _piezas(board, quien, x, base=12)
    finally:
        board.pop()
    x[24][_orientar(move.from_square, quien)] = 1
    x[25][_orientar(move.to_square, quien)] = 1
    return x


def encode_game(moves_uci: Sequence[str], initial_fen: str = chess.STARTING_FEN) -> np.ndarray:
    """Tensores de todas las jugadas de una partida: (n_jugadas, 26, 8, 8)."""
    board = chess.Board(initial_fen)
    salida = np.zeros((len(moves_uci), N_PLANOS, 8, 8), dtype=np.uint8)
    for i, uci in enumerate(moves_uci):
        move = chess.Move.from_uci(uci)
        salida[i] = encode_move(board, move)
        board.push(move)
    return salida
