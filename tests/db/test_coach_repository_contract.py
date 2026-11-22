"""Contrato del repositorio del coach: el de memoria (tests/fakes.py) se comporta como el SQL.

Las mismas pruebas corren con [sql] (PostgreSQL) y [memoria]."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

from app.models import CoachGameRecord, CoachMessage, User
from app.repositories.coach import CoachRepository, SqlCoachRepository
from tests.fakes import InMemoryCoachRepository

JUGADA = {
    "ply": 1, "san": "e4", "uci": "e2e4", "by": "user", "eval_before": 20, "eval_after": 30,
    "cp_loss": 0, "win_drop": 0.0, "label": "buena", "best_san": "e4", "best_line": ["e4", "e5"],
}  # fmt: skip


@pytest.fixture(params=["sql", "memoria"])
def entorno(request) -> tuple[CoachRepository, Callable[[str], User]]:
    if request.param == "sql":
        session = request.getfixturevalue("session")  # se salta si no hay BD

        def nuevo_usuario(nombre: str) -> User:
            user = User(email=f"{nombre}@example.com", username=nombre, hashed_password="x")
            session.add(user)
            session.flush()
            return user

        return SqlCoachRepository(session), nuevo_usuario

    ids = iter(range(1, 100))
    return InMemoryCoachRepository(), lambda nombre: User(id=next(ids), username=nombre)


def nueva(user: User, moves=None) -> CoachGameRecord:
    return CoachGameRecord(user_id=user.id, user_color="white", level=3, moves=moves or [], messages=[])


def test_create_asigna_id_fechas_y_valores_por_defecto(entorno):
    repo, usuario = entorno
    p = repo.create(nueva(usuario("ana")))
    assert p.id is not None and p.created_at is not None and p.updated_at is not None
    assert p.result == "*" and p.moves == [] and p.termination is None


def test_get_solo_del_dueno_y_con_mensajes(entorno):
    repo, usuario = entorno
    ana, otro = usuario("ana"), usuario("otro")
    p = repo.create(nueva(ana))
    assert repo.get(otro.id, p.id) is None
    assert repo.get(ana.id, p.id, for_update=True).id == p.id
    assert repo.get(ana.id, 999_999) is None


def test_save_turn_guarda_jugadas_y_mensajes_en_orden(entorno):
    repo, usuario = entorno
    ana = usuario("ana")
    p = repo.create(nueva(ana))
    p = repo.get(ana.id, p.id, for_update=True)
    p.moves = [JUGADA]
    repo.save_turn(
        p,
        [
            CoachMessage(user_id=ana.id, role="user", content="¿qué tal?"),
            CoachMessage(user_id=ana.id, role="coach", content="bien", model="m"),
        ],
    )
    leida = repo.get(ana.id, p.id)
    assert leida.moves == [JUGADA]
    assert [(m.role, m.content, m.model) for m in leida.messages] == [
        ("user", "¿qué tal?", None),
        ("coach", "bien", "m"),
    ]
    assert all(m.id is not None and m.created_at is not None for m in leida.messages)


def test_list_page_del_usuario_mas_reciente_primero(entorno):
    repo, usuario = entorno
    ana, otro = usuario("ana"), usuario("otro")
    ids = [repo.create(nueva(ana)).id for _ in range(3)]
    repo.create(nueva(otro))
    pagina, total = repo.list_page(ana.id, limit=2, offset=0)
    assert total == 3 and [p.id for p in pagina] == ids[::-1][:2]
    assert [p.id for p in repo.list_page(ana.id, limit=2, offset=2)[0]] == ids[:1]


def test_coach_answers_since_cuenta_solo_respuestas_del_usuario(entorno):
    repo, usuario = entorno
    ana, otro = usuario("ana"), usuario("otro")
    for user in (ana, otro):
        p = repo.create(nueva(user))
        repo.save_turn(
            p,
            [
                CoachMessage(user_id=user.id, role="user", content="?"),
                CoachMessage(user_id=user.id, role="coach", content="!"),
                CoachMessage(user_id=user.id, role="coach", content="!!"),
            ],
        )
    hace_un_rato = datetime.now(UTC) - timedelta(minutes=5)
    assert repo.coach_answers_since(ana.id, hace_un_rato) == 2
    assert repo.coach_answers_since(ana.id, datetime.now(UTC) + timedelta(minutes=5)) == 0


def test_delete(entorno):
    repo, usuario = entorno
    ana = usuario("ana")
    p = repo.create(nueva(ana))
    repo.save_turn(p, [CoachMessage(user_id=ana.id, role="user", content="?")])
    repo.delete(p)
    assert repo.get(ana.id, p.id) is None
