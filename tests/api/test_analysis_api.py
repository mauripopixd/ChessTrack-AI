"""POST/GET /games/{id}/analysis contra PostgreSQL real.

Casi todo con un analizador falso (resultados exactos y sin motor). Un test usa
Stockfish de verdad si está instalado (en el CI sí): es el checkpoint de la Etapa 4.
"""

import chess.engine
import pytest
from sqlalchemy import func, select

from app.analysis import MATE_CP, find_stockfish
from app.deps import get_analyzer, get_classifier
from app.engine import EnginePool
from app.models import MoveAnalysis
from app.pgn_parser import parse_pgn
from app.services.analysis import StockfishAnalyzer
from tests.api.test_games import cuenta, leer, subir
from tests.fakes import FakeAnalyzer, FakeClassifier

ERRORES = {3, 4, 7}


@pytest.fixture
def analizador():
    return FakeAnalyzer(ERRORES)


@pytest.fixture
def api(client, analizador):
    client.app.dependency_overrides[get_analyzer] = lambda: analizador
    client.app.dependency_overrides[get_classifier] = lambda: FakeClassifier({3, 5})
    return client


@pytest.fixture
def yo(api):
    return cuenta(api, "weytey")


@pytest.fixture
def partida(api, yo) -> int:
    return subir(api, yo, leer("partida1.pgn")).json()["created"][0]["id"]


def test_post_analiza_y_devuelve_el_resumen(api, yo, partida):
    r = api.post(f"/games/{partida}/analysis", headers=yo)
    assert r.status_code == 200
    body = r.json()
    assert body["game_id"] == partida and body["depth"] == 7
    assert [e["ply"] for e in body["summary"]["errors"]] == [3, 7]
    assert body["model"]["both"] == 1 and body["model"]["recall"] == 0.5
    assert body["moves"][0]["san"] == "e4" and body["moves"][0]["best_move"] == "e4"


def test_se_guarda_en_la_bd(api, yo, partida, session):
    api.post(f"/games/{partida}/analysis", headers=yo)
    jugadas = len(parse_pgn(leer("partida1.pgn").decode()).moves)
    assert session.scalar(select(func.count()).select_from(MoveAnalysis)) == jugadas  # una por jugada
    assert api.get(f"/games/{partida}/analysis", headers=yo).json()["summary"]["labels"]["error_grave"] == 2


def test_get_antes_de_analizar_da_404_explicativo(api, yo, partida):
    r = api.get(f"/games/{partida}/analysis", headers=yo)
    assert r.status_code == 404 and "POST" in r.json()["detail"]


def test_segundo_post_no_vuelve_a_analizar(api, yo, partida, analizador):
    api.post(f"/games/{partida}/analysis", headers=yo)
    api.post(f"/games/{partida}/analysis", headers=yo)
    assert analizador.llamadas == 1


def test_force_rehace_y_sustituye_las_filas(api, yo, partida, session):
    api.post(f"/games/{partida}/analysis", headers=yo)
    antes = session.scalar(select(func.count()).select_from(MoveAnalysis))
    api.app.dependency_overrides[get_analyzer] = lambda: FakeAnalyzer(set(), depth=9)
    r = api.post(f"/games/{partida}/analysis", params={"force": True}, headers=yo)
    assert r.status_code == 200 and r.json()["depth"] == 9 and r.json()["summary"]["errors"] == []
    # Misma cantidad de filas: se actualizaron, no se duplicaron.
    assert session.scalar(select(func.count()).select_from(MoveAnalysis)) == antes


def test_sin_clasificador(api, yo, partida):
    api.app.dependency_overrides[get_classifier] = lambda: None
    body = api.post(f"/games/{partida}/analysis", headers=yo).json()
    assert body["model"] is None and body["moves"][0]["error_prob"] is None


def test_partida_ajena_da_404(api, yo, partida):
    otro = cuenta(api, "intruso")
    for metodo in ("post", "get"):
        r = getattr(api, metodo)(f"/games/{partida}/analysis", headers=otro)
        assert r.status_code == 404 and r.json() == {"detail": "Partida no encontrada"}


def test_sin_token_da_401(api, partida):
    assert api.post(f"/games/{partida}/analysis").status_code == 401


def test_borrar_la_partida_borra_su_analisis(api, yo, partida, session):
    api.post(f"/games/{partida}/analysis", headers=yo)
    api.delete(f"/games/{partida}", headers=yo)
    session.expire_all()
    assert session.scalar(select(func.count()).select_from(MoveAnalysis)) == 0


def test_sin_stockfish_da_503(api, yo, partida):
    api.app.dependency_overrides[get_analyzer] = lambda: StockfishAnalyzer(EnginePool(None), depth=5)
    r = api.post(f"/games/{partida}/analysis", headers=yo)
    assert r.status_code == 503 and "Stockfish" in r.json()["detail"]


# ---------------------------------------------------------------- con Stockfish de verdad


def test_checkpoint_etapa4_con_stockfish_real(api, yo, partida):
    """Subo una partida real y el sistema marca mis errores con Stockfish."""
    ruta = find_stockfish()
    if ruta is None:
        pytest.skip("Stockfish no está instalado")
    pool = EnginePool(ruta, size=1)
    api.app.dependency_overrides[get_analyzer] = lambda: StockfishAnalyzer(pool, depth=8)
    try:
        body = api.post(f"/games/{partida}/analysis", headers=yo).json()
    finally:
        pool.close()
    ultima = body["moves"][-1]
    assert ultima["san"] == "Ra8#" and ultima["eval_after"] == MATE_CP  # partida1 acaba en mate
    assert body["summary"]["user_color"] == "white"
    assert set(body["summary"]["labels"]) == {"buena", "imprecision", "error", "error_grave"}
    assert all(e["best_move"] for e in body["summary"]["errors"])


def test_pool_presta_motores_distintos_a_la_vez():
    ruta = find_stockfish()
    if ruta is None:
        pytest.skip("Stockfish no está instalado")
    pool = EnginePool(ruta, size=2)
    try:
        with pool.engine() as a, pool.engine() as b:
            assert a is not b
            assert isinstance(a, chess.engine.SimpleEngine)
        with pool.engine() as c:
            assert c in (a, b)  # se reutilizan, no se crean nuevos
    finally:
        pool.close()
