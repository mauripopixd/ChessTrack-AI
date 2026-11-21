"""Asistente RAG y cliente de LLM, sin red ni modelos: buscador y HTTP falsos."""

from datetime import timedelta

import httpx
import pytest

from app.rag.assistant import SIN_FUENTES, SYSTEM, OpeningAssistant, citas_en, contexto
from app.rag.hits import Hit
from app.rag.llm import Completion, LLMClient, LLMUnavailableError, Provider, groq, ollama


def hit(n: int, source: str = "wikibooks") -> Hit:
    return Hit(
        id=f"h{n}", text=f"Texto de la fuente {n}", source=source, title=f"Página {n}",
        url=f"https://ejemplo/{n}", moves="1. e4 c5", name="Sicilian Defense", eco="B20",
        license="CC BY-SA 4.0" if source == "wikibooks" else "CC0", score=0.9,
    )  # fmt: skip


class FakeRetriever:
    def __init__(self, hits: list[Hit]) -> None:
        self.hits = hits
        self.preguntas: list[str] = []

    def search(self, pregunta: str, k: int = 5) -> list[Hit]:
        self.preguntas.append(pregunta)
        return self.hits[:k]


class FakeLLM:
    def __init__(self, texto: str) -> None:
        self.texto = texto
        self.recibido: tuple[str, str] | None = None

    def complete(self, system: str, user: str, max_tokens: int = 1500) -> Completion:
        self.recibido = (system, user)
        return Completion(self.texto, "fake", "modelo-falso", 5, 10)


# ---------------------------------------------------------------- citas


@pytest.mark.parametrize(
    ("texto", "citas"),
    [
        ("Idea [1].", [1]),
        ("Uno [2] y dos [1][3].", [2, 1, 3]),
        ("Juntas [1, 2] y repetida [1].", [1, 2]),
        ("Sin citas.", []),
        ("Una jugada [Nf3] no es cita.", []),
    ],
)
def test_citas_en(texto, citas):
    assert citas_en(texto) == citas


def test_contexto_numera_las_fuentes_con_titulo_y_licencia():
    c = contexto([hit(1), hit(2, "lichess")])
    assert c.startswith("[1] Página 1 · wikibooks (CC BY-SA 4.0)\nTexto de la fuente 1")
    assert "[2] Página 2 · lichess (CC0)" in c


# ---------------------------------------------------------------- asistente


def test_responde_con_las_citas_de_sus_fuentes():
    llm = FakeLLM("Las negras luchan por d4 [2]. Ver también [1].")
    a = OpeningAssistant(FakeRetriever([hit(1), hit(2), hit(3)]), llm, k=3).ask("¿Siciliana?")
    assert [c.n for c in a.citations] == [2, 1]
    assert a.citations[0].url == "https://ejemplo/2" and a.citations[0].license == "CC BY-SA 4.0"
    assert a.invalid_citations == [] and a.provider == "fake"
    sistema, usuario = llm.recibido
    assert sistema == SYSTEM
    assert usuario.endswith("Pregunta: ¿Siciliana?") and "[3] Página 3" in usuario


def test_cita_inexistente_se_marca_como_invalida():
    a = OpeningAssistant(FakeRetriever([hit(1)]), FakeLLM("Algo [1] y otra cosa [7]."), k=1).ask("?")
    assert [c.n for c in a.citations] == [1] and a.invalid_citations == [7]


def test_sin_fuentes_no_llama_al_llm():
    llm = FakeLLM("no debería usarse")
    a = OpeningAssistant(FakeRetriever([]), llm).ask("¿Algo raro?")
    assert a.text == SIN_FUENTES and a.citations == [] and llm.recibido is None


def test_respeta_k():
    buscador = FakeRetriever([hit(i) for i in range(1, 10)])
    a = OpeningAssistant(buscador, FakeLLM("x [1]"), k=4).ask("?")
    assert len(a.retrieved) == 4


# ---------------------------------------------------------------- cliente de LLM (HTTP falso)


def _respuesta(status: int, contenido: str | None = "Hola", tokens: int = 7) -> httpx.Response:
    cuerpo = {"choices": [{"message": {"content": contenido}}], "usage": {"total_tokens": tokens}}
    r = httpx.Response(status, json=cuerpo, request=httpx.Request("POST", "https://x/chat/completions"))
    r.elapsed = timedelta(milliseconds=42)
    return r


@pytest.fixture
def http_falso(monkeypatch):
    """Cola de respuestas por proveedor (según la URL) y registro de las peticiones."""
    estado = {"respuestas": {}, "peticiones": []}

    def post(url, json, headers, timeout):
        estado["peticiones"].append({"url": url, "json": json, "headers": headers})
        respuesta = estado["respuestas"][url.split("/chat")[0]].pop(0)
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta

    monkeypatch.setattr(httpx, "post", post)
    return estado


A = Provider("a", "https://a", "modelo-a", "clave-a")
B = Provider("b", "https://b", "modelo-b")


def test_usa_el_primer_proveedor_si_responde(http_falso):
    http_falso["respuestas"] = {"https://a": [_respuesta(200, "de A")], "https://b": []}
    c = LLMClient([A, B]).complete("sistema", "usuario")
    assert (c.text, c.provider, c.model, c.latency_ms, c.tokens) == ("de A", "a", "modelo-a", 42, 7)
    peticion = http_falso["peticiones"][0]
    assert peticion["headers"] == {"Authorization": "Bearer clave-a"}
    assert peticion["json"]["messages"][0] == {"role": "system", "content": "sistema"}


@pytest.mark.parametrize(
    "fallo",
    [_respuesta(429), _respuesta(503), httpx.ConnectError("sin red"), _respuesta(200, contenido="")],
    ids=["limite-429", "caida-503", "sin-red", "respuesta-vacia"],
)
def test_cae_al_siguiente_proveedor(http_falso, fallo):
    http_falso["respuestas"] = {"https://a": [fallo], "https://b": [_respuesta(200, "de B")]}
    c = LLMClient([A, B]).complete("s", "u")
    assert c.provider == "b" and c.text == "de B"
    assert "Authorization" not in http_falso["peticiones"][1]["headers"]  # B no lleva clave


def test_si_fallan_todos_lanza_error_con_los_motivos(http_falso):
    http_falso["respuestas"] = {"https://a": [_respuesta(429)], "https://b": [httpx.ConnectError("apagado")]}
    with pytest.raises(LLMUnavailableError, match="^a: HTTP 429; b: ConnectError: apagado$"):
        LLMClient([A, B]).complete("s", "u")


def test_sin_proveedores_es_un_error_de_configuracion():
    with pytest.raises(ValueError):
        LLMClient([])


def test_proveedores_predefinidos_desactivan_o_limitan_el_razonamiento():
    assert groq("k").extra == {"reasoning_effort": "low"} and groq("k").model == "openai/gpt-oss-120b"
    assert ollama("qwen").extra == {"reasoning_effort": "none"} and ollama("qwen").api_key is None


# ---------------------------------------------------------------- reescritura de la consulta


class BuscadorPorConsulta:
    """Devuelve resultados distintos según el texto buscado."""

    def __init__(self, por_texto: dict[str, list[Hit]]) -> None:
        self.por_texto = por_texto

    def search(self, pregunta: str, k: int = 5) -> list[Hit]:
        return self.por_texto.get(pregunta, [])[:k]


def _con_score(h: Hit, score: float) -> Hit:
    return Hit(**{**{f: getattr(h, f) for f in Hit.__slots__}, "score": score})


def test_reescritura_combina_y_se_queda_con_los_mejores():
    original = [_con_score(hit(1), 0.50), _con_score(hit(2), 0.40)]
    reescrita = [_con_score(hit(2), 0.90), _con_score(hit(3), 0.70)]
    buscador = BuscadorPorConsulta({"¿Gambito de Dama?": original, "Queen's Gambit": reescrita})
    a = OpeningAssistant(buscador, FakeLLM("Queen's Gambit"), k=2, rewrite=True)
    hits = a.buscar("¿Gambito de Dama?")
    assert [(h.id, h.score) for h in hits] == [("h2", 0.90), ("h3", 0.70)]


def test_sin_reescritura_no_llama_al_llm():
    llm = FakeLLM("no debería usarse")
    OpeningAssistant(FakeRetriever([hit(1)]), llm, k=1).buscar("?")
    assert llm.recibido is None


def test_si_la_reescritura_falla_sigue_con_la_busqueda_normal():
    class LLMCaido:
        def complete(self, system, user, max_tokens=1500):
            raise LLMUnavailableError("groq: HTTP 429")

    a = OpeningAssistant(FakeRetriever([hit(1)]), LLMCaido(), k=1, rewrite=True)
    assert [h.id for h in a.buscar("?")] == ["h1"]
