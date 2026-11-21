"""GameService sin base de datos: repositorio en memoria (tests/fakes.py)."""

from datetime import date
from pathlib import Path

import pytest

from app.errors import ConcurrentImportError
from app.models import User
from app.pgn_parser import InvalidPGNError, parse_pgn
from app.repositories.games import GameFilter
from app.services.games import GameService
from tests.fakes import InMemoryGameRepository

SAMPLES = Path(__file__).resolve().parents[2] / "data" / "samples"
COLORES = ["white", "black", "black", "white", "black"]
TODAS = GameFilter()


def leer(nombre: str) -> str:
    return (SAMPLES / nombre).read_text(encoding="utf-8")


@pytest.fixture
def repo() -> InMemoryGameRepository:
    return InMemoryGameRepository()


@pytest.fixture
def service(repo) -> GameService:
    return GameService(repo)


@pytest.fixture
def yo() -> User:
    return User(id=1, username="weytey", email="w@example.com", hashed_password="x")


@pytest.fixture
def otro() -> User:
    return User(id=2, username="intruso", email="i@example.com", hashed_password="x")


# ---------------------------------------------------------------- importar


def test_importa_las_cinco_con_su_color(service, yo):
    r = service.import_pgn(yo, leer("varias.pgn"))
    assert [g.user_color for g in r.created] == COLORES
    assert r.duplicates == [] and r.errors == []


def test_las_jugadas_se_guardan_tal_cual_las_lee_el_parser(service, repo, yo):
    esperado = parse_pgn(leer("partida1.pgn"))
    creada = service.import_pgn(yo, leer("partida1.pgn")).created[0]
    guardadas = repo.games[creada.id].moves
    assert [(m.ply, m.san, m.uci, m.fen_after) for m in guardadas] == [
        (m.ply, m.san, m.uci, m.fen_after) for m in esperado.moves
    ]
    assert creada.move_count == len(esperado.moves)


def test_reimportar_da_duplicadas_con_su_id(service, yo):
    primera = service.import_pgn(yo, leer("varias.pgn")).created
    r = service.import_pgn(yo, leer("varias.pgn"))
    assert r.created == []
    assert [d.game_id for d in r.duplicates] == [g.id for g in primera]


def test_repetida_en_el_mismo_archivo(service, yo):
    r = service.import_pgn(yo, leer("partida1.pgn") + "\n\n" + leer("partida1.pgn"))
    assert len(r.created) == 1
    assert [(d.index, d.game_id) for d in r.duplicates] == [(1, r.created[0].id)]


def test_partida_invalida_se_informa_y_las_demas_se_guardan(service, yo):
    r = service.import_pgn(yo, leer("partida1.pgn") + "\n\n1. e4 e5 2. Ke3 *\n\n" + leer("partida2.pgn"))
    assert len(r.created) == 2
    assert [e.index for e in r.errors] == [1]


def test_texto_vacio_lanza_invalid_pgn(service, yo):
    with pytest.raises(InvalidPGNError):
        service.import_pgn(yo, "")


def test_player_cambia_la_deteccion_de_color(service):
    javier = User(id=3, username="javier", email="j@example.com", hashed_password="x")
    assert service.import_pgn(javier, leer("partida1.pgn")).created[0].user_color is None
    assert service.import_pgn(javier, leer("partida2.pgn"), player="weytey").created[0].user_color == "black"


def test_subida_simultanea_propaga_el_error(service, repo, yo):
    repo.fail_next_save = True
    with pytest.raises(ConcurrentImportError):
        service.import_pgn(yo, leer("partida1.pgn"))


def test_duplicados_son_por_usuario(service, yo, otro):
    service.import_pgn(otro, leer("partida1.pgn"))
    assert service.import_pgn(yo, leer("partida1.pgn")).duplicates == []


# ---------------------------------------------------------------- consultar y borrar


def test_listado_paginado_y_filtrado(service, yo):
    service.import_pgn(yo, leer("varias.pgn"))
    page = service.list_games(yo, limit=2, offset=0, filters=TODAS)
    assert page.total == 5 and len(page.items) == 2
    assert service.list_games(yo, limit=20, offset=0, filters=GameFilter(result="1-0")).total == 2
    assert (
        service.list_games(yo, limit=20, offset=0, filters=GameFilter(played_from=date(2099, 1, 1))).total
        == 0
    )


def test_partida_ajena_no_se_ve_ni_se_borra(service, yo, otro):
    mia = service.import_pgn(yo, leer("partida1.pgn")).created[0].id
    assert service.get_detail(otro, mia) is None
    assert service.get_moves(otro, mia) is None
    assert service.delete(otro, mia) is False
    assert service.list_games(otro, limit=20, offset=0, filters=TODAS).total == 0
    assert service.get_detail(yo, mia) is not None  # sigue ahí


def test_detalle_y_jugadas(service, yo):
    creada = service.import_pgn(yo, leer("partida1.pgn")).created[0]
    detalle = service.get_detail(yo, creada.id)
    assert detalle.move_count == creada.move_count
    assert parse_pgn(detalle.pgn).moves[-1].san == "Ra8#"
    assert service.get_moves(yo, creada.id)[-1].san == "Ra8#"


def test_borrar(service, yo):
    creada = service.import_pgn(yo, leer("partida1.pgn")).created[0]
    assert service.delete(yo, creada.id) is True
    assert service.get_detail(yo, creada.id) is None
    assert service.delete(yo, creada.id) is False
