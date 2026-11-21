"""Motor de SQLAlchemy, sesiones y clase base de los modelos."""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

# Nombres fijos para índices y restricciones: así Alembic genera migraciones
# estables y los errores de la BD dicen qué regla se rompió (p. ej. uq_users_email).
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


@lru_cache
def get_engine() -> Engine:
    # pool_pre_ping: descarta conexiones muertas (p. ej. si se reinicia el contenedor).
    # connect_timeout: si la BD no responde, fallar en 5 s en vez de colgarse.
    return create_engine(get_settings().database_url, pool_pre_ping=True, connect_args={"connect_timeout": 5})


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """Una sesión por petición; FastAPI la usará con Depends(get_session)."""
    with get_session_factory()() as session:
        yield session
