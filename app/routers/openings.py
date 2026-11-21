"""Preguntas de teoría de aperturas respondidas con fuentes citadas (RAG, Etapa 5A)."""

from fastapi import APIRouter, HTTPException, status

from app.deps import CurrentUser, OpeningAssistantDep
from app.rag.assistant import Answer
from app.rag.llm import LLMUnavailableError
from app.schemas import AskRequest, AskResponse, CitationRead

router = APIRouter(prefix="/openings", tags=["openings"])


def _respuesta(a: Answer) -> AskResponse:
    return AskResponse(
        question=a.question,
        answer=a.text,
        citations=[
            CitationRead(
                n=c.n,
                title=c.title,
                url=c.url,
                license=c.license,
                source=c.source,
                opening=c.name,
                eco=c.eco,
                moves=c.moves,
            )  # fmt: skip
            for c in a.citations
        ],
        provider=a.provider,
        model=a.model,
        latency_ms=a.latency_ms,
        invalid_citations=a.invalid_citations,
    )


@router.post(
    "/ask",
    response_model=AskResponse,
    responses={503: {"description": "Índice del RAG sin construir o ningún LLM disponible"}},
)
def ask(data: AskRequest, user: CurrentUser, assistant: OpeningAssistantDep) -> AskResponse:
    """Responde una pregunta sobre aperturas citando Wikibooks y Lichess. Pide sesión
    iniciada: el LLM gratuito tiene un límite diario compartido y no debe gastarlo cualquiera."""
    try:
        return _respuesta(assistant.ask(data.question))
    except LLMUnavailableError as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"Ningún LLM disponible: {e}") from None
