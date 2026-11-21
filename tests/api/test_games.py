from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.models import Game, Move
from app.pgn_parser import parse_pgn, parse_pgn_many

SAMPLES = Path(__file__).resolve().parents[2] / "data" / "samples"
# Color de weytey en cada muestra (tabla del README).
COLORES = ["white", "black", "black", "white", "black"]


def leer(nombre: str) -> bytes:
    return (SAMPLES / nombre).read_bytes()


def cuenta(client, username: str) -> dict[str, str]:
    """Registra un usuario, hace login y devuelve la cabecera Authorization."""
    password = "contraseña-segura"
    client.post(
        "/auth/register",
        json={"email": f"{username}@example.com", "username": username, "password": password},
    )
    token = client.post("/auth/login", data={"username": username, "password": password}).json()
    return {"Authorization": f"Bearer {token['access_token']}"}


def subir(client, headers, contenido: bytes, nombre="partidas.pgn", **form):
    return client.post("/games", headers=headers, files={"file": (nombre, contenido)}, data=form)


@pytest.fixture
def yo(client):
    return cuenta(client, "weytey")


@pytest.fixture
def otro(client):
    return cuenta(client, "intruso")


# ---------------------------------------------------------------- checkpoint de la Etapa 1


def test_subo_una_partida_real_y_la_recupero_con_jugadas_y_fen(client, yo):
    esperado = parse_pgn(leer("partida1.pgn").decode())

    r = subir(client, yo, leer("partida1.pgn"))
    assert r.status_code == 201
    creada = r.json()["created"][0]
    assert creada["user_color"] == "white"
    assert creada["result"] == "1-0"
    assert creada["move_count"] == len(esperado.moves)
    assert creada["created_at"] is not None

    detalle = client.get(f"/games/{creada['id']}", headers=yo).json()
    assert (detalle["white"], detalle["black"]) == (esperado.white, esperado.black)
    assert datetime.fromisoformat(detalle["played_at"]) == esperado.played_at
    assert parse_pgn(detalle["pgn"]).moves == esperado.moves  # el PGN guardado se vuelve a leer igual

    jugadas = client.get(f"/games/{creada['id']}/moves", headers=yo).json()
    assert [(m["ply"], m["san"], m["uci"], m["fen_after"]) for m in jugadas] == [
        (m.ply, m.san, m.uci, m.fen_after) for m in esperado.moves
    ]


def test_subo_varias_partidas_en_un_archivo(client, yo):
    r = subir(client, yo, leer("varias.pgn"))
    assert r.status_code == 201
    body = r.json()
    assert [g["user_color"] for g in body["created"]] == COLORES
    assert body["duplicates"] == [] and body["errors"] == []
    esperadas = parse_pgn_many(leer("varias.pgn").decode())
    assert [g["move_count"] for g in body["created"]] == [len(g.moves) for g in esperadas]


# ---------------------------------------------------------------- duplicados


def test_subir_otra_vez_no_duplica(client, yo, session):
    primera = subir(client, yo, leer("varias.pgn")).json()["created"]
    r = subir(client, yo, leer("varias.pgn"))
    assert r.status_code == 200  # nada nuevo
    body = r.json()
    assert body["created"] == []
    assert [d["game_id"] for d in body["duplicates"]] == [g["id"] for g in primera]
    assert session.scalar(select(func.count()).select_from(Game)) == 5


def test_misma_partida_repetida_en_el_mismo_archivo(client, yo):
    dos_veces = leer("partida1.pgn") + b"\n\n" + leer("partida1.pgn")
    body = subir(client, yo, dos_veces).json()
    assert len(body["created"]) == 1
    assert body["duplicates"] == [{"index": 1, "game_id": body["created"][0]["id"]}]


def test_cambiar_espacios_no_engaña_al_detector_de_duplicados(client, yo):
    subir(client, yo, leer("partida1.pgn"))
    reformateada = leer("partida1.pgn").replace(b"\n", b"\r\n") + b"\n\n\n"
    body = subir(client, yo, reformateada).json()
    assert body["created"] == [] and len(body["duplicates"]) == 1


# ---------------------------------------------------------------- archivos con errores


def test_partidas_validas_e_invalidas_mezcladas(client, yo):
    mezcla = leer("partida1.pgn") + b"\n\n1. e4 e5 2. Ke3 *\n\n" + leer("partida2.pgn")
    r = subir(client, yo, mezcla)
    assert r.status_code == 201
    body = r.json()
    assert len(body["created"]) == 2
    assert len(body["errors"]) == 1
    assert body["errors"][0]["index"] == 1
    assert "Ke3" in body["errors"][0]["detail"]


@pytest.mark.parametrize(
    ("contenido", "texto"),
    [
        (b"", "vac"),
        (b"   \n\n", "vac"),
        (b"1. e4 e5 2. Ke3 *", "Ke3"),
        (b"hola mundo", "PGN"),
        ("1. e4 *".encode("utf-16"), "UTF-8"),
    ],
    ids=["vacio", "espacios", "ilegal", "no-pgn", "no-utf8"],
)
def test_archivo_sin_partidas_validas_da_422(client, yo, contenido, texto):
    r = subir(client, yo, contenido)
    assert r.status_code == 422
    assert texto in str(r.json()["detail"])


def test_archivo_demasiado_grande_da_413(client, yo):
    assert subir(client, yo, b" " * (5 * 1024 * 1024 + 1)).status_code == 413


def test_subir_sin_archivo_da_422(client, yo):
    assert client.post("/games", headers=yo).status_code == 422


def test_subir_sin_token_da_401(client):
    assert subir(client, {}, leer("partida1.pgn")).status_code == 401


# ---------------------------------------------------------------- color del jugador


def test_player_indica_mi_nombre_en_el_pgn(client):
    headers = cuenta(client, "javier")  # en la app no me llamo como en chess.com
    sin_player = subir(client, headers, leer("partida1.pgn")).json()["created"][0]
    assert sin_player["user_color"] is None

    con_player = subir(client, headers, leer("partida2.pgn"), player="WeYtEy").json()["created"][0]
    assert con_player["user_color"] == "black"


# ---------------------------------------------------------------- listado


def _subir_las_cinco(client, headers) -> list[dict]:
    for n in range(1, 6):  # una por una: created_at/id crecientes
        subir(client, headers, leer(f"partida{n}.pgn"))
    return client.get("/games", headers=headers, params={"limit": 100}).json()["items"]


def test_listado_mas_reciente_primero(client, yo):
    items = _subir_las_cinco(client, yo)
    assert len(items) == 5
    ids = [g["id"] for g in items]
    assert ids == sorted(ids, reverse=True)
    assert "pgn" not in items[0]  # el listado no trae el PGN completo


def test_paginacion(client, yo):
    todos = [g["id"] for g in _subir_las_cinco(client, yo)]
    pagina = client.get("/games", headers=yo, params={"limit": 2, "offset": 2}).json()
    assert pagina["total"] == 5
    assert (pagina["limit"], pagina["offset"]) == (2, 2)
    assert [g["id"] for g in pagina["items"]] == todos[2:4]
    fuera = client.get("/games", headers=yo, params={"offset": 10}).json()
    assert fuera["items"] == [] and fuera["total"] == 5


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"result": "2-0"}])
def test_parametros_de_listado_invalidos(client, yo, params):
    assert client.get("/games", headers=yo, params=params).status_code == 422


@pytest.mark.parametrize(("resultado", "cuantas"), [("1-0", 2), ("0-1", 2), ("1/2-1/2", 1), ("*", 0)])
def test_filtro_por_resultado(client, yo, resultado, cuantas):
    _subir_las_cinco(client, yo)
    page = client.get("/games", headers=yo, params={"result": resultado}).json()
    assert page["total"] == cuantas
    assert all(g["result"] == resultado for g in page["items"])


def test_filtro_por_fecha(client, yo):
    items = _subir_las_cinco(client, yo)
    fechas = sorted(datetime.fromisoformat(g["played_at"]) for g in items)
    dia = fechas[0].astimezone(timezone.utc).date().isoformat()
    esperadas = sum(1 for f in fechas if f.astimezone(timezone.utc).date().isoformat() == dia)

    page = client.get("/games", headers=yo, params={"played_from": dia, "played_to": dia}).json()
    assert page["total"] == esperadas >= 1
    assert client.get("/games", headers=yo, params={"played_from": "2099-01-01"}).json()["total"] == 0
    r = client.get("/games", headers=yo, params={"played_from": "2026-10-10", "played_to": "2026-10-01"})
    assert r.status_code == 422


# ---------------------------------------------------------------- borrar


def test_borrar_partida_borra_sus_jugadas(client, yo, session):
    game_id = subir(client, yo, leer("partida1.pgn")).json()["created"][0]["id"]
    assert client.delete(f"/games/{game_id}", headers=yo).status_code == 204
    assert client.get(f"/games/{game_id}", headers=yo).status_code == 404
    assert session.scalar(select(func.count()).select_from(Move)) == 0


def test_despues_de_borrar_se_puede_volver_a_subir(client, yo):
    game_id = subir(client, yo, leer("partida1.pgn")).json()["created"][0]["id"]
    client.delete(f"/games/{game_id}", headers=yo)
    assert subir(client, yo, leer("partida1.pgn")).status_code == 201


@pytest.mark.parametrize(
    ("metodo", "ruta"),
    [("get", "/games/999999999"), ("get", "/games/999999999/moves"), ("delete", "/games/999999999")],
)
def test_partida_inexistente_da_404(client, yo, metodo, ruta):
    assert getattr(client, metodo)(ruta, headers=yo).status_code == 404


# ---------------------------------------------------------------- aislamiento entre usuarios


def test_nadie_ve_ni_borra_partidas_de_otro(client, yo, otro):
    mia = subir(client, yo, leer("partida1.pgn")).json()["created"][0]["id"]

    assert client.get("/games", headers=otro).json() == {"items": [], "total": 0, "limit": 20, "offset": 0}
    for metodo, ruta in [("get", f"/games/{mia}"), ("get", f"/games/{mia}/moves"), ("delete", f"/games/{mia}")]:
        r = getattr(client, metodo)(ruta, headers=otro)
        assert r.status_code == 404, f"{metodo.upper()} {ruta}"
        assert r.json() == {"detail": "Partida no encontrada"}  # idéntico a una que no existe

    assert client.get(f"/games/{mia}", headers=yo).status_code == 200  # sigue ahí


def test_dos_usuarios_pueden_subir_la_misma_partida(client, yo, otro):
    a = subir(client, yo, leer("partida1.pgn")).json()["created"][0]["id"]
    b = subir(client, otro, leer("partida1.pgn")).json()["created"][0]["id"]
    assert a != b
    assert client.get("/games", headers=yo).json()["total"] == 1
    assert client.get("/games", headers=otro).json()["total"] == 1


def test_mis_duplicados_no_dependen_de_otro_usuario(client, yo, otro):
    subir(client, otro, leer("partida1.pgn"))
    # Que el otro ya la tenga no la convierte en duplicada para mí.
    assert subir(client, yo, leer("partida1.pgn")).json()["duplicates"] == []


@pytest.mark.parametrize(
    ("metodo", "ruta"),
    [("get", "/games"), ("get", "/games/1"), ("get", "/games/1/moves"), ("delete", "/games/1")],
)
def test_todas_las_rutas_piden_token(client, metodo, ruta):
    assert getattr(client, metodo)(ruta).status_code == 401
