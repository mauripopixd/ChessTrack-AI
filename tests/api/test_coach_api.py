"""/coach/games contra PostgreSQL real, con Stockfish real (se salta sin él) y un LLM falso."""

import contextlib

import chess
import chess.engine
import pytest
from langchain_core.messages import AIMessage
from sqlalchemy import func, select

from app.analysis import find_stockfish
from app.config import get_settings
from app.deps import get_classifier, get_coach_llm_factory, get_coach_motor, get_coach_retriever
from app.models import CoachMessage
from app.repositories.coach import SqlCoachRepository
from tests.api.test_games import cuenta
from tests.fakes import FakeLLM
from tests.unit.test_coach_service import partida_tras


@pytest.fixture(scope="module")
def stockfish():
    ruta = find_stockfish()
    if ruta is None:
        pytest.skip("Stockfish no está instalado (ver README)")
    with chess.engine.SimpleEngine.popen_uci(ruta) as eng:
        eng.configure({"Threads": 1})
        yield eng


@pytest.fixture
def llm():
    return FakeLLM(respuestas=[], llamadas=[])


@pytest.fixture
def api(client, stockfish, llm):
    o = client.app.dependency_overrides
    o[get_coach_motor] = lambda: lambda: contextlib.nullcontext(stockfish)
    o[get_coach_llm_factory] = lambda: lambda tools: llm
    o[get_coach_retriever] = lambda: None
    o[get_classifier] = lambda: None
    return client


@pytest.fixture
def yo(api):
    return cuenta(api, "weytey")


def mi_id(api, yo) -> int:
    return api.get("/users/me", headers=yo).json()["id"]


def test_sin_sesion_da_401(api):
    assert api.post("/coach/games", json={}).status_code == 401
    assert api.get("/coach/games").status_code == 401


def test_crear_listar_y_leer(api, yo):
    r = api.post("/coach/games", json={"color": "black", "level": 0}, headers=yo)
    assert r.status_code == 201
    p = r.json()
    assert p["color"] == "black" and p["move_count"] == 1 and p["your_turn"] and p["result"] == "*"
    assert api.get("/coach/games", headers=yo).json()["total"] == 1
    leida = api.get(f"/coach/games/{p['id']}", headers=yo).json()
    assert leida["moves"][0]["by"] == "coach" and leida["fen"] == p["fen"]


@pytest.mark.parametrize("body", [{"level": 21}, {"level": -1}, {"color": "verde"}])
def test_crear_valida_la_entrada(api, yo, body):
    assert api.post("/coach/games", json=body, headers=yo).status_code == 422


def test_jugar_una_jugada(api, yo, llm):
    p = api.post("/coach/games", json={"level": 0}, headers=yo).json()
    r = api.post(f"/coach/games/{p['id']}/move", json={"move": "e4"}, headers=yo)
    assert r.status_code == 200
    t = r.json()
    assert t["your_move"]["san"] == "e4" and t["your_move"]["label"] == "buena"
    assert t["coach_move"]["by"] == "coach" and t["your_turn"] and t["answer"] is None
    assert llm.llamadas == []
    assert api.get(f"/coach/games/{p['id']}", headers=yo).json()["move_count"] == 2


def test_jugada_ilegal_422_y_partida_ajena_404(api, yo):
    p = api.post("/coach/games", json={}, headers=yo).json()
    r = api.post(f"/coach/games/{p['id']}/move", json={"move": "Ke2"}, headers=yo)
    assert r.status_code == 422 and "no es legal" in r.json()["detail"]
    otro = cuenta(api, "otro")
    assert api.get(f"/coach/games/{p['id']}", headers=otro).status_code == 404
    assert api.post(f"/coach/games/{p['id']}/move", json={"move": "e4"}, headers=otro).status_code == 404
    assert api.post(f"/coach/games/{p['id']}/ask", json={"question": "¿?"}, headers=otro).status_code == 404


def test_error_comentado_y_guardado_en_el_chat(api, yo, stockfish, llm, session):
    p = SqlCoachRepository(session).create(partida_tras(stockfish, mi_id(api, yo), "e4", "d5"))
    llm.respuestas = [AIMessage("La dama queda a tiro del alfil.")]
    t = api.post(f"/coach/games/{p.id}/move", json={"move": "Qg4"}, headers=yo).json()
    assert t["your_move"]["label"] == "error_grave" and t["answer"].startswith("La dama")
    mensajes = api.get(f"/coach/games/{p.id}", headers=yo).json()["messages"]
    assert [m["role"] for m in mensajes] == ["user", "coach"]


def test_partida_terminada_409(api, yo, stockfish, session):
    p = SqlCoachRepository(session).create(partida_tras(stockfish, mi_id(api, yo), "f3", "e5", "g4", "Qh4#"))
    r = api.post(f"/coach/games/{p.id}/move", json={"move": "a3"}, headers=yo)
    assert r.status_code == 409


def test_preguntar_y_limite_por_hora(api, yo, llm, monkeypatch, session):
    monkeypatch.setattr(get_settings(), "coach_answers_per_hour", 1)
    p = api.post("/coach/games", json={}, headers=yo).json()
    llm.respuestas = [AIMessage("Igualada.")]
    r = api.post(f"/coach/games/{p['id']}/ask", json={"question": "¿Voy ganando?"}, headers=yo)
    assert r.status_code == 200 and r.json()["answer"] == "Igualada."
    r = api.post(f"/coach/games/{p['id']}/ask", json={"question": "¿Y ahora?"}, headers=yo)
    assert r.status_code == 429 and r.headers["retry-after"] == "3600"
    assert session.scalar(select(func.count()).select_from(CoachMessage)) == 2  # la del 429 no se guarda


def test_llm_caido_503(api, yo, llm):
    p = api.post("/coach/games", json={}, headers=yo).json()
    llm.falla = True
    r = api.post(f"/coach/games/{p['id']}/ask", json={"question": "¿Voy ganando?"}, headers=yo)
    assert r.status_code == 503 and "no puede responder" in r.json()["detail"]


def test_borrar(api, yo):
    p = api.post("/coach/games", json={}, headers=yo).json()
    assert api.delete(f"/coach/games/{p['id']}", headers=yo).status_code == 204
    assert api.get(f"/coach/games/{p['id']}", headers=yo).status_code == 404
    assert api.delete(f"/coach/games/{p['id']}", headers=yo).status_code == 404


def test_partida_completa_por_api(api, yo, stockfish):
    """Partida entera contra el coach por HTTP: el usuario es Stockfish a nivel 0 y el coach a 20."""
    p = api.post("/coach/games", json={"level": 20}, headers=yo).json()
    tablero = chess.Board()
    for _ in range(150):
        jugada = stockfish.play(tablero, chess.engine.Limit(time=0.01), options={"Skill Level": 0}).move
        t = api.post(f"/coach/games/{p['id']}/move", json={"move": jugada.uci()}, headers=yo).json()
        tablero = chess.Board(t["fen"])
        if t["result"] != "*":
            break
    final = api.get(f"/coach/games/{p['id']}", headers=yo).json()
    assert final["result"] in ("0-1", "1/2-1/2") and final["termination"] is not None
    assert final["move_count"] == len(final["moves"]) and not final["your_turn"]


def test_ofrecer_y_rechazar_tablas_por_api(api, yo):
    p = api.post("/coach/games", json={}, headers=yo).json()
    r = api.post(f"/coach/games/{p['id']}/draw", headers=yo)
    assert r.status_code == 200 and r.json()["accepted"] is False
    assert api.post(f"/coach/games/{p['id']}/draw/decline", headers=yo).status_code == 204
    otro = cuenta(api, "otro")
    assert api.post(f"/coach/games/{p['id']}/draw", headers=otro).status_code == 404


def test_tablas_aceptadas_por_api_y_luego_409(api, yo, stockfish, session):
    jugadas = ["e4", "e5", "Nf3", "Nf6", "Nxe5", "Nxe4", "Qe2", "Nf6", "Nc6+", "Be7"]
    p = SqlCoachRepository(session).create(partida_tras(stockfish, mi_id(api, yo), *jugadas))
    r = api.post(f"/coach/games/{p.id}/draw", headers=yo).json()
    assert r["accepted"] and r["result"] == "1/2-1/2" and r["termination"] == "agreement"
    assert api.post(f"/coach/games/{p.id}/draw", headers=yo).status_code == 409
    assert api.post(f"/coach/games/{p.id}/move", json={"move": "Nxd8"}, headers=yo).status_code == 409


def test_rendirse_por_api(api, yo):
    p = api.post("/coach/games", json={}, headers=yo).json()
    r = api.post(f"/coach/games/{p['id']}/resign", headers=yo)
    assert r.status_code == 200 and r.json()["result"] == "0-1" and r.json()["termination"] == "resignation"
    assert api.post(f"/coach/games/{p['id']}/resign", headers=yo).status_code == 409
    assert api.post(f"/coach/games/{p['id']}/draw", headers=yo).status_code == 409
    assert api.post(f"/coach/games/{p['id']}/resign", headers=cuenta(api, "otro")).status_code == 404


def test_crear_por_elo(api, yo):
    p = api.post("/coach/games", json={"elo": 800}, headers=yo).json()
    assert p["elo"] == 800 and p["level"] is None
    assert api.get("/coach/games", headers=yo).json()["items"][0]["elo"] == 800
    assert api.post("/coach/games", json={}, headers=yo).json()["elo"] == 1200


@pytest.mark.parametrize("body", [{"elo": 300}, {"elo": 3200}, {"elo": 1500, "level": 3}])
def test_crear_por_elo_valida_la_entrada(api, yo, body):
    assert api.post("/coach/games", json=body, headers=yo).status_code == 422
