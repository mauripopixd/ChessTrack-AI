"""Acceso a las tablas games y moves.

Todos los métodos reciben el `user_id` y filtran por él: es lo que garantiza que
nadie vea ni borre partidas de otro, y vive aquí para que ningún service lo olvide.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Protocol

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import ConcurrentImportError
from app.models import Game, Move


@dataclass(frozen=True)
class GameFilter:
    result: str | None = None
    played_from: date | None = None  # inclusivo, día UTC
    played_to: date | None = None  # inclusivo, día UTC


class GameRepository(Protocol):
    def existing_hashes(self, user_id: int, hashes: set[str]) -> dict[str, int]:
        """{pgn_hash: id} de las que ese usuario ya tiene guardadas."""
        ...

    def save_all(self, games: Sequence[Game]) -> None:
        """Guarda las partidas (con sus jugadas) en una transacción.
        Lanza ConcurrentImportError si otra petición guardó alguna a la vez."""
        ...

    def list_page(
        self, user_id: int, filters: GameFilter, limit: int, offset: int
    ) -> tuple[list[tuple[Game, int]], int]:
        """([(partida, nº de jugadas)], total sin paginar), más reciente primero."""
        ...

    def get(self, user_id: int, game_id: int) -> Game | None:
        """None si no existe o es de otro usuario: para el que pregunta, es lo mismo."""
        ...

    def delete(self, game: Game) -> None: ...


class SqlGameRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _de_usuario(self, user_id: int) -> Select:
        return select(Game).where(Game.user_id == user_id)

    def existing_hashes(self, user_id: int, hashes: set[str]) -> dict[str, int]:
        # Una sola consulta IN (...) en vez de una por partida (docs/decisiones.md §4).
        filas = self.session.execute(
            select(Game.pgn_hash, Game.id).where(Game.user_id == user_id, Game.pgn_hash.in_(hashes))
        )
        return dict(filas.all())

    def save_all(self, games: Sequence[Game]) -> None:
        self.session.add_all(games)
        try:
            self.session.commit()
        except IntegrityError:
            # uq_games_user_id_pgn_hash: otra subida simultánea ganó la carrera.
            self.session.rollback()
            raise ConcurrentImportError from None

    def list_page(
        self, user_id: int, filters: GameFilter, limit: int, offset: int
    ) -> tuple[list[tuple[Game, int]], int]:
        query = self._de_usuario(user_id)
        if filters.result is not None:
            query = query.where(Game.result == filters.result)
        if filters.played_from is not None:
            query = query.where(Game.played_at >= datetime.combine(filters.played_from, time.min, UTC))
        if filters.played_to is not None:  # inclusivo: todo el día `played_to`
            hasta = datetime.combine(filters.played_to + timedelta(days=1), time.min, UTC)
            query = query.where(Game.played_at < hasta)

        total = self.session.scalar(select(func.count()).select_from(query.subquery()))

        # Orden por (created_at, id): es justo el índice ix_games_user_id_created_at_id, así
        # que PostgreSQL recorre el índice sin ordenar. El id desempata partidas subidas en
        # el mismo archivo (mismo created_at).
        orden = (Game.created_at.desc(), Game.id.desc())
        # 1) Ids de la página, solo con el índice. 2) Filas y conteo de jugadas SOLO para esos
        # ids. Hacerlo en una consulta calculaba move_count también para las filas que el
        # OFFSET descarta: 87 ms en vez de 1 ms con offset=6000 (docs/decisiones.md §3).
        pagina = query.with_only_columns(Game.id).order_by(*orden).limit(limit).offset(offset).subquery()
        move_count = (
            select(func.count(Move.id)).where(Move.game_id == Game.id).correlate(Game).scalar_subquery()
        )
        filas = self.session.execute(
            select(Game, move_count).join(pagina, Game.id == pagina.c.id).order_by(*orden)
        ).all()
        return [(game, n) for game, n in filas], total

    def get(self, user_id: int, game_id: int) -> Game | None:
        return self.session.scalars(self._de_usuario(user_id).where(Game.id == game_id)).first()

    def delete(self, game: Game) -> None:
        self.session.delete(game)  # sus jugadas caen por ON DELETE CASCADE
        self.session.commit()
