"""Dependencias compartidas de FastAPI (se inyectan con Depends).

Aquí se "cablea" la aplicación: sesión → repositorio SQL → service. Es el único
sitio que decide qué implementación concreta usa cada capa; los routers piden un
service y los services piden un repositorio (Protocol), sin saber cuál es.
"""

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.analysis import find_stockfish
from app.coach.session import default_llm_factory
from app.coach.tools import MotorFn
from app.config import get_settings
from app.db import get_session
from app.engine import EnginePool
from app.ml.classifier import ErrorClassifier
from app.models import User
from app.rag.assistant import OpeningAssistant
from app.rag.hits import Hit
from app.rag.llm import LLMClient, groq, ollama
from app.repositories.coach import SqlCoachRepository
from app.repositories.games import SqlGameRepository
from app.repositories.users import SqlUserRepository, UserRepository
from app.security import InvalidTokenError, decode_access_token
from app.services.analysis import AnalysisService, Analyzer, StockfishAnalyzer
from app.services.auth import AuthService
from app.services.coach import CoachService
from app.services.games import GameService

# tokenUrl: dónde pide el token el botón "Authorize" de la documentación (/docs).
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

SessionDep = Annotated[Session, Depends(get_session)]


def get_user_repository(session: SessionDep) -> UserRepository:
    return SqlUserRepository(session)


UserRepositoryDep = Annotated[UserRepository, Depends(get_user_repository)]


def get_auth_service(users: UserRepositoryDep) -> AuthService:
    return AuthService(users)


def get_game_service(session: SessionDep) -> GameService:
    return GameService(SqlGameRepository(session))


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
GameServiceDep = Annotated[GameService, Depends(get_game_service)]


@lru_cache
def get_engine_pool() -> EnginePool:
    """Uno para toda la API (lru_cache): los motores se reutilizan entre peticiones."""
    settings = get_settings()
    return EnginePool(settings.stockfish_path or find_stockfish(), settings.engine_pool_size)


@lru_cache
def get_classifier() -> ErrorClassifier | None:
    """Se carga una vez (el Random Forest pesa ~110 MB); None si no hay modelo entrenado."""
    return ErrorClassifier.load(get_settings().classifier_path)


def get_analyzer() -> Analyzer:
    return StockfishAnalyzer(get_engine_pool(), get_settings().analysis_depth)


def get_analysis_service(
    session: SessionDep,
    analyzer: Annotated[Analyzer, Depends(get_analyzer)],
    classifier: Annotated[ErrorClassifier | None, Depends(get_classifier)],
) -> AnalysisService:
    return AnalysisService(SqlGameRepository(session), analyzer, classifier)


AnalysisServiceDep = Annotated[AnalysisService, Depends(get_analysis_service)]

_NO_AUTENTICADO = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Token inválido o caducado",
    headers={"WWW-Authenticate": "Bearer"},  # lo exige el estándar para 401 con Bearer
)


def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], users: UserRepositoryDep) -> User:
    """Usuario dueño del token. 401 si falta, es inválido, caducó o el usuario ya no existe."""
    try:
        user_id = decode_access_token(token)
    except InvalidTokenError:
        raise _NO_AUTENTICADO from None
    user = users.get(user_id)
    if user is None:
        raise _NO_AUTENTICADO
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


class RAGUnavailableError(Exception):
    """Falta el índice (scripts/build_rag_index.py) o sus dependencias."""


def build_llm_client() -> LLMClient:
    settings = get_settings()
    proveedores = []
    if settings.groq_api_key:
        proveedores.append(groq(settings.groq_api_key.get_secret_value(), settings.groq_model))
    if settings.ollama_model:
        proveedores.append(ollama(settings.ollama_model, settings.ollama_url))
    return LLMClient(proveedores)


@lru_cache
def get_opening_assistant() -> OpeningAssistant:
    """Uno para toda la API: cargar el modelo de embeddings (bge-m3, ~2 GB) tarda segundos."""
    settings = get_settings()
    indice = Path(settings.rag_index_dir)
    if not indice.exists():
        raise RAGUnavailableError(f"No hay índice en {indice}: ejecuta python -m scripts.build_rag_index")
    try:
        # Import aquí: sentence-transformers y chromadb solo hacen falta si se usa el RAG.
        import torch

        from app.rag.index import OpeningIndex
    except ImportError as e:
        raise RAGUnavailableError(f"Faltan dependencias del RAG ({e.name}): requirements-analysis.txt") from e
    dispositivo = "cuda" if torch.cuda.is_available() else "cpu"
    return OpeningAssistant(
        OpeningIndex(indice, device=dispositivo), build_llm_client(), k=settings.rag_top_k
    )


def _assistant_dep() -> OpeningAssistant:
    try:
        return get_opening_assistant()
    except (RAGUnavailableError, ValueError) as e:  # ValueError: ningún proveedor de LLM configurado
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from None


OpeningAssistantDep = Annotated[OpeningAssistant, Depends(_assistant_dep)]


# ---------------------------------------------------------------- coach (Etapa 5B)


def get_coach_motor() -> MotorFn:
    """Un Stockfish del pool por cada uso (jugada del coach, evaluación de una herramienta…)."""
    return get_engine_pool().engine


def get_coach_llm_factory():
    """Groq gratis → Ollama, con las herramientas de cada partida (app/coach/session.py)."""
    return default_llm_factory()


class LazyOpeningRetriever:
    """El RAG solo se carga (bge-m3, unos segundos y ~2 GB) la primera vez que el coach busca
    teoría, no en cada jugada. Si no está disponible, la herramienta se lo dice al LLM."""

    def search(self, pregunta: str, k: int = 5, source: str | None = None) -> list[Hit]:
        try:
            retriever = get_opening_assistant().retriever
        except RAGUnavailableError as e:
            raise RuntimeError(f"La teoría de aperturas no está disponible: {e}") from None
        return retriever.search(pregunta, k=k, source=source)


def get_coach_retriever():
    return LazyOpeningRetriever()


def get_coach_service(
    session: SessionDep,
    motor: Annotated[MotorFn, Depends(get_coach_motor)],
    llm_factory: Annotated[object, Depends(get_coach_llm_factory)],
    retriever: Annotated[object, Depends(get_coach_retriever)],
    classifier: Annotated[ErrorClassifier | None, Depends(get_classifier)],
) -> CoachService:
    return CoachService(
        SqlCoachRepository(session), motor, llm_factory, classifier=classifier, retriever=retriever,
        answers_per_hour=get_settings().coach_answers_per_hour,
    )  # fmt: skip


CoachServiceDep = Annotated[CoachService, Depends(get_coach_service)]
