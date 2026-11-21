"""Variables del clasificador: casos de ajedrez conocidos."""

import chess
import pytest

from app.ml.features import FEATURES, game_features, move_features


def tras(*jugadas: str) -> chess.Board:
    board = chess.Board()
    for uci in jugadas:
        board.push_uci(uci)
    return board


def test_todas_las_variables_y_en_orden():
    f = move_features(chess.Board(), chess.Move.from_uci("e2e4"), ply=1)
    assert list(f) == FEATURES


def test_no_modifica_el_tablero():
    board = tras("e2e4", "e7e5")
    fen = board.fen()
    move_features(board, chess.Move.from_uci("g1f3"), ply=3)
    assert board.fen() == fen


def test_posicion_inicial():
    f = move_features(chess.Board(), chess.Move.from_uci("e2e4"), ply=1)
    assert f["legal_moves"] == 20
    assert f["material_mover"] == f["material_rival"] == 39
    assert f["material_diff"] == 0 and f["mover_is_white"] == 1
    assert f["hanging_mine_after"] == 0 and f["rival_mate_in_1"] == 0


def test_dama_colgada():
    # 1. e4 e5 2. Qh5 Nc6 3. Qxe5+?? Nxe5: la dama queda atacada por el caballo sin defensa.
    board = tras("e2e4", "e7e5", "d1h5", "b8c6")
    f = move_features(board, chess.Move.from_uci("h5e5"), ply=5)
    assert f["is_capture"] == 1 and f["captured_value"] == 1 and f["is_check"] == 1
    assert f["moved_piece_hanging"] == 1
    assert f["hanging_mine_after_max"] == 9


def test_atacada_por_pieza_menor_cuenta_aunque_este_defendida():
    # La torre blanca de g2 está defendida (por la de g1) pero la ataca el alfil negro de d5:
    # negras ganan calidad. Mueven negras, así que es una pieza rival "regalada".
    board = chess.Board("4k3/8/8/3b4/8/8/6R1/4K1R1 b - - 0 1")
    f = move_features(board, chess.Move.from_uci("e8e7"), ply=2)
    assert f["hanging_theirs_before_max"] == 5


def test_permitir_mate_en_1():
    # 1. f3 e5 2. g4?? permite Qh4#.
    board = tras("f2f3", "e7e5")
    f = move_features(board, chess.Move.from_uci("g2g4"), ply=3)
    assert f["rival_mate_in_1"] == 1
    sano = move_features(board, chess.Move.from_uci("e2e4"), ply=3)
    assert sano["rival_mate_in_1"] == 0


def test_captura_gratis_no_aprovechada():
    # Negras dejan el caballo en e5 sin defensa; blancas no lo toman.
    board = chess.Board("4k3/8/8/4n3/8/8/4R3/4K3 w - - 0 1")
    f = move_features(board, chess.Move.from_uci("e1d1"), ply=1)
    assert f["hanging_theirs_before_max"] == 3 and f["free_capture_missed"] == 1
    tomarlo = move_features(board, chess.Move.from_uci("e2e5"), ply=1)
    assert tomarlo["free_capture_missed"] == 0 and tomarlo["captured_value"] == 3


def test_captura_al_paso_cuenta_como_captura():
    board = chess.Board("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1")
    f = move_features(board, chess.Move.from_uci("e5d6"), ply=1)
    assert f["is_capture"] == 1 and f["captured_value"] == 1


def test_enroque_y_coronacion():
    enroque = move_features(chess.Board("4k3/8/8/8/8/8/8/4K2R w K - 0 1"), chess.Move.from_uci("e1g1"), ply=1)
    assert enroque["is_castling"] == 1
    corona = move_features(chess.Board("8/P7/8/8/8/8/8/k6K w - - 0 1"), chess.Move.from_uci("a7a8q"), ply=1)
    assert corona["is_promotion"] == 1


def test_tiempo_gastado_por_jugador():
    # Relojes tras cada jugada: blancas 180→170 (gastan 10), negras 180→175 (gastan 5).
    filas = game_features(["e2e4", "e7e5", "g1f3", "b8c6"], [180, 180, 170, 175])
    assert [f["time_spent"] for f in filas] == [-1, -1, 10, 5]
    assert [f["clock_after"] for f in filas] == [180, 180, 170, 175]


def test_sin_reloj():
    filas = game_features(["e2e4", "e7e5"])
    assert all(f["clock_after"] == -1 and f["time_spent"] == -1 for f in filas)


@pytest.mark.parametrize("n", [1, 10])
def test_game_features_una_fila_por_jugada(n):
    jugadas = ["g1f3", "g8f6", "f3g1", "f6g8"] * 3
    assert len(game_features(jugadas[:n])) == n
