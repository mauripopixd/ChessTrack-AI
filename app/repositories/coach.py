"""Acceso a coach_games y coach_messages (Etapa 5B).

Como en games.py, todo filtra por `user_id`: una partida de otro usuario no existe.
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import CoachGameRecord, CoachMessage


class CoachRepository(Protocol):
    def create(self, game: CoachGameRecord) -> CoachGameRecord:
        """Guarda la partida nueva (con sus jugadas iniciales, si el coach empezó)."""
        ...

    def list_page(self, user_id: int, limit: int, offset: int) -> tuple[list[CoachGameRecord], int]:
        """(partidas, total), más reciente primero."""
        ...

    def get(self, user_id: int, game_id: int, *, for_update: bool = False) -> CoachGameRecord | None:
        """Con sus mensajes. for_update bloquea la fila hasta el commit: dos turnos simultáneos
        de la misma partida se ejecutan uno detrás de otro, en vez de pisarse las jugadas."""
        ...

    def save_turn(self, game: CoachGameRecord, new_messages: Sequence[CoachMessage]) -> None:
        """Guarda los cambios de la partida (jugadas, resultado) y los mensajes nuevos."""
        ...

    def coach_answers_since(self, user_id: int, since: datetime) -> int:
        """Respuestas del LLM a ese usuario desde `since`, en todas sus partidas (para el límite)."""
        ...

    def delete(self, game: CoachGameRecord) -> None: ...


class SqlCoachRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, game: CoachGameRecord) -> CoachGameRecord:
        self.session.add(game)
        self.session.commit()
        return game

    def list_page(self, user_id: int, limit: int, offset: int) -> tuple[list[CoachGameRecord], int]:
        de_usuario = select(CoachGameRecord).where(CoachGameRecord.user_id == user_id)
        total = self.session.scalar(select(func.count()).select_from(de_usuario.subquery()))
        filas = self.session.scalars(
            de_usuario.order_by(CoachGameRecord.created_at.desc(), CoachGameRecord.id.desc())
            .limit(limit)
            .offset(offset)
        ).all()
        return list(filas), total

    def get(self, user_id: int, game_id: int, *, for_update: bool = False) -> CoachGameRecord | None:
        query = (
            select(CoachGameRecord)
            .where(CoachGameRecord.user_id == user_id, CoachGameRecord.id == game_id)
            .options(selectinload(CoachGameRecord.messages))
        )
        if for_update:
            query = query.with_for_update(of=CoachGameRecord)
        return self.session.scalars(query).first()

    def save_turn(self, game: CoachGameRecord, new_messages: Sequence[CoachMessage]) -> None:
        game.messages.extend(new_messages)
        self.session.commit()  # también libera el bloqueo de for_update

    def coach_answers_since(self, user_id: int, since: datetime) -> int:
        return self.session.scalar(
            select(func.count()).where(
                CoachMessage.user_id == user_id,
                CoachMessage.role == "coach",
                CoachMessage.created_at >= since,
            )
        )

    def delete(self, game: CoachGameRecord) -> None:
        self.session.delete(game)  # sus mensajes caen por ON DELETE CASCADE
        self.session.commit()
