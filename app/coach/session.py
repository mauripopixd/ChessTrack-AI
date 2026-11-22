"""Turno del coach de principio a fin: ejecuta el grafo y deja la partida y el chat al día.

Es lo que usan el CLI (scripts/coach_cli.py) y, en el siguiente PR, la API.
"""

import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI

from app.coach.game import CoachGame, MoveReport
from app.coach.graph import build_graph, respuesta_final
from app.coach.tools import MotorFn
from app.config import get_settings
from app.rag.assistant import citas_en

RECURSION_LIMIT = 16  # ~7 rondas LLM ↔ herramientas como mucho


@dataclass(frozen=True)
class TurnResult:
    user_move: MoveReport | None
    coach_move: MoveReport | None
    answer: str | None  # texto del coach (pregunta o comentario de un error)
    model: str | None  # qué modelo respondió (groq u ollama)
    error: str | None  # jugada ilegal, partida terminada…
    result: str | None  # resultado si la partida terminó
    sources: list[str] = field(default_factory=list)  # "[n] título — url (licencia)" citadas
    llm_error: str | None = None  # el LLM falló: la jugada (si la hubo) se hizo igual


def normalizar_citas(texto: str) -> str:
    """gpt-oss a veces cita con su formato nativo, "【1†source】"; se pasa a "[1]"."""
    return re.sub(r"【(\d+)†[^】]*】", r"[\1]", texto)


def fuentes_citadas(texto: str, mensajes: list) -> list[str]:
    """Las fuentes de la última búsqueda de teoría que la respuesta cita con [n]."""
    busqueda = next(
        (m.content for m in reversed(mensajes) if m.type == "tool" and m.name == "buscar_teoria"), ""
    )
    cabeceras = {int(m.group(1)): m.group(0) for m in re.finditer(r"^\[(\d+)\] .+$", busqueda, re.M)}
    return [cabeceras[n] for n in citas_en(texto) if n in cabeceras]


def default_llm_factory() -> Callable[[list[BaseTool]], BaseChatModel]:
    """Groq gratis (gpt-oss-120b) con respaldo en Ollama local, ambos con las herramientas."""
    s = get_settings()

    def factory(tools: list[BaseTool]) -> BaseChatModel:  # tools=[] → modelo sin herramientas
        modelos = []
        if s.groq_api_key:
            modelos.append(
                ChatOpenAI(
                    model=s.groq_model,
                    base_url="https://api.groq.com/openai/v1",
                    api_key=s.groq_api_key.get_secret_value(),
                    temperature=0.2,
                    reasoning_effort="medium",
                    max_retries=0,
                    timeout=60,
                )  # fmt: skip
            )
        if s.ollama_model:
            modelos.append(
                ChatOpenAI(
                    model=s.ollama_model,
                    base_url=s.ollama_url,
                    api_key="ollama",
                    temperature=0.2,
                    reasoning_effort="none",
                    timeout=180,
                )  # fmt: skip
            )
        if not modelos:
            raise ValueError("No hay LLM configurado (GROQ_API_KEY u OLLAMA_MODEL)")
        con_tools = [m.bind_tools(tools) if tools else m for m in modelos]  # [] = sin herramientas
        # max_retries=0 en Groq: ante un 429 se pasa a Ollama al momento en vez de reintentar.
        return con_tools[0].with_fallbacks(con_tools[1:]) if len(con_tools) > 1 else con_tools[0]

    return factory


def enable_tracing_from_env_file() -> bool:
    """LangChain lee LANGSMITH_* de os.environ, no de .env: los copia si están en .env."""
    try:
        from dotenv import dotenv_values
    except ImportError:
        return False
    for clave, valor in dotenv_values(".env").items():
        if clave.startswith("LANGSMITH_") and valor and clave not in os.environ:
            os.environ[clave] = valor
    return os.environ.get("LANGSMITH_TRACING", "").lower() == "true" and bool(
        os.environ.get("LANGSMITH_API_KEY")
    )


def play_turn(
    game: CoachGame,
    motor: MotorFn,
    *,
    move: str | None = None,
    question: str | None = None,
    llm_factory: Callable[[list[BaseTool]], BaseChatModel] | None = None,
    classifier=None,
    retriever=None,
    trace_metadata: dict | None = None,
    comment_errors: bool = True,
) -> TurnResult:
    if bool(move) == bool(question):
        raise ValueError("Un turno es una jugada O una pregunta")
    grafo = build_graph(game, motor, llm_factory or default_llm_factory(), classifier, retriever)
    estado = grafo.invoke(
        {"jugada": move, "pregunta": question, "comentar": comment_errors, "messages": []},
        config={
            "recursion_limit": RECURSION_LIMIT,
            "run_name": "coach · " + ("jugada" if move else "pregunta"),
            "tags": ["chesstrack", "coach"],
            "metadata": {
                "user_color": "white" if game.user_color else "black",
                "ply": game.board.ply(),
                **(trace_metadata or {}),
            },  # fmt: skip
        },
    )
    final = respuesta_final(estado)
    texto = normalizar_citas(final.content) if final else None
    if texto:
        # En el historial va la pregunta corta, no el análisis entero (ahorra tokens).
        informe = estado.get("informe_usuario")
        pedido = question or f"¿Qué falló en mi jugada {informe.san if informe else ''}?"
        game.chat += [("user", pedido), ("coach", texto)]
    return TurnResult(
        user_move=estado.get("informe_usuario"),
        coach_move=estado.get("informe_coach"),
        answer=texto,
        model=(final.response_metadata.get("model_name") if final else None),
        error=estado.get("error"),
        result=game.result(),
        sources=fuentes_citadas(texto, estado["messages"]) if texto else [],
        llm_error=estado.get("llm_error"),
    )
