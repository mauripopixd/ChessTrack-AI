"""Aplicación FastAPI.

Arranque en desarrollo (con Docker Desktop abierto y `docker compose up -d`):

    uvicorn app.main:app --reload

Documentación interactiva en http://127.0.0.1:8000/docs
"""

from fastapi import FastAPI, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.deps import SessionDep
from app.routers import auth, games, users


def create_app() -> FastAPI:
    app = FastAPI(
        title="ChessTrack AI",
        description="Coach de ajedrez con IA. Capa 1: API de partidas.",
        version="0.1.0",
    )
    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(games.router)

    @app.get("/health", tags=["health"])
    def health(session: SessionDep) -> dict[str, str]:
        """200 si la API y la BD responden; 503 si la BD no. Lo usará Docker en la Etapa 2."""
        try:
            session.execute(text("SELECT 1"))
        except OperationalError:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Base de datos no disponible") from None
        return {"status": "ok", "database": "ok"}

    return app


app = create_app()
