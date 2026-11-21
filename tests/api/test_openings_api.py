"""POST /openings/ask con un asistente falso (sin índice, sin LLM)."""

import pytest

from app.deps import _assistant_dep
from app.rag.assistant import OpeningAssistant
from app.rag.llm import LLMUnavailableError
from tests.api.test_games import cuenta
from tests.unit.test_rag_assistant import FakeLLM, FakeRetriever, hit


@pytest.fixture
def api(client):
    asistente = OpeningAssistant(
        FakeRetriever([hit(1), hit(2, "lichess")]), FakeLLM("Idea [1] y jugadas [2].")
    )
    client.app.dependency_overrides[_assistant_dep] = lambda: asistente
    return client


def test_responde_con_citas(api):
    r = api.post("/openings/ask", json={"question": "¿Qué es la Siciliana?"}, headers=cuenta(api, "ana"))
    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == "Idea [1] y jugadas [2]."
    assert [c["n"] for c in body["citations"]] == [1, 2]
    assert body["citations"][1] | {"url": None} == {
        "n": 2, "title": "Página 2", "url": None, "license": "CC0", "source": "lichess",
        "opening": "Sicilian Defense", "eco": "B20", "moves": "1. e4 c5",
    }  # fmt: skip
    assert body["provider"] == "fake" and body["invalid_citations"] == []


def test_pide_sesion(api):
    assert api.post("/openings/ask", json={"question": "¿Qué es la Siciliana?"}).status_code == 401


@pytest.mark.parametrize("pregunta", ["", "hola", "x" * 501])
def test_pregunta_invalida_da_422(api, pregunta):
    r = api.post("/openings/ask", json={"question": pregunta}, headers=cuenta(api, "ana"))
    assert r.status_code == 422


def test_sin_llm_disponible_da_503(client):
    class SinLLM:
        def ask(self, pregunta):
            raise LLMUnavailableError("groq: 429; ollama: apagado")

    client.app.dependency_overrides[_assistant_dep] = lambda: SinLLM()
    r = client.post(
        "/openings/ask", json={"question": "¿Qué es la Siciliana?"}, headers=cuenta(client, "ana")
    )
    assert r.status_code == 503 and "429" in r.json()["detail"]


def test_sin_indice_da_503(client, monkeypatch, tmp_path):
    from app import deps

    deps.get_opening_assistant.cache_clear()
    monkeypatch.setattr(deps.get_settings(), "rag_index_dir", str(tmp_path / "no_existe"))
    try:
        r = client.post(
            "/openings/ask", json={"question": "¿Qué es la Siciliana?"}, headers=cuenta(client, "ana")
        )
    finally:
        deps.get_opening_assistant.cache_clear()
    assert r.status_code == 503 and "build_rag_index" in r.json()["detail"]
