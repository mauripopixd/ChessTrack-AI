"""Fixtures de BD: PostgreSQL real (TEST_DATABASE_URL), no SQLite.

- Al empezar, la BD de pruebas se vacía y se crea con `alembic upgrade head`,
  así cada ejecución prueba también las migraciones.
- Cada test corre dentro de una transacción que se deshace al final:
  los tests no se ensucian entre sí y no hace falta borrar nada.
- Si no hay BD configurada o no responde, estos tests se saltan con el motivo.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.config import get_settings

ROOT = Path(__file__).resolve().parents[2]


def _test_url() -> str | None:
    try:
        return get_settings().test_database_url
    except ValidationError:  # sin .env ni variables de entorno
        return None


def alembic_config(url: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.attributes["configure_logger"] = False  # no tocar el logging de pytest
    return cfg


@pytest.fixture(scope="session")
def db_url() -> str:
    url = _test_url()
    if not url:
        pytest.skip("TEST_DATABASE_URL no está definida (copia .env.example a .env)")
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
        pytest.skip(f"PostgreSQL de pruebas no responde ({db_url.split('@')[-1]}): "
                    f"¿está corriendo 'docker compose up -d'? Detalle: {e.orig}")
    command.upgrade(alembic_config(db_url), "head")
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with engine.connect() as conn:
        trans = conn.begin()
        # Los commit/rollback del código bajo prueba usan SAVEPOINTs dentro de
        # esta transacción, que se deshace entera al terminar el test.
        with Session(bind=conn, join_transaction_mode="create_savepoint") as s:
            yield s
        trans.rollback()
