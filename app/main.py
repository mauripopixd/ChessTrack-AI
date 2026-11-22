"""Aplicación FastAPI.

Arranque en desarrollo (con Docker Desktop abierto y `docker compose up -d`):

    uvicorn app.main:app --reload

Documentación interactiva en http://127.0.0.1:8000/docs
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.coach.session import enable_tracing_from_env_file
from app.deps import SessionDep, get_engine_pool
from app.routers import auth, coach, games, openings, users


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Trazas del coach en LangSmith si LANGSMITH_* están en .env (LangChain solo mira os.environ).
    enable_tracing_from_env_file()
    yield
    # Al apagar: cerrar los Stockfish abiertos (si se llegó a crear el pool), sin dejar huérfanos.
    if get_engine_pool.cache_info().currsize:
        get_engine_pool().close()


def create_app() -> FastAPI:
    app = FastAPI(
        title="ChessTrack AI",
        description="Coach de ajedrez con IA: partidas, análisis con Stockfish, clasificador de errores, "
        "RAG de aperturas y un coach contra el que jugar.",
        version="0.3.0",
        lifespan=lifespan,
    )
    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(games.router)
    app.include_router(openings.router)
    app.include_router(coach.router)

    @app.get("/health", tags=["health"])
    def health(session: SessionDep) -> dict[str, str]:
        """200 si la API y la BD responden; 503 si la BD no. Lo usa el HEALTHCHECK de Docker."""
        try:
            session.execute(text("SELECT 1"))
        except OperationalError:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Base de datos no disponible") from None
        return {"status": "ok", "database": "ok"}

    return app


app = create_app()
