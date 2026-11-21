"""Análisis de jugadas: funciones puras sin motor y, si Stockfish está instalado, con motor."""

import chess
import chess.engine
import pytest

from app.analysis import (
    CP_LOSS_MAX,
    MATE_CP,
    analyze_moves,
    classify,
    find_stockfish,
    win_probability,
)

# ---------------------------------------------------------------- sin motor


def test_win_probability_simetrica_y_acotada():
    assert win_probability(0) == pytest.approx(50)
    for cp in (50, 300, 900):
        assert win_probability(cp) + win_probability(-cp) == pytest.approx(100)
        assert 50 < win_probability(cp) < 100
    assert win_probability(MATE_CP) == pytest.approx(100, abs=1e-6)
    assert win_probability(-MATE_CP) == pytest.approx(0, abs=1e-6)


def test_win_probability_crece_con_la_ventaja():
    valores = [win_probability(cp) for cp in range(-1000, 1001, 100)]
    assert valores == sorted(valores)


def test_perder_100cp_importa_mas_igualado_que_ganando():
    igualado = win_probability(0) - win_probability(-100)
    ganando = win_probability(900) - win_probability(800)
    assert igualado > 3 * ganando


@pytest.mark.parametrize(
    ("caida", "etiqueta"),
    [(0, "buena"), (4.99, "buena"), (5, "imprecision"), (10, "error"), (19.9, "error"), (20, "error_grave")],
)
def test_classify(caida, etiqueta):
    assert classify(caida) == etiqueta


# ---------------------------------------------------------------- con Stockfish


@pytest.fixture(scope="module")
def engine():
    ruta = find_stockfish()
    if ruta is None:
        pytest.skip("Stockfish no está instalado (ver README)")
    with chess.engine.SimpleEngine.popen_uci(ruta) as eng:
        eng.configure({"Threads": 1})
        yield eng


LIMITE = chess.engine.Limit(depth=10)


def test_mate_pastor(engine):
    # 3... Nf6?? permite el mate: error grave de negras; 4. Qxf7# termina la partida.
    jugadas = ["e2e4", "e7e5", "d1h5", "b8c6", "f1c4", "g8f6", "h5f7"]
    r = analyze_moves(jugadas, engine, LIMITE)
    assert [m.san for m in r] == ["e4", "e5", "Qh5", "Nc6", "Bc4", "Nf6", "Qxf7#"]
    nf6 = r[5]
    assert nf6.mover == "black" and nf6.label == "error_grave"
    assert nf6.cp_loss == CP_LOSS_MAX
    assert r[-1].eval_after == MATE_CP  # tras el mate, gana blancas
    assert r[-1].best_uci == "h5f7"  # antes de mover, el motor ya veía el mate


def test_jugar_la_mejor_no_pierde(engine):
    r = analyze_moves(["e2e4"], engine, LIMITE)
    assert r[0].label == "buena" and r[0].win_drop < 5


def test_regalar_la_dama_es_error_grave(engine):
    # Desde la posición inicial tras 1. e4 e5 2. Qh5 Nc6: 3. Qxe5+?? Nxe5 pierde la dama.
    r = analyze_moves(["e2e4", "e7e5", "d1h5", "b8c6", "h5e5", "c6e5"], engine, LIMITE)
    assert r[4].san == "Qxe5+" and r[4].label == "error_grave"
    # Dama por peón. Los cp exactos dependen de la versión de Stockfish (19 local da ~700,
    # 16 en el CI de Ubuntu da 572), así que se piden "más de 5 peones" y una caída fuerte.
    assert r[4].cp_loss >= 500
    assert r[4].win_drop >= 30


def test_posicion_inicial_distinta(engine):
    fen = "8/P7/8/8/8/8/8/k6K w - - 0 1"
    r = analyze_moves(["a7a8q"], engine, LIMITE, initial_fen=fen)
    assert r[0].san == "a8=Q+"  # la dama da jaque por la columna a
    # Se respeta la posición de partida: blancas ganan claro (sin tablas de finales,
    # a poca profundidad el motor no ve aún el mate, así que no se pide un número exacto).
    assert r[0].eval_before > 0 and r[0].win_after > 80
