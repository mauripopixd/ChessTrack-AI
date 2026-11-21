"""Configuración leída de variables de entorno (o de un archivo .env en la raíz).

Los secretos nunca van en el código: copia `.env.example` a `.env` y ajústalo.
"""

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str
    # BD aparte para los tests: se borra y recrea en cada ejecución.
    test_database_url: str | None = None

    # Firma de los JWT. SecretStr evita que aparezca en logs o en repr().
    # Mínimo 32 caracteres: con HS256, una clave corta se puede adivinar por fuerza bruta.
    jwt_secret_key: SecretStr = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=60, gt=0)


@lru_cache
def get_settings() -> Settings:
    return Settings()
