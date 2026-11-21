"""Test de contrato: el repositorio en memoria (tests/fakes.py) se comporta como el de
SQLAlchemy en lo que usan los services. Si alguien cambia uno y no el otro, falla aquí,
y así los tests unitarios con el falso siguen diciendo la verdad.

Las mismas pruebas corren dos veces: [sql] contra PostgreSQL y [memoria] sin BD.
"""

from collections.abc import Callable
from pathlib import Path

import pytest

from app.models import Game, Move, User
from app.pgn_parser import parse_pgn_many
from app.repositories.games import GameFilter, GameRepository, SqlGameRepository
from app.services.games import pgn_hash
from tests.fakes import InMemoryGameRepository

SAMPLES = Path(__file__).resolve().parents[2] / "data" / "samples"
TODAS = GameFilter()


@pytest.fixture(params=["sql", "memoria"])
def entorno(request) -> tuple[GameRepository, Callable[[str], User]]:
    """(repositorio, función que crea un usuario) para cada implementación."""
    if request.param == "sql":
        session = request.getfixturevalue("session")  # se salta si no hay BD

        def nuevo_usuario(nombre: str) -> User:
            user = User(email=f"{nombre}@example.com", username=nombre, hashed_password="x")
            session.add(user)
            session.flush()
            return user

        return SqlGameRepository(session), nuevo_usuario

    ids = iter(range(1, 100))
    return InMemoryGameRepository(), lambda nombre: User(id=next(ids), username=nombre)


def partidas(user: User) -> list[Game]:
    juegos = parse_pgn_many((SAMPLES / "varias.pgn").read_text(encoding="utf-8"))
    return [
        Game(
            user_id=user.id,
            pgn_raw=p.pgn,
            pgn_hash=pgn_hash(p),
            white=p.white,
            black=p.black,
            result=p.result,
            played_at=p.played_at,
            moves=[Move(ply=m.ply, san=m.san, uci=m.uci, fen_after=m.fen_after) for m in p.moves],
        )
        for p in juegos
    ]


def test_save_all_asigna_id_y_created_at(entorno):
    repo, nuevo = entorno
    games = partidas(nuevo("ana"))
    repo.save_all(games)
    assert all(g.id is not None and g.created_at is not None for g in games)


def test_existing_hashes_solo_del_dueno(entorno):
    repo, nuevo = entorno
    ana, luis = nuevo("ana"), nuevo("luis")
    games = partidas(ana)
    repo.save_all(games)
    hashes = {g.pgn_hash for g in games}
    assert repo.existing_hashes(ana.id, hashes) == {g.pgn_hash: g.id for g in games}
    assert repo.existing_hashes(luis.id, hashes) == {}


def test_list_page_orden_total_y_conteo(entorno):
    repo, nuevo = entorno
    ana = nuevo("ana")
    lote1, lote2 = partidas(ana)[:3], partidas(ana)[3:]
    repo.save_all(lote1)
    repo.save_all(lote2)
    filas, total = repo.list_page(ana.id, TODAS, limit=10, offset=0)
    assert total == 5
    ids = [g.id for g, _ in filas]
    # Más reciente primero; dentro del mismo lote (mismo created_at), id descendente.
    assert ids == sorted(ids, reverse=True)
    assert [n for _, n in filas] == [len(g.moves) for g, _ in filas]
    pagina, _ = repo.list_page(ana.id, TODAS, limit=2, offset=1)
    assert [g.id for g, _ in pagina] == ids[1:3]


def test_list_page_filtra_por_resultado(entorno):
    repo, nuevo = entorno
    ana = nuevo("ana")
    repo.save_all(partidas(ana))
    filas, total = repo.list_page(ana.id, GameFilter(result="1-0"), limit=10, offset=0)
    assert total == 2 and all(g.result == "1-0" for g, _ in filas)


def test_get_y_delete_respetan_al_dueno(entorno):
    repo, nuevo = entorno
    ana, luis = nuevo("ana"), nuevo("luis")
    game = partidas(ana)[0]
    repo.save_all([game])
    assert repo.get(luis.id, game.id) is None
    assert repo.get(ana.id, game.id) is game
    repo.delete(game)
    assert repo.get(ana.id, game.id) is None
