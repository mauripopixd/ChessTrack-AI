"""Responde preguntas de teoría de aperturas con fuentes citadas (RAG).

1. Busca los k fragmentos más parecidos a la pregunta (app/rag/index.py).
2. Se los da al LLM numerados [1]…[k], con la instrucción de responder SOLO con ellos y
   citar cada afirmación con [n].
3. Convierte las marcas [n] de la respuesta en citas con título, URL y licencia.

Sin el paso 1, un modelo pequeño inventa (probado: Qwen 9B dijo que la Siciliana es
"1.d4 c5"). Con él, cada afirmación es comprobable en su fuente.
"""

import re
from dataclasses import dataclass, field
from typing import Protocol

from app.rag.hits import Hit
from app.rag.llm import LLMClient, LLMUnavailableError

SYSTEM = """Eres el coach de ajedrez de ChessTrack AI y respondes preguntas sobre aperturas.

Reglas:
- Responde SOLO con la información de las fuentes numeradas que te doy. No uses lo que sepas por tu cuenta.
- Cita cada afirmación con el número de su fuente entre corchetes, por ejemplo [1] o [2][3].
- Si las fuentes no bastan para responder, dilo claramente en vez de completar con suposiciones.
- Responde en español (di "blancas" y "negras", no "White" y "Black"), en 120 palabras como
  máximo, sin títulos.
- Escribe las jugadas en notación algebraica inglesa (SAN), exactamente como aparecen en las fuentes.
- Las fuentes de Lichess son fichas de catálogo (nombre, código ECO y jugadas); las de Wikibooks
  explican ideas y planes."""

# Reescritura de la consulta (opcional, DESACTIVADA por defecto): el LLM traduce la pregunta
# a una búsqueda en inglés con nombres de apertura y jugadas. Medido con
# scripts/eval_retrieval.py --rewrite: arregla "Gambito de Dama aceptado" pero rompe otras 4
# (p. ej. reescribe la India de Rey como "Queen's Indian"): acierto@5 baja de 95 % a 80 %.
REESCRITURA = """Convierte la pregunta de ajedrez en una consulta de búsqueda EN INGLÉS para un libro de
teoría de aperturas. Incluye el nombre inglés estándar de la apertura o variante y sus jugadas
en SAN si las conoces. Responde SOLO con la consulta, en una línea, sin explicaciones."""

SIN_FUENTES = "No encontré teoría sobre eso en mis fuentes (Wikibooks y Lichess)."
_CITA = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")


class Retriever(Protocol):
    def search(self, pregunta: str, k: int = 5) -> list[Hit]: ...


@dataclass(frozen=True)
class Citation:
    n: int
    title: str
    url: str
    license: str
    source: str
    name: str | None
    eco: str | None
    moves: str


@dataclass(frozen=True)
class Answer:
    question: str
    text: str
    citations: list[Citation]
    provider: str | None
    model: str | None
    latency_ms: int | None
    invalid_citations: list[int] = field(default_factory=list)  # [n] que no existen: alucinación
    retrieved: list[Hit] = field(default_factory=list)


def citas_en(texto: str) -> list[int]:
    """Números citados, en orden de aparición y sin repetir: "[1] … [2, 3] … [1]" → [1, 2, 3]."""
    vistos: list[int] = []
    for grupo in _CITA.findall(texto):
        for n in (int(x) for x in grupo.split(",")):
            if n not in vistos:
                vistos.append(n)
    return vistos


def contexto(hits: list[Hit]) -> str:
    return "\n\n".join(
        f"[{i}] {h.title} · {h.source} ({h.license})\n{h.text}" for i, h in enumerate(hits, start=1)
    )


class OpeningAssistant:
    def __init__(self, retriever: Retriever, llm: LLMClient, k: int = 6, rewrite: bool = False) -> None:
        self.retriever = retriever
        self.llm = llm
        self.k = k
        self.rewrite = rewrite

    def buscar(self, pregunta: str) -> list[Hit]:
        """Fragmentos para la pregunta. Con `rewrite`, busca también con la versión que propone
        el LLM (en inglés, con nombres de apertura y jugadas) y combina: de cada fragmento se
        queda la mejor similitud, y se devuelven los k mejores."""
        hits = self.retriever.search(pregunta, k=self.k)
        if not self.rewrite:
            return hits
        try:
            consulta = self.llm.complete(REESCRITURA, pregunta, max_tokens=300).text.strip()
        except LLMUnavailableError:
            return hits  # sin LLM no hay reescritura, pero la búsqueda normal sigue valiendo
        mejores = {h.id: h for h in hits}
        for h in self.retriever.search(consulta, k=self.k):
            if h.id not in mejores or h.score > mejores[h.id].score:
                mejores[h.id] = h
        return sorted(mejores.values(), key=lambda h: h.score, reverse=True)[: self.k]

    def ask(self, pregunta: str) -> Answer:
        hits = self.buscar(pregunta)
        if not hits:
            return Answer(pregunta, SIN_FUENTES, [], None, None, None)
        respuesta = self.llm.complete(SYSTEM, f"Fuentes:\n\n{contexto(hits)}\n\nPregunta: {pregunta}")
        citadas = citas_en(respuesta.text)
        validas = [n for n in citadas if 1 <= n <= len(hits)]
        return Answer(
            question=pregunta,
            text=respuesta.text,
            citations=[
                Citation(
                    n=n,
                    title=hits[n - 1].title,
                    url=hits[n - 1].url,
                    license=hits[n - 1].license,
                    source=hits[n - 1].source,
                    name=hits[n - 1].name,
                    eco=hits[n - 1].eco,
                    moves=hits[n - 1].moves,
                )  # fmt: skip
                for n in validas
            ],
            provider=respuesta.provider,
            model=respuesta.model,
            latency_ms=respuesta.latency_ms,
            invalid_citations=[n for n in citadas if n not in validas],
            retrieved=hits,
        )
