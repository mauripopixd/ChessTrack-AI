"""Lógica de partidas: importar PGN, listar, consultar y borrar.

Sin SQL ni HTTP: habla con un GameRepository (app/repositories/games.py), así que
se prueba con un repositorio en memoria (tests/unit/) y se usa igual desde la API
que desde scripts/import_raw.py.
"""

import hashlib

from app.models import Game, Move, User
from app.pgn_parser import InvalidPGNError, ParsedGame, parse_pgn_each
from app.repositories.games import GameFilter, GameRepository
from app.schemas import (
    GameDetail,
    GamePage,
    GameSummary,
    ImportDuplicate,
    ImportFailure,
    ImportResult,
    MoveRead,
)


def pgn_hash(parsed: ParsedGame) -> str:
    """Huella de la partida. Usa el PGN normalizado por python-chess, así el mismo
    archivo descargado dos veces da el mismo hash aunque cambien espacios o saltos de línea."""
    return hashlib.sha256(parsed.pgn.encode("utf-8")).hexdigest()


def detect_color(parsed: ParsedGame, player: str) -> str | None:
    player = player.lower()
    if (parsed.white or "").lower() == player:
        return "white"
    if (parsed.black or "").lower() == player:
        return "black"
    return None


def summary(game: Game, move_count: int) -> GameSummary:
    return GameSummary(
        id=game.id,
        white=game.white,
        black=game.black,
        result=game.result,
        played_at=game.played_at,
        user_color=game.user_color,
        move_count=move_count,
        created_at=game.created_at,
    )


def _to_game(user: User, parsed: ParsedGame, h: str, player: str) -> Game:
    return Game(
        user_id=user.id,
        pgn_raw=parsed.pgn,
        pgn_hash=h,
        white=parsed.white,
        black=parsed.black,
        result=parsed.result,
        played_at=parsed.played_at,
        user_color=detect_color(parsed, player),
        moves=[Move(ply=m.ply, san=m.san, uci=m.uci, fen_after=m.fen_after) for m in parsed.moves],
    )


class GameService:
    def __init__(self, games: GameRepository) -> None:
        self.games = games

    def import_pgn(self, user: User, text: str, player: str | None = None) -> ImportResult:
        """Guarda todas las partidas válidas del texto; informa de repetidas e inválidas.

        `player` es tu nombre dentro del PGN (p. ej. tu usuario de chess.com) para saber
        con qué color jugaste; por defecto, tu username de la app.
        Lanza InvalidPGNError si el texto no contiene ninguna partida y
        ConcurrentImportError si otra subida simultánea guardó alguna a la vez.
        """
        items = parse_pgn_each(text)
        player = player or user.username

        validas = [(i, p, pgn_hash(p)) for i, p in enumerate(items) if isinstance(p, ParsedGame)]
        existentes = self.games.existing_hashes(user.id, {h for _, _, h in validas})

        nuevas: list[tuple[Game, int]] = []
        nuevas_por_hash: dict[str, Game] = {}  # para repetidas dentro del mismo archivo
        repetidas: list[tuple[int, Game | int]] = []  # (índice, partida nueva o id ya guardado)
        for index, parsed, h in validas:
            if h in existentes:
                repetidas.append((index, existentes[h]))
            elif h in nuevas_por_hash:
                repetidas.append((index, nuevas_por_hash[h]))  # su id existe tras guardar
            else:
                game = _to_game(user, parsed, h, player)
                nuevas.append((game, len(parsed.moves)))
                nuevas_por_hash[h] = game

        self.games.save_all([g for g, _ in nuevas])

        return ImportResult(
            created=[summary(g, n) for g, n in nuevas],
            duplicates=[
                ImportDuplicate(index=i, game_id=g if isinstance(g, int) else g.id) for i, g in repetidas
            ],
            errors=[
                ImportFailure(index=i, detail=str(e))
                for i, e in enumerate(items)
                if isinstance(e, InvalidPGNError)
            ],
        )

    def list_games(self, user: User, *, limit: int, offset: int, filters: GameFilter) -> GamePage:
        filas, total = self.games.list_page(user.id, filters, limit, offset)
        return GamePage(items=[summary(g, n) for g, n in filas], total=total, limit=limit, offset=offset)

    def get_detail(self, user: User, game_id: int) -> GameDetail | None:
        game = self.games.get(user.id, game_id)
        if game is None:
            return None
        return GameDetail(**summary(game, len(game.moves)).model_dump(), pgn=game.pgn_raw)

    def get_moves(self, user: User, game_id: int) -> list[MoveRead] | None:
        game = self.games.get(user.id, game_id)
        if game is None:
            return None
        return [MoveRead.model_validate(m) for m in game.moves]  # ordenadas por ply (models.py)

    def delete(self, user: User, game_id: int) -> bool:
        game = self.games.get(user.id, game_id)
        if game is None:
            return False
        self.games.delete(game)
        return True
