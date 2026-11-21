"""Dependencias compartidas de FastAPI (se inyectan con Depends)."""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import User
from app.security import InvalidTokenError, decode_access_token

# tokenUrl: dónde pide el token el botón "Authorize" de la documentación (/docs).
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

SessionDep = Annotated[Session, Depends(get_session)]

_NO_AUTENTICADO = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Token inválido o caducado",
    headers={"WWW-Authenticate": "Bearer"},  # lo exige el estándar para 401 con Bearer
)


def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], session: SessionDep) -> User:
    """Usuario dueño del token. 401 si falta, es inválido, caducó o el usuario ya no existe."""
    try:
        user_id = decode_access_token(token)
    except InvalidTokenError:
        raise _NO_AUTENTICADO from None
    user = session.get(User, user_id)
    if user is None:
        raise _NO_AUTENTICADO
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
