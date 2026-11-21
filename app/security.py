"""Contraseñas (Argon2) y tokens de acceso (JWT).

- Argon2id es el algoritmo recomendado por OWASP para guardar contraseñas:
  es lento a propósito y usa mucha memoria, lo que encarece los ataques con GPU.
- El JWT lleva el id del usuario en `sub` y caduca (`exp`). Va firmado con
  JWT_SECRET_KEY: quien no tenga la clave no puede fabricar ni modificar uno.
"""

from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash

from app.config import get_settings

_password_hash = PasswordHash.recommended()  # Argon2id con parámetros por defecto seguros
# Hash de una contraseña cualquiera: se verifica contra él cuando el usuario no existe,
# para que el login tarde lo mismo y no revele qué usuarios están registrados.
_DUMMY_HASH = _password_hash.hash("contraseña-ficticia-para-igualar-tiempos")


class InvalidTokenError(Exception):
    """Token ausente, mal formado, con firma inválida o caducado."""


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, hashed: str | None) -> bool:
    """Compara en tiempo constante. Con `hashed=None` (usuario inexistente) siempre es False."""
    if hashed is None:
        _password_hash.verify(password, _DUMMY_HASH)
        return False
    return _password_hash.verify(password, hashed)


def create_access_token(user_id: int, expires_in: timedelta | None = None) -> str:
    settings = get_settings()
    ahora = datetime.now(UTC)
    if expires_in is None:
        expires_in = timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": str(user_id), "iat": ahora, "exp": ahora + expires_in}
    return jwt.encode(payload, settings.jwt_secret_key.get_secret_value(), algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> int:
    """Devuelve el id del usuario o lanza InvalidTokenError."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key.get_secret_value(),
            # Lista explícita: impide el ataque de cambiar el algoritmo a "none".
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "exp"]},
        )
        return int(payload["sub"])
    except (jwt.PyJWTError, ValueError) as e:
        raise InvalidTokenError(str(e)) from e
