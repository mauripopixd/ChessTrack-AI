"""Codificación del tablero para la red: forma, orientación y contenido."""

import chess
import numpy as np

from app.ml.board_tensor import N_PLANOS, encode_game, encode_move

PEON, CABALLO, REY = 0, 1, 5  # índices de plano dentro de cada bloque de 6


def test_forma_y_tipo():
    x = encode_move(chess.Board(), chess.Move.from_uci("e2e4"))
    assert x.shape == (N_PLANOS, 8, 8) and x.dtype == np.uint8


def test_posicion_inicial_32_piezas_antes_y_despues():
    x = encode_move(chess.Board(), chess.Move.from_uci("e2e4"))
    assert x[0:12].sum() == 32 and x[12:24].sum() == 32
    assert x[0:6].sum() == 16 and x[6:12].sum() == 16  # mías / del rival


def test_origen_y_destino():
    x = encode_move(chess.Board(), chess.Move.from_uci("e2e4"))
    assert x[24, 1, 4] == 1 and x[24].sum() == 1  # e2 = fila 1, columna 4
    assert x[25, 3, 4] == 1 and x[25].sum() == 1  # e4
    assert x[PEON, 1, 4] == 1 and x[12 + PEON, 1, 4] == 0 and x[12 + PEON, 3, 4] == 1


def test_negras_se_ven_desde_su_lado():
    # Tras 1. e4, negras juegan 1... e5: desde su lado es "e2→e4" visto desde abajo.
    board = chess.Board()
    board.push_uci("e2e4")
    x_negras = encode_move(board, chess.Move.from_uci("e7e5"))
    x_blancas = encode_move(chess.Board(), chess.Move.from_uci("e2e4"))
    assert np.array_equal(x_negras[24], x_blancas[24]) and np.array_equal(x_negras[25], x_blancas[25])
    assert x_negras[REY, 0, 4] == 1  # mi rey (negro) abajo, en "e1"
    assert x_negras[6 + PEON, 4, 4] == 1  # el peón blanco de e4, girado, cae en "e5" (fila 4)


def test_captura_desaparece_la_pieza_rival():
    board = chess.Board("4k3/8/8/4n3/8/8/4R3/4K3 w - - 0 1")
    x = encode_move(board, chess.Move.from_uci("e2e5"))
    assert x[6 + CABALLO].sum() == 1 and x[18 + CABALLO].sum() == 0


def test_no_modifica_el_tablero():
    board = chess.Board()
    encode_move(board, chess.Move.from_uci("g1f3"))
    assert board.fen() == chess.STARTING_FEN


def test_encode_game():
    x = encode_game(["e2e4", "e7e5", "g1f3"])
    assert x.shape == (3, N_PLANOS, 8, 8)
    # La jugada 3 (blancas) ve la posición tras 1. e4 e5: 32 piezas, peón negro en e5.
    assert x[2, 0:12].sum() == 32 and x[2, 6 + PEON, 4, 4] == 1
