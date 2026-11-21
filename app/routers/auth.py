"""Registro e inicio de sesión. Solo traduce HTTP ↔ AuthService."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.deps import AuthServiceDep
from app.errors import DuplicateUserError, InvalidCredentialsError
from app.models import User
from app.schemas import Token, UserCreate, UserRead

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(data: UserCreate, auth: AuthServiceDep) -> User:
    try:
        return auth.register(data)
    except DuplicateUserError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None


@router.post("/login", response_model=Token)
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], auth: AuthServiceDep) -> Token:
    """Formulario OAuth2 estándar: `username` acepta el username o el email."""
    try:
        user = auth.authenticate(form.username, form.password)
    except InvalidCredentialsError:
        # Mismo mensaje en ambos casos: no revela si el usuario existe.
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Usuario o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    return auth.issue_token(user)
