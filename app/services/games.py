"""Lógica de partidas: importar PGN, listar, consultar y borrar.

Los routers solo traducen HTTP ↔ estas funciones. Toda consulta filtra por
`user_id`: es lo que garantiza que nadie vea ni borre partidas de otro.
"""

import hashlib
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models import Game, Move, User
from app.pgn_parser import InvalidPGNError, ParsedGame, parse_pgn_each
from app.schemas import GamePage, GameSummary, ImportDuplicate, ImportFailure, ImportResult


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


# ---------------------------------------------------------------- importar


def import_pgn(session: Session, user: User, text: str, player: str | None = None) -> ImportResult:
    """Guarda todas las partidas válidas del texto; informa de repetidas e inválidas.

    `player` es tu nombre dentro del PGN (p. ej. tu usuario de chess.com) para saber
    con qué color jugaste; por defecto, tu username de la app.
    Lanza InvalidPGNError si el texto no contiene ninguna partida.
    """
    items = parse_pgn_each(text)
    player = player or user.username

    validas = [(i, p, pgn_hash(p)) for i, p in enumerate(items) if isinstance(p, ParsedGame)]
    # Una sola consulta para saber cuáles ya estaban guardadas (en vez de una por partida).
    existentes = dict(
        session.execute(
            select(Game.pgn_hash, Game.id).where(
                Game.user_id == user.id, Game.pgn_hash.in_({h for _, _, h in validas})
            )
        ).all()
    )

    nuevas: list[tuple[Game, int]] = []
    nuevas_por_hash: dict[str, Game] = {}  # para repetidas dentro del mismo archivo
    repetidas: list[tuple[int, Game | int]] = []  # (índice, partida nueva o id ya guardado)
    for index, parsed, h in validas:
        if h in existentes:
            repetidas.append((index, existentes[h]))
            continue
        if h in nuevas_por_hash:
            repetidas.append((index, nuevas_por_hash[h]))  # su id existe tras el commit
            continue
        game = Game(
            user=user,
            pgn_raw=parsed.pgn,
            pgn_hash=h,
            white=parsed.white,
            black=parsed.black,
            result=parsed.result,
            played_at=parsed.played_at,
            user_color=detect_color(parsed, player),
            moves=[Move(ply=m.ply, san=m.san, uci=m.uci, fen_after=m.fen_after) for m in parsed.moves],
        )
        session.add(game)
        nuevas.append((game, len(parsed.moves)))
        nuevas_por_hash[h] = game

    session.commit()

    duplicates = [ImportDuplicate(index=i, game_id=g if isinstance(g, int) else g.id) for i, g in repetidas]
    errors = [
        ImportFailure(index=i, detail=str(e)) for i, e in enumerate(items) if isinstance(e, InvalidPGNError)
    ]
    return ImportResult(created=[summary(g, n) for g, n in nuevas], duplicates=duplicates, errors=errors)


# ---------------------------------------------------------------- consultar


def _de_usuario(user: User) -> Select:
    return select(Game).where(Game.user_id == user.id)


def list_games(
    session: Session,
    user: User,
    *,
    limit: int,
    offset: int,
    result: str | None = None,
    played_from: date | None = None,
    played_to: date | None = None,
) -> GamePage:
    query = _de_usuario(user)
    if result is not None:
        query = query.where(Game.result == result)
    if played_from is not None:
        query = query.where(Game.played_at >= datetime.combine(played_from, time.min, UTC))
    if played_to is not None:  # inclusivo: todo el día `played_to`
        hasta = datetime.combine(played_to + timedelta(days=1), time.min, UTC)
        query = query.where(Game.played_at < hasta)

    total = session.scalar(select(func.count()).select_from(query.subquery()))

    # Orden por (created_at, id): es justo el índice ix_games_user_id_created_at_id, así
    # que PostgreSQL recorre el índice sin ordenar. El id desempata partidas subidas en
    # el mismo archivo (mismo created_at).
    orden = (Game.created_at.desc(), Game.id.desc())
    # 1) Ids de la página, solo con el índice. 2) Filas y conteo de jugadas SOLO para esos
    # ids. Hacerlo en una consulta calculaba move_count también para las filas que el
    # OFFSET descarta: 87 ms en vez de 1 ms con offset=6000 (docs/decisiones.md).
    pagina = query.with_only_columns(Game.id).order_by(*orden).limit(limit).offset(offset).subquery()
    move_count = select(func.count(Move.id)).where(Move.game_id == Game.id).correlate(Game).scalar_subquery()
    rows = session.execute(
        select(Game, move_count).join(pagina, Game.id == pagina.c.id).order_by(*orden)
    ).all()
    return GamePage(items=[summary(game, n) for game, n in rows], total=total, limit=limit, offset=offset)


def get_game(session: Session, user: User, game_id: int) -> Game | None:
    """None si no existe o es de otro usuario: para el que pregunta, es lo mismo."""
    return session.scalars(_de_usuario(user).where(Game.id == game_id)).first()


def delete_game(session: Session, user: User, game_id: int) -> bool:
    game = get_game(session, user, game_id)
    if game is None:
        return False
    session.delete(game)  # sus jugadas caen por ON DELETE CASCADE
    session.commit()
    return True
