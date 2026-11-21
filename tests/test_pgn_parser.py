from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path

import chess
import pytest

from app.pgn_parser import InvalidPGNError, ParsedGame, parse_pgn, parse_pgn_each, parse_pgn_many

SAMPLES = Path(__file__).resolve().parent.parent / "data" / "samples"

# (archivo, resultado, color de weytey, texto esperado en Termination)
MUESTRAS = [
    ("partida1.pgn", "1-0", "white", "checkmate"),
    ("partida2.pgn", "1-0", "black", "resignation"),
    ("partida3.pgn", "1/2-1/2", "black", "repetition"),
    ("partida4.pgn", "0-1", "white", "on time"),
    ("partida5.pgn", "0-1", "black", "on time"),
]


def leer(nombre: str) -> str:
    return (SAMPLES / nombre).read_text(encoding="utf-8")


def ucis(game: ParsedGame) -> set[str]:
    return {m.uci for m in game.moves}


def sans(game: ParsedGame) -> set[str]:
    return {m.san for m in game.moves}


# ---------------------------------------------------------------- partidas reales


@pytest.mark.parametrize(("archivo", "resultado", "color", "final"), MUESTRAS)
def test_muestras_reales(archivo, resultado, color, final):
    game = parse_pgn(leer(archivo))

    assert game.result == resultado
    assert getattr(game, color).lower() == "weytey"
    assert final in game.headers["Termination"]
    assert game.moves, "debe tener jugadas"
    assert [m.ply for m in game.moves] == list(range(1, len(game.moves) + 1))
    # chess.com guarda la posición final: debe coincidir con nuestra última FEN
    # (se comparan los 4 primeros campos; los contadores pueden diferir).
    ultima = game.moves[-1].fen_after.split()[:4]
    assert ultima == game.headers["CurrentPosition"].split()[:4]


def test_partida1_termina_en_mate():
    game = parse_pgn(leer("partida1.pgn"))
    assert chess.Board(game.moves[-1].fen_after).is_checkmate()
    assert game.moves[-1].san.endswith("#")


def test_partida3_termina_en_triple_repeticion():
    game = parse_pgn(leer("partida3.pgn"))
    board = chess.Board(game.initial_fen)
    for m in game.moves:
        board.push_uci(m.uci)
    assert board.is_repetition(3)


def test_muestras_cubren_jugadas_especiales():
    p1, p2, p4 = (parse_pgn(leer(f"partida{n}.pgn")) for n in (1, 2, 4))
    assert "O-O-O" in sans(p1)  # enroque largo
    assert any(
        chess.Board(a.fen_after).is_en_passant(chess.Move.from_uci(b.uci)) for a, b in pairwise(p2.moves)
    )  # captura al paso
    assert any("=" in m.san for m in p4.moves)  # coronación


def test_played_at_usa_utc_de_chess_com():
    game = parse_pgn(leer("partida1.pgn"))
    h = game.headers
    esperado = datetime.strptime(f"{h['UTCDate']} {h['UTCTime']}", "%Y.%m.%d %H:%M:%S")
    assert game.played_at == esperado.replace(tzinfo=UTC)


# ---------------------------------------------------------------- varias partidas


def test_varias_lee_las_cinco_en_orden():
    games = parse_pgn_many(leer("varias.pgn"))
    individuales = [parse_pgn(leer(m[0])) for m in MUESTRAS]
    assert len(games) == 5
    assert [g.moves for g in games] == [g.moves for g in individuales]


def test_parse_pgn_rechaza_varias_partidas():
    with pytest.raises(InvalidPGNError, match="contiene 5"):
        parse_pgn(leer("varias.pgn"))


def test_varias_con_una_ilegal_indica_cual():
    texto = "1. e4 e5 *\n\n1. d4 d5 2. Ke3 *\n\n1. c4 *"
    with pytest.raises(InvalidPGNError) as exc:
        parse_pgn_many(texto)
    assert exc.value.game_index == 1
    assert "Partida 2" in str(exc.value)


# ---------------------------------------------------------------- entradas inválidas


@pytest.mark.parametrize("texto", ["", "   \n\n\t ", "﻿"])
def test_vacio_lanza_error(texto):
    with pytest.raises(InvalidPGNError, match="vacío"):
        parse_pgn(texto)


def test_texto_que_no_es_pgn_lanza_error():
    with pytest.raises(InvalidPGNError, match="ni jugadas"):
        parse_pgn("hola mundo esto no es pgn")


def test_jugada_ilegal_lanza_error_con_numero_de_jugada():
    with pytest.raises(InvalidPGNError, match=r"jugada 2\. inválida.*Ke3"):
        parse_pgn("1. e4 e5 2. Ke3 Nc6 *")


def test_jugada_ilegal_de_negras():
    with pytest.raises(InvalidPGNError, match=r"jugada 1\.\.\. inválida"):
        parse_pgn("1. e4 e4 *")


def test_jugada_ambigua_lanza_error():
    pgn = '[SetUp "1"]\n[FEN "k7/8/8/8/8/8/8/KN3N2 w - - 0 1"]\n\n1. Nd2 *'
    with pytest.raises(InvalidPGNError, match="ambiguous"):
        parse_pgn(pgn)


def test_resultado_no_valido_lanza_error():
    with pytest.raises(InvalidPGNError, match="resultado"):
        parse_pgn('[Result "gané"]\n\n1. e4 *')


def test_error_no_se_imprime_en_el_log(caplog):
    with pytest.raises(InvalidPGNError):
        parse_pgn("1. e4 e5 2. Ke3 *")
    assert not caplog.records


# ---------------------------------------------------------------- casos borde válidos


def test_sin_headers_usa_none():
    game = parse_pgn("1. e4 e5 2. Nf3 Nc6 1-0")
    assert game.white is None and game.black is None
    assert game.played_at is None
    assert game.result == "1-0"
    assert [m.san for m in game.moves] == ["e4", "e5", "Nf3", "Nc6"]


def test_solo_headers_sin_jugadas_es_valida():
    game = parse_pgn('[White "a"]\n[Black "b"]\n[Result "*"]\n\n*')
    assert game.moves == ()
    assert game.white == "a"


def test_fecha_incompleta_da_none():
    assert parse_pgn('[Date "2026.??.??"]\n\n1. e4 *').played_at is None


def test_fecha_sin_hora_usa_medianoche_utc():
    game = parse_pgn('[Date "2026.10.03"]\n\n1. e4 *')
    assert game.played_at == datetime(2026, 10, 3, tzinfo=UTC)


def test_primera_jugada_fen_y_uci():
    move = parse_pgn("1. e4 *").moves[0]
    assert move.ply == 1
    assert move.uci == "e2e4"
    assert move.fen_after == "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"


def test_enroque_corto_uci():
    game = parse_pgn("1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 4. O-O *")
    assert game.moves[-1].san == "O-O"
    assert game.moves[-1].uci == "e1g1"


def test_subcoronacion_a_caballo():
    pgn = '[SetUp "1"]\n[FEN "8/P7/8/8/8/8/8/k6K w - - 0 1"]\n\n1. a8=N *'
    game = parse_pgn(pgn)
    assert game.initial_fen == "8/P7/8/8/8/8/8/k6K w - - 0 1"
    assert game.moves[0].san == "a8=N"
    assert game.moves[0].uci == "a7a8n"
    assert game.moves[0].fen_after.startswith("N7/")


def test_comentarios_reloj_y_variantes_se_ignoran():
    pgn = "1. e4 {[%clk 0:02:58]} e5 $1 (1... c5 2. Nf3) 2. Nf3 Nc6 *"
    assert [m.san for m in parse_pgn(pgn).moves] == ["e4", "e5", "Nf3", "Nc6"]


def test_bom_al_inicio():
    assert parse_pgn("﻿1. e4 *").moves[0].san == "e4"


def test_objetos_inmutables():
    game = parse_pgn("1. e4 *")
    with pytest.raises(FrozenInstanceError):
        game.result = "1-0"
    with pytest.raises(FrozenInstanceError):
        game.moves[0].san = "d4"


# ---------------------------------------------------------------- lectura sin abortar


def test_each_sigue_despues_de_una_partida_invalida():
    texto = '[Event "a"]\n\n1. e4 e5 *\n\n[Event "b"]\n\n1. d4 d5 2. Ke3 *\n\n[Event "c"]\n\n1. c4 *'
    a, b, c = parse_pgn_each(texto)
    assert isinstance(a, ParsedGame) and a.headers["Event"] == "a"
    assert isinstance(b, InvalidPGNError) and b.game_index == 1
    assert isinstance(c, ParsedGame) and c.headers["Event"] == "c"


def test_each_con_texto_vacio_lanza_error():
    with pytest.raises(InvalidPGNError, match="vacío"):
        parse_pgn_each("  \n")


def test_each_y_many_coinciden_si_todo_es_valido():
    texto = leer("varias.pgn")
    assert [g.moves for g in parse_pgn_each(texto)] == [g.moves for g in parse_pgn_many(texto)]
