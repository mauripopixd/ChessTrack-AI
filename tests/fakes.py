"""Repositorios en memoria que cumplen los mismos Protocol que los de SQLAlchemy.

Permiten probar los services sin base de datos (tests/unit/): milisegundos en vez
de segundos y sin Docker. tests/db/test_repository_contract.py comprueba que se
comportan igual que los reales en lo que importa, para que no se desvíen.
"""

from collections.abc import Sequence
from datetime import UTC, datetime, time, timedelta
from itertools import count

from app.errors import ConcurrentImportError, DuplicateUserError
from app.models import Game, MoveAnalysis, User
from app.repositories.games import GameFilter


class InMemoryUserRepository:
    def __init__(self) -> None:
        self.users: dict[int, User] = {}
        self._ids = count(1)

    def get(self, user_id: int) -> User | None:
        return self.users.get(user_id)

    def get_by_login(self, identifier: str) -> User | None:
        return next((u for u in self.users.values() if identifier in (u.username, u.email)), None)

    def create(self, user: User) -> User:
        for campo in ("email", "username"):
            if any(getattr(u, campo) == getattr(user, campo) for u in self.users.values()):
                raise DuplicateUserError(campo)
        user.id = next(self._ids)
        user.created_at = datetime.now(UTC)
        self.users[user.id] = user
        return user


class InMemoryGameRepository:
    def __init__(self) -> None:
        self.games: dict[int, Game] = {}
        self._ids = count(1)
        self.fail_next_save = False  # para simular una subida simultánea

    def existing_hashes(self, user_id: int, hashes: set[str]) -> dict[str, int]:
        return {
            g.pgn_hash: g.id for g in self.games.values() if g.user_id == user_id and g.pgn_hash in hashes
        }

    def save_all(self, games: Sequence[Game]) -> None:
        if self.fail_next_save:
            self.fail_next_save = False
            raise ConcurrentImportError
        ahora = datetime.now(UTC)  # como now() en PostgreSQL: misma hora para toda la transacción
        for g in games:
            g.id = next(self._ids)
            g.created_at = ahora
            self.games[g.id] = g

    def list_page(
        self, user_id: int, filters: GameFilter, limit: int, offset: int
    ) -> tuple[list[tuple[Game, int]], int]:
        filas = [g for g in self.games.values() if g.user_id == user_id]
        if filters.result is not None:
            filas = [g for g in filas if g.result == filters.result]
        if filters.played_from is not None:
            desde = datetime.combine(filters.played_from, time.min, UTC)
            filas = [g for g in filas if g.played_at is not None and g.played_at >= desde]
        if filters.played_to is not None:
            hasta = datetime.combine(filters.played_to + timedelta(days=1), time.min, UTC)
            filas = [g for g in filas if g.played_at is not None and g.played_at < hasta]
        filas.sort(key=lambda g: (g.created_at, g.id), reverse=True)
        pagina = filas[offset : offset + limit]
        return [(g, len(g.moves)) for g in pagina], len(filas)

    def get(self, user_id: int, game_id: int) -> Game | None:
        game = self.games.get(game_id)
        return game if game is not None and game.user_id == user_id else None

    def delete(self, game: Game) -> None:
        del self.games[game.id]

    def get_with_analysis(self, user_id: int, game_id: int) -> Game | None:
        return self.get(user_id, game_id)

    def save_analysis(self, game: Game, analyses: Sequence[MoveAnalysis], depth: int) -> None:
        for move, analisis in zip(game.moves, analyses, strict=True):
            move.analysis = analisis
        game.analysis_depth = depth
        game.analyzed_at = datetime.now(UTC)


class FakeAnalyzer:
    """Analizador sin motor: las jugadas cuyo ply esté en `errores` son error grave (500 cp);
    el resto, buenas. La mejor jugada que "propone" es siempre la propia jugada."""

    def __init__(self, errores: set[int] = frozenset(), depth: int = 7) -> None:
        self.errores = set(errores)
        self.depth = depth
        self.llamadas = 0

    def analyze(self, moves_uci: list[str], initial_fen: str):
        from app.analysis import MoveEval

        self.llamadas += 1
        filas = []
        for ply, uci in enumerate(moves_uci, start=1):
            mover = "white" if ply % 2 else "black"
            grave = ply in self.errores
            filas.append(
                MoveEval(
                    ply=ply,
                    mover=mover,
                    san="?",
                    uci=uci,
                    best_uci=uci,
                    eval_before=0,
                    eval_after=(-500 if mover == "white" else 500) if grave else 0,
                    cp_loss=500 if grave else 0,
                    win_before=50.0,
                    win_after=10.0 if grave else 50.0,
                    win_drop=40.0 if grave else 0.0,
                    label="error_grave" if grave else "buena",
                )  # fmt: skip
            )
        return filas


class FakeClassifier:
    """Clasificador sin modelo: probabilidad 0.9 en los plies de `marcadas`, 0.1 en el resto."""

    umbral = 0.5

    def __init__(self, marcadas: set[int] = frozenset()) -> None:
        self.marcadas = set(marcadas)

    def error_probs(self, filas: list[dict[str, float]]) -> list[float]:
        return [0.9 if f["ply"] in self.marcadas else 0.1 for f in filas]
