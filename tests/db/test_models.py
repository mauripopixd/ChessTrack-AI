import hashlib
from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import delete, func, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Game, Move, User
from app.pgn_parser import ParsedGame, parse_pgn
from tests.db.conftest import alembic_config

SAMPLES = Path(__file__).resolve().parents[2] / "data" / "samples"


# ---------------------------------------------------------------- helpers


def crear_usuario(session: Session, nombre: str = "weytey") -> User:
    user = User(email=f"{nombre}@example.com", username=nombre, hashed_password="x")
    session.add(user)
    session.flush()
    return user


def partida_desde_pgn(user: User, parsed: ParsedGame) -> Game:
    """Convierte un ParsedGame en filas. (La versión definitiva irá en el servicio de partidas.)"""
    usuario = user.username.lower()
    color = {(parsed.white or "").lower(): "white", (parsed.black or "").lower(): "black"}.get(usuario)
    return Game(
        user=user,
        pgn_raw=parsed.pgn,
        pgn_hash=hashlib.sha256(parsed.pgn.encode()).hexdigest(),
        white=parsed.white,
        black=parsed.black,
        result=parsed.result,
        played_at=parsed.played_at,
        user_color=color,
        moves=[Move(ply=m.ply, san=m.san, uci=m.uci, fen_after=m.fen_after) for m in parsed.moves],
    )


def muestra(n: int = 1) -> ParsedGame:
    return parse_pgn((SAMPLES / f"partida{n}.pgn").read_text(encoding="utf-8"))


def error_de_restriccion(session: Session, nombre: str) -> None:
    """El flush debe fallar justo por la restricción `nombre` de la BD."""
    with pytest.raises(IntegrityError) as exc:
        session.flush()
    assert exc.value.orig.diag.constraint_name == nombre
    session.rollback()


# ---------------------------------------------------------------- migraciones


def test_migracion_crea_las_tablas(engine):
    assert set(inspect(engine).get_table_names()) == {"alembic_version", "users", "games", "moves"}


def test_modelos_y_migracion_coinciden(db_url, engine):
    # Falla si alguien cambia un modelo y olvida crear la migración.
    command.check(alembic_config(db_url))


def test_downgrade_y_upgrade_funcionan(db_url, engine):
    cfg = alembic_config(db_url)
    command.downgrade(cfg, "base")
    assert set(inspect(engine).get_table_names()) == {"alembic_version"}
    command.upgrade(cfg, "head")
    assert {"users", "games", "moves"} <= set(inspect(engine).get_table_names())


# ---------------------------------------------------------------- guardar y leer


def test_guarda_y_recupera_partida_real(session):
    parsed = muestra(1)
    user = crear_usuario(session)
    session.add(partida_desde_pgn(user, parsed))
    session.commit()
    session.expunge_all()  # obliga a leer de la BD, no de la memoria de la sesión

    game = session.scalars(select(Game)).one()
    assert (game.white, game.black, game.result) == (parsed.white, parsed.black, "1-0")
    assert game.user_color == "white"
    assert game.played_at == parsed.played_at
    assert [m.ply for m in game.moves] == list(range(1, len(parsed.moves) + 1))
    assert [(m.san, m.uci, m.fen_after) for m in game.moves] == [
        (m.san, m.uci, m.fen_after) for m in parsed.moves
    ]


def test_created_at_lo_pone_la_bd_en_utc(session):
    user = crear_usuario(session)
    session.refresh(user)
    assert user.created_at.tzinfo is not None
    assert abs(user.created_at - datetime.now(timezone.utc)).total_seconds() < 60


def test_jugadas_salen_ordenadas_por_ply(session):
    user = crear_usuario(session)
    game = partida_desde_pgn(user, muestra(2))
    game.moves.reverse()  # insertadas al revés
    session.add(game)
    session.commit()
    session.expunge_all()
    plies = [m.ply for m in session.scalars(select(Game)).one().moves]
    assert plies == sorted(plies)


# ---------------------------------------------------------------- restricciones


def test_email_duplicado(session):
    crear_usuario(session, "ana")
    session.add(User(email="ana@example.com", username="otra", hashed_password="x"))
    error_de_restriccion(session, "uq_users_email")


def test_username_duplicado(session):
    crear_usuario(session, "ana")
    session.add(User(email="otra@example.com", username="ana", hashed_password="x"))
    error_de_restriccion(session, "uq_users_username")


def test_misma_partida_dos_veces_mismo_usuario(session):
    user = crear_usuario(session)
    session.add(partida_desde_pgn(user, muestra(1)))
    session.flush()
    session.add(partida_desde_pgn(user, muestra(1)))
    error_de_restriccion(session, "uq_games_user_id_pgn_hash")


def test_misma_partida_distintos_usuarios_si_se_permite(session):
    for nombre in ("ana", "luis"):
        session.add(partida_desde_pgn(crear_usuario(session, nombre), muestra(1)))
    session.flush()
    assert session.scalar(select(func.count()).select_from(Game)) == 2


def test_ply_duplicado(session):
    game = partida_desde_pgn(crear_usuario(session), muestra(1))
    game.moves[1].ply = 1
    session.add(game)
    error_de_restriccion(session, "uq_moves_game_id_ply")


def test_ply_cero(session):
    game = partida_desde_pgn(crear_usuario(session), muestra(1))
    game.moves[0].ply = 0
    session.add(game)
    error_de_restriccion(session, "ck_moves_ply_positivo")


def test_resultado_invalido(session):
    game = partida_desde_pgn(crear_usuario(session), muestra(1))
    game.result = "2-0"
    session.add(game)
    error_de_restriccion(session, "ck_games_result_valido")


def test_color_invalido(session):
    game = partida_desde_pgn(crear_usuario(session), muestra(1))
    game.user_color = "rojo"
    session.add(game)
    error_de_restriccion(session, "ck_games_user_color_valido")


def test_partida_de_usuario_inexistente(session):
    session.add(Game(user_id=999_999, pgn_raw="*", pgn_hash="0" * 64, result="*"))
    error_de_restriccion(session, "fk_games_user_id_users")


# ---------------------------------------------------------------- borrado en cascada


def _contar(session: Session) -> tuple[int, int]:
    return (
        session.scalar(select(func.count()).select_from(Game)),
        session.scalar(select(func.count()).select_from(Move)),
    )


def test_borrar_usuario_en_sql_borra_partidas_y_jugadas(session):
    user = crear_usuario(session)
    session.add(partida_desde_pgn(user, muestra(1)))
    session.flush()
    assert _contar(session) != (0, 0)
    # DELETE directo en SQL: lo resuelve el ON DELETE CASCADE de la BD.
    session.execute(delete(User).where(User.id == user.id))
    session.expire_all()
    assert _contar(session) == (0, 0)


def test_borrar_partida_desde_el_orm_borra_sus_jugadas(session):
    user = crear_usuario(session)
    otra = partida_desde_pgn(user, muestra(2))
    game = partida_desde_pgn(user, muestra(1))
    session.add_all([game, otra])
    session.flush()
    session.delete(game)
    session.flush()
    assert _contar(session) == (1, len(otra.moves))
