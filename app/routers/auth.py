"""Registro e inicio de sesión."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.deps import SessionDep
from app.models import User
from app.schemas import Token, UserCreate, UserRead
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

# Nombre de la restricción de la BD → campo repetido (ver naming convention en app/db.py).
_DUPLICADOS = {"uq_users_email": "email", "uq_users_username": "username"}


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(data: UserCreate, session: SessionDep) -> User:
    user = User(email=data.email, username=data.username, hashed_password=hash_password(data.password))
    session.add(user)
    try:
        session.commit()
    except IntegrityError as e:
        # Se deja decidir a la BD en vez de consultar antes: así no hay carrera
        # entre dos registros simultáneos con el mismo email.
        session.rollback()
        campo = _DUPLICADOS.get(getattr(e.orig.diag, "constraint_name", None))
        if campo is None:
            raise
        raise HTTPException(status.HTTP_409_CONFLICT, f"Ya existe un usuario con ese {campo}") from None
    session.refresh(user)
    return user


@router.post("/login", response_model=Token)
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], session: SessionDep) -> Token:
    """Formulario OAuth2 estándar: `username` acepta el username o el email."""
    identificador = form.username.strip().lower()
    user = session.scalars(
        select(User).where(or_(User.username == identificador, User.email == identificador))
    ).first()
    if not verify_password(form.password, user.hashed_password if user else None):
        # Mismo mensaje en ambos casos: no revela si el usuario existe.
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Usuario o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    minutos = get_settings().access_token_expire_minutes
    return Token(access_token=create_access_token(user.id), expires_in=minutos * 60)
