"""Acceso a la tabla users."""

from typing import Protocol

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import DuplicateUserError
from app.models import User

# Nombre de la restricción de la BD → campo repetido (ver naming convention en app/db.py).
_DUPLICADOS = {"uq_users_email": "email", "uq_users_username": "username"}


class UserRepository(Protocol):
    def get(self, user_id: int) -> User | None: ...

    def get_by_login(self, identifier: str) -> User | None:
        """Busca por username o email (ya normalizados a minúsculas)."""
        ...

    def create(self, user: User) -> User:
        """Guarda el usuario. Lanza DuplicateUserError si el email o el username existen."""
        ...


class SqlUserRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, user_id: int) -> User | None:
        return self.session.get(User, user_id)

    def get_by_login(self, identifier: str) -> User | None:
        return self.session.scalars(
            select(User).where(or_(User.username == identifier, User.email == identifier))
        ).first()

    def create(self, user: User) -> User:
        self.session.add(user)
        try:
            self.session.commit()
        except IntegrityError as e:
            # Decide la BD en vez de consultar antes: así no hay carrera entre dos
            # registros simultáneos con el mismo email.
            self.session.rollback()
            campo = _DUPLICADOS.get(getattr(e.orig.diag, "constraint_name", None))
            if campo is None:
                raise
            raise DuplicateUserError(campo) from None
        return user
