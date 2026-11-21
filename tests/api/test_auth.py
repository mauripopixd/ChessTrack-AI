from datetime import timedelta

import jwt
import pytest
from sqlalchemy import delete, select

from app.config import get_settings
from app.models import User
from app.security import create_access_token, hash_password, verify_password

USUARIO = {"email": "Weytey@Example.com", "username": "Weytey", "password": "contraseña-segura"}


def registrar(client, **cambios):
    return client.post("/auth/register", json={**USUARIO, **cambios})


def login(client, username="weytey", password=USUARIO["password"]):
    # OAuth2 exige formulario (form-data), no JSON.
    return client.post("/auth/login", data={"username": username, "password": password})


def token_de(client) -> str:
    registrar(client)
    return login(client).json()["access_token"]


def con_token(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------- seguridad (unidad)


def test_hash_no_guarda_la_contraseña_y_se_verifica():
    h = hash_password("secreta123")
    assert "secreta123" not in h
    assert h.startswith("$argon2id$")
    assert verify_password("secreta123", h)
    assert not verify_password("otra-cosa", h)


def test_mismo_password_da_hash_distinto():
    # Cada hash lleva su propia sal aleatoria.
    assert hash_password("secreta123") != hash_password("secreta123")


def test_verify_sin_hash_es_false():
    assert verify_password("loquesea", None) is False


# ---------------------------------------------------------------- health


def test_health(client):
    assert client.get("/health").json() == {"status": "ok", "database": "ok"}


# ---------------------------------------------------------------- registro


def test_registro_devuelve_usuario_sin_contraseña(client, session):
    r = registrar(client)
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "weytey@example.com"  # normalizado a minúsculas
    assert body["username"] == "weytey"
    assert set(body) == {"id", "email", "username", "created_at"}

    user = session.scalars(select(User)).one()
    assert user.hashed_password.startswith("$argon2id$")
    assert USUARIO["password"] not in user.hashed_password


@pytest.mark.parametrize(
    ("cambio", "campo"),
    [
        ({"username": "otro"}, "email"),  # mismo email
        ({"email": "otro@example.com"}, "username"),  # mismo username
        ({"username": "otro", "email": "WEYTEY@example.COM"}, "email"),  # sin distinguir mayúsculas
        ({"email": "otro@example.com", "username": "WEYTEY"}, "username"),
    ],
)
def test_registro_duplicado_da_409(client, cambio, campo):
    assert registrar(client).status_code == 201
    r = registrar(client, **cambio)
    assert r.status_code == 409
    assert campo in r.json()["detail"]


@pytest.mark.parametrize(
    "cambio",
    [
        {"email": "no-es-un-email"},
        {"password": "corta"},
        {"password": "x" * 129},
        {"username": "ab"},
        {"username": "con espacios"},
        {"username": "x" * 51},
    ],
)
def test_registro_con_datos_invalidos_da_422(client, cambio):
    assert registrar(client, **cambio).status_code == 422


# ---------------------------------------------------------------- login


@pytest.mark.parametrize("identificador", ["weytey", "WEYTEY", "weytey@example.com"])
def test_login_con_username_o_email(client, identificador):
    registrar(client)
    r = login(client, username=identificador)
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == get_settings().access_token_expire_minutes * 60


@pytest.mark.parametrize(
    ("username", "password"), [("weytey", "incorrecta"), ("nadie", USUARIO["password"])]
)
def test_login_fallido_da_401_con_el_mismo_mensaje(client, username, password):
    registrar(client)
    r = login(client, username=username, password=password)
    assert r.status_code == 401
    assert r.json()["detail"] == "Usuario o contraseña incorrectos"


# ---------------------------------------------------------------- /users/me


def test_me_con_token(client):
    r = client.get("/users/me", headers=con_token(token_de(client)))
    assert r.status_code == 200
    assert r.json()["username"] == "weytey"


def test_me_sin_token_da_401(client):
    r = client.get("/users/me")
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


EXP_2100 = 4102444800  # 1 ene 2100: un token que no caduca durante el test
CLAVE = lambda: get_settings().jwt_secret_key.get_secret_value()  # noqa: E731

# Cada caso recibe el id REAL del usuario registrado: si usara un id inventado,
# daría 401 por "usuario inexistente" y no probaría lo que dice probar.
TOKENS_INVALIDOS = {
    "basura": lambda uid: "no-es-un-jwt",
    "firma-ajena": lambda uid: jwt.encode({"sub": str(uid), "exp": EXP_2100}, "otra-clave-" + "y" * 32),
    "sin-exp": lambda uid: jwt.encode({"sub": str(uid)}, CLAVE()),
    "sin-sub": lambda uid: jwt.encode({"exp": EXP_2100}, CLAVE()),
    "sub-no-numerico": lambda uid: jwt.encode({"sub": "abc", "exp": EXP_2100}, CLAVE()),
    "alg-none": lambda uid: jwt.encode({"sub": str(uid), "exp": EXP_2100}, None, algorithm="none"),
    "alg-hs512": lambda uid: jwt.encode({"sub": str(uid), "exp": EXP_2100}, CLAVE(), algorithm="HS512"),
}


def test_token_bien_formado_si_funciona(client, session):
    # Control: el mismo jwt.encode con datos correctos sí entra. Si esto fallara,
    # los 401 de abajo no demostrarían nada.
    registrar(client)
    uid = session.scalars(select(User)).one().id
    token = jwt.encode({"sub": str(uid), "exp": EXP_2100}, CLAVE())
    assert client.get("/users/me", headers=con_token(token)).status_code == 200


@pytest.mark.parametrize("caso", TOKENS_INVALIDOS)
def test_me_con_token_invalido_da_401(client, session, caso):
    registrar(client)
    uid = session.scalars(select(User)).one().id
    token = TOKENS_INVALIDOS[caso](uid)
    assert client.get("/users/me", headers=con_token(token)).status_code == 401


def test_me_con_token_caducado_da_401(client, session):
    registrar(client)
    user = session.scalars(select(User)).one()
    caducado = create_access_token(user.id, expires_in=timedelta(seconds=-1))
    assert client.get("/users/me", headers=con_token(caducado)).status_code == 401


def test_me_de_usuario_borrado_da_401(client, session):
    token = token_de(client)
    session.execute(delete(User))
    session.expire_all()
    assert client.get("/users/me", headers=con_token(token)).status_code == 401
