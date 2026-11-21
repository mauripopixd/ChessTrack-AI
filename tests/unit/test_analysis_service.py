"""AnalysisService sin BD ni motor: repositorio en memoria + analizador y clasificador falsos."""

from pathlib import Path

import pytest

from app.models import User
from app.pgn_parser import parse_pgn
from app.services.analysis import AnalysisService, NotAnalyzedError
from app.services.games import GameService
from tests.fakes import FakeAnalyzer, FakeClassifier, InMemoryGameRepository

PARTIDA1 = (Path(__file__).resolve().parents[2] / "data" / "samples" / "partida1.pgn").read_text(
    encoding="utf-8"
)
# En partida1 weytey juega con blancas (plies impares). Errores "de Stockfish" en dos
# jugadas mías (3 y 7) y una del rival (4).
ERRORES = {3, 4, 7}


@pytest.fixture
def repo():
    return InMemoryGameRepository()


@pytest.fixture
def yo():
    return User(id=1, username="weytey", email="w@example.com", hashed_password="x")


@pytest.fixture
def partida(repo, yo) -> int:
    return GameService(repo).import_pgn(yo, PARTIDA1).created[0].id


def servicio(repo, analizador=None, clasificador=None):
    return AnalysisService(repo, analizador or FakeAnalyzer(ERRORES), clasificador)


def test_analiza_todas_las_jugadas(repo, yo, partida):
    r = servicio(repo).analyze(yo, partida)
    assert len(r.moves) == len(parse_pgn(PARTIDA1).moves)
    assert r.depth == 7 and r.analyzed_at is not None
    assert [m.move_number for m in r.moves[:4]] == [1, 1, 2, 2]
    assert [m.mover for m in r.moves[:2]] == ["white", "black"]
    assert r.moves[0].best_move == r.moves[0].san  # el fake propone la propia jugada, en SAN


def test_resumen_solo_con_mis_jugadas(repo, yo, partida):
    r = servicio(repo).analyze(yo, partida)
    mias = [m for m in r.moves if m.is_user]
    assert r.summary.user_color == "white"
    assert r.summary.moves_analyzed == len(mias)
    assert [e.ply for e in r.summary.errors] == [3, 7]  # el error del rival (ply 4) no cuenta
    assert r.summary.labels["error_grave"] == 2
    assert sum(r.summary.labels.values()) == len(mias)
    assert r.summary.acpl == round(2 * 500 / len(mias), 1)


def test_sin_clasificador_no_hay_comparacion(repo, yo, partida):
    r = servicio(repo).analyze(yo, partida)
    assert r.model is None
    assert all(m.error_prob is None and m.model_flag is None for m in r.moves)


def test_comparacion_con_el_clasificador(repo, yo, partida):
    # El modelo marca 3 (acierta), 5 y 9 (falsas alarmas); no ve el 7.
    r = servicio(repo, clasificador=FakeClassifier({3, 5, 9})).analyze(yo, partida)
    m = r.model
    assert (m.stockfish_errors, m.model_flags, m.both) == (2, 3, 1)
    assert m.precision == round(1 / 3, 3) and m.recall == 0.5
    assert r.moves[2].model_flag is True and r.moves[6].model_flag is False


def test_ya_analizada_no_se_repite(repo, yo, partida):
    analizador = FakeAnalyzer(ERRORES)
    s = servicio(repo, analizador)
    s.analyze(yo, partida)
    s.analyze(yo, partida)
    assert analizador.llamadas == 1


def test_force_rehace_el_analisis(repo, yo, partida):
    s = servicio(repo, FakeAnalyzer(ERRORES))
    s.analyze(yo, partida)
    s.analyzer = FakeAnalyzer(set(), depth=9)
    r = s.analyze(yo, partida, force=True)
    assert r.depth == 9 and r.summary.errors == []


def test_get_antes_de_analizar(repo, yo, partida):
    with pytest.raises(NotAnalyzedError):
        servicio(repo).get(yo, partida)
    servicio(repo).analyze(yo, partida)
    assert servicio(repo).get(yo, partida).summary.labels["error_grave"] == 2


def test_partida_ajena_o_inexistente(repo, yo, partida):
    otro = User(id=2, username="otro", email="o@example.com", hashed_password="x")
    assert servicio(repo).analyze(otro, partida) is None
    assert servicio(repo).get(otro, partida) is None
    assert servicio(repo).analyze(yo, 999) is None


def test_sin_color_resume_todas_las_jugadas(repo):
    javier = User(id=3, username="javier", email="j@example.com", hashed_password="x")
    gid = GameService(repo).import_pgn(javier, PARTIDA1).created[0].id
    r = servicio(repo).analyze(javier, gid)
    assert r.summary.user_color is None
    assert r.summary.moves_analyzed == len(r.moves)
    assert [e.ply for e in r.summary.errors] == [3, 4, 7]
