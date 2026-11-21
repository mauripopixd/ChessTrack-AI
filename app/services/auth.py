"""Registro, login y tokens. Sin SQL ni HTTP: habla con un UserRepository."""

from app.config import get_settings
from app.errors import InvalidCredentialsError
from app.models import User
from app.repositories.users import UserRepository
from app.schemas import Token, UserCreate
from app.security import create_access_token, hash_password, verify_password


class AuthService:
    def __init__(self, users: UserRepository) -> None:
        self.users = users

    def register(self, data: UserCreate) -> User:
        """Lanza DuplicateUserError si el email o el username ya existen."""
        user = User(email=data.email, username=data.username, hashed_password=hash_password(data.password))
        return self.users.create(user)

    def authenticate(self, identifier: str, password: str) -> User:
        """`identifier` es el username o el email. Lanza InvalidCredentialsError."""
        user = self.users.get_by_login(identifier.strip().lower())
        # verify_password con None tarda lo mismo que con un hash real: el tiempo de
        # respuesta no revela si el usuario existe.
        if not verify_password(password, user.hashed_password if user else None):
            raise InvalidCredentialsError
        return user

    def issue_token(self, user: User) -> Token:
        minutos = get_settings().access_token_expire_minutes
        return Token(access_token=create_access_token(user.id), expires_in=minutos * 60)
