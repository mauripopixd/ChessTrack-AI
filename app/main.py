"""Aplicación FastAPI.

Arranque en desarrollo (con Docker Desktop abierto y `docker compose up -d`):

    uvicorn app.main:app --reload

Documentación interactiva en http://127.0.0.1:8000/docs
"""

import hashlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.coach.session import enable_tracing_from_env_file
from app.deps import SessionDep, get_engine_pool
from app.routers import auth, coach, games, openings, users

WEB = Path(__file__).parent / "web"  # interfaz: HTML + JS sin frameworks (Etapa 6)
# Cabeceras de la portada. La CSP solo deja cargar recursos de este servidor: aunque alguien
# lograra inyectar HTML (p. ej. en una respuesta del LLM), no podría ejecutar scripts de fuera
# ni en línea. frame-ancestors impide meter la página en un iframe (clickjacking).
CABECERAS_WEB = {
    "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; style-src 'self'; "
    "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}


def portada_versionada() -> str:
    """index.html con `?v=<hash>` en app.js y style.css. Si cambian, cambia la URL y el
    navegador descarga la versión nueva: recargar no basta, porque Chrome puede seguir usando
    los archivos que tiene guardados (le pasó a Javier: veía el tablero viejo)."""
    html = (WEB / "index.html").read_text(encoding="utf-8")
    for nombre in ("app.js", "style.css"):
        huella = hashlib.sha256((WEB / nombre).read_bytes()).hexdigest()[:10]
        html = html.replace(f"/static/{nombre}", f"/static/{nombre}?v={huella}")
    return html


class EstaticosSinCacheVieja(StaticFiles):
    """Cada carga pregunta al servidor si el archivo cambió (ETag): si no, responde 304 sin
    reenviarlo. Sin esta cabecera, el navegador decide por su cuenta cuánto tiempo lo guarda."""

    def file_response(self, *args, **kwargs):
        respuesta = super().file_response(*args, **kwargs)
        respuesta.headers["Cache-Control"] = "no-cache"
        return respuesta


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
    app.mount("/static", EstaticosSinCacheVieja(directory=WEB), name="static")
    portada = portada_versionada()

    @app.get("/", include_in_schema=False)
    def web() -> HTMLResponse:
        """La interfaz web: registro, tablero contra el coach y chat."""
        return HTMLResponse(portada, headers={**CABECERAS_WEB, "Cache-Control": "no-cache"})

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
