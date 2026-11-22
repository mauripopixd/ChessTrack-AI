"""Fixtures compartidas: BD PostgreSQL real (TEST_DATABASE_URL, no SQLite) y cliente HTTP.

- Al empezar, la BD de pruebas se vacía y se crea con `alembic upgrade head`,
  así cada ejecución prueba también las migraciones.
- Cada test corre dentro de una transacción que se deshace al final:
  los tests no se ensucian entre sí y no hace falta borrar nada.
- Si no hay BD configurada o no responde, los tests que la usan se saltan con el motivo
  (o fallan, con REQUIRE_DB=1, como en el CI).
"""

import os

# Clave fija para los tests, antes de que nada lea la configuración: las variables
# de entorno tienen prioridad sobre .env, así los tests no dependen de tu clave real.
os.environ["JWT_SECRET_KEY"] = "clave-solo-para-tests-" + "x" * 32
# Sin trazas en LangSmith durante los tests (la app las activa si LANGSMITH_* están en .env).
os.environ["LANGSMITH_TRACING"] = "false"

from collections.abc import Iterator  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from pydantic import ValidationError  # noqa: E402
from sqlalchemy import Engine, create_engine, text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import get_session  # noqa: E402
from app.main import create_app  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _test_url() -> str | None:
    try:
        return get_settings().test_database_url
    except ValidationError:  # sin .env ni variables de entorno
        return None


def _sin_bd(motivo: str) -> None:
    """En local, saltar los tests de BD con el motivo. En CI (REQUIRE_DB=1), fallar:
    si no, un CI sin base de datos saldría en verde con todos los tests de BD y API saltados."""
    if os.environ.get("REQUIRE_DB") == "1":
        pytest.fail(f"REQUIRE_DB=1 y no hay BD de pruebas: {motivo}", pytrace=False)
    pytest.skip(motivo)


def alembic_config(url: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.attributes["configure_logger"] = False  # no tocar el logging de pytest
    return cfg


@pytest.fixture(autouse=True)
def _limites_a_cero() -> Iterator[None]:
    """Los límites de intentos (app/ratelimit.py) viven en memoria: cada test empieza de cero."""
    from app.ratelimit import LOGIN, REGISTER

    LOGIN.reset()
    REGISTER.reset()
    yield


@pytest.fixture(scope="session")
def db_url() -> str:
    url = _test_url()
    if not url:
        _sin_bd("TEST_DATABASE_URL no está definida (copia .env.example a .env)")
    return url


@pytest.fixture(scope="session")
def engine(db_url: str) -> Iterator[Engine]:
    # connect_timeout: sin él, Windows reintenta un puerto cerrado durante minutos.
    eng = create_engine(db_url, connect_args={"connect_timeout": 3})
    try:
        with eng.begin() as conn:
            # Empezar desde una BD vacía, como pide el checkpoint de la Etapa 1.
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
    except OperationalError as e:
        _sin_bd(
            f"PostgreSQL de pruebas no responde ({db_url.split('@')[-1]}): "
            f"¿está corriendo 'docker compose up -d'? Detalle: {e.orig}"
        )
    command.upgrade(alembic_config(db_url), "head")
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with engine.connect() as conn:
        trans = conn.begin()
        # Los commit/rollback del código bajo prueba usan SAVEPOINTs dentro de
        # esta transacción, que se deshace entera al terminar el test.
        # expire_on_commit=False, igual que la sesión de la app (app/db.py).
        with Session(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False) as s:
            yield s
        trans.rollback()


@pytest.fixture
def client(session: Session) -> Iterator[TestClient]:
    """Cliente HTTP contra la app, usando la sesión del test (sus cambios se deshacen al final)."""
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as c:
        yield c
