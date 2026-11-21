"""Resultado de una búsqueda en el índice. Módulo aparte y sin dependencias pesadas:
el asistente y la API lo usan sin tener que importar chromadb ni sentence-transformers."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Hit:
    id: str
    text: str
    source: str
    title: str
    url: str
    moves: str
    name: str | None
    eco: str | None
    license: str
    score: float  # similitud coseno (1 = idéntico)
