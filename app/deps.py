"""Dependencias compartidas de FastAPI (se inyectan con Depends).

Aquí se "cablea" la aplicación: sesión → repositorio SQL → service. Es el único
sitio que decide qué implementación concreta usa cada capa; los routers piden un
service y los services piden un repositorio (Protocol), sin saber cuál es.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import User
from app.repositories.games import SqlGameRepository
from app.repositories.users import SqlUserRepository, UserRepository
from app.security import InvalidTokenError, decode_access_token
from app.services.auth import AuthService
from app.services.games import GameService

# tokenUrl: dónde pide el token el botón "Authorize" de la documentación (/docs).
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

SessionDep = Annotated[Session, Depends(get_session)]


def get_user_repository(session: SessionDep) -> UserRepository:
    return SqlUserRepository(session)


UserRepositoryDep = Annotated[UserRepository, Depends(get_user_repository)]


def get_auth_service(users: UserRepositoryDep) -> AuthService:
    return AuthService(users)


def get_game_service(session: SessionDep) -> GameService:
    return GameService(SqlGameRepository(session))


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
GameServiceDep = Annotated[GameService, Depends(get_game_service)]

_NO_AUTENTICADO = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Token inválido o caducado",
    headers={"WWW-Authenticate": "Bearer"},  # lo exige el estándar para 401 con Bearer
)


def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], users: UserRepositoryDep) -> User:
    """Usuario dueño del token. 401 si falta, es inválido, caducó o el usuario ya no existe."""
    try:
        user_id = decode_access_token(token)
    except InvalidTokenError:
        raise _NO_AUTENTICADO from None
    user = users.get(user_id)
    if user is None:
        raise _NO_AUTENTICADO
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
