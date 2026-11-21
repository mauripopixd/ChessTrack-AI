"""AuthService sin base de datos: repositorio en memoria (tests/fakes.py)."""

import pytest

from app.errors import DuplicateUserError, InvalidCredentialsError
from app.schemas import UserCreate
from app.security import decode_access_token
from app.services.auth import AuthService
from tests.fakes import InMemoryUserRepository

DATOS = UserCreate(email="Weytey@Example.com", username="Weytey", password="contraseña-segura")


@pytest.fixture
def auth() -> AuthService:
    return AuthService(InMemoryUserRepository())


def test_registro_guarda_hash_no_contraseña(auth):
    user = auth.register(DATOS)
    assert (user.email, user.username) == ("weytey@example.com", "weytey")  # normaliza el schema
    assert user.hashed_password.startswith("$argon2id$")
    assert "contraseña-segura" not in user.hashed_password


@pytest.mark.parametrize(
    ("cambio", "campo"), [({"username": "otro"}, "email"), ({"email": "otro@example.com"}, "username")]
)
def test_registro_duplicado(auth, cambio, campo):
    auth.register(DATOS)
    with pytest.raises(DuplicateUserError) as exc:
        auth.register(DATOS.model_copy(update=cambio))
    assert exc.value.field == campo


@pytest.mark.parametrize("identificador", ["weytey", " WEYTEY ", "weytey@example.com"])
def test_autentica_con_username_o_email(auth, identificador):
    user = auth.register(DATOS)
    assert auth.authenticate(identificador, "contraseña-segura") is user


@pytest.mark.parametrize(("identificador", "password"), [("weytey", "mala"), ("nadie", "contraseña-segura")])
def test_credenciales_incorrectas(auth, identificador, password):
    auth.register(DATOS)
    with pytest.raises(InvalidCredentialsError):
        auth.authenticate(identificador, password)


def test_token_lleva_el_id_del_usuario(auth):
    user = auth.register(DATOS)
    token = auth.issue_token(user)
    assert decode_access_token(token.access_token) == user.id
    assert token.token_type == "bearer"
