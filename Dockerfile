# Imagen de la API. La construye y arranca docker-compose.yml (servicios `migrate` y `api`).
#   docker build -t chesstrack-api .
FROM python:3.13-slim

# Sin .pyc dentro del contenedor y logs sin búfer (se ven al momento en `docker compose logs`).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Las dependencias van antes que el código: si solo cambia el código, Docker reutiliza
# esta capa y no reinstala nada (builds de segundos en vez de minutos).
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY alembic.ini .
COPY migrations ./migrations
COPY app ./app

# No correr como root: si alguien explotara la API, no tendría privilegios en el contenedor.
RUN useradd --create-home --uid 1000 app
USER app

EXPOSE 8000

# Docker marca el contenedor como "healthy" cuando /health responde (API y BD funcionando).
HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
