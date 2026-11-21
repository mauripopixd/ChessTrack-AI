"""Lectura y validación de partidas PGN.

Convierte texto PGN en objetos inmutables (`ParsedGame`, `ParsedMove`) y lanza
`InvalidPGNError` ante cualquier entrada que no sea una partida válida.

python-chess es tolerante por diseño y hay que revisar su salida:
- `read_game` devuelve None con texto vacío o solo espacios.
- Ante una jugada ilegal o ambigua no lanza: corta la partida y deja el error
  en `game.errors`.
- Con texto que no es PGN ("hola mundo") devuelve una partida vacía sin errores.

Limitación conocida: python-chess ignora en silencio palabras sueltas dentro
de las jugadas ("1. e4 hola e5" se lee como 1. e4 e5).
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime, timezone

import chess
import chess.pgn

RESULTADOS_VALIDOS = frozenset({"1-0", "0-1", "1/2-1/2", "*"})
_HEADERS_VACIOS = dict(chess.pgn.Headers())  # los 7 tags por defecto, con "?"


class InvalidPGNError(ValueError):
    """El texto no contiene una partida PGN válida.

    `game_index` indica qué partida falló (desde 0) cuando se leen varias.
    """

    def __init__(self, message: str, game_index: int | None = None) -> None:
        super().__init__(message)
        self.game_index = game_index


@dataclass(frozen=True, slots=True)
class ParsedMove:
    ply: int  # medio movimiento, desde 1 (1 = primera jugada de blancas)
    san: str  # notación algebraica estándar: "Nf3", "O-O", "exd6", "a8=N"
    uci: str  # notación de casillas: "g1f3", "e1g1", "e5d6", "a7a8n"
    fen_after: str  # posición tras la jugada (la usará Stockfish en la Etapa 4)


@dataclass(frozen=True, slots=True)
class ParsedGame:
    white: str | None
    black: str | None
    result: str  # "1-0", "0-1", "1/2-1/2" o "*" (sin terminar / desconocido)
    played_at: datetime | None  # UTC
    initial_fen: str  # posición inicial (distinta de la estándar si hay [SetUp])
    moves: tuple[ParsedMove, ...]
    headers: dict[str, str]
    pgn: str  # PGN normalizado por python-chess (base para el hash anti-duplicados)


class _SilentGameBuilder(chess.pgn.GameBuilder):
    """Igual que el builder por defecto, pero sin imprimir errores en el log."""

    def handle_error(self, error: Exception) -> None:
        self.game.errors.append(error)


# ---------------------------------------------------------------- API pública


def parse_pgn(text: str) -> ParsedGame:
    """Lee exactamente una partida. Lanza InvalidPGNError si hay cero o más de una."""
    games = parse_pgn_many(text)
    if len(games) > 1:
        raise InvalidPGNError(
            f"Se esperaba una partida y el texto contiene {len(games)}; usa parse_pgn_many."
        )
    return games[0]


def parse_pgn_many(text: str) -> list[ParsedGame]:
    """Lee todas las partidas del texto. Lanza InvalidPGNError si alguna es inválida."""
    games = []
    for item in parse_pgn_each(text):
        if isinstance(item, InvalidPGNError):
            raise item
        games.append(item)
    return games


def parse_pgn_each(text: str) -> list[ParsedGame | InvalidPGNError]:
    """Lee todas las partidas sin abortar: una inválida aparece como su InvalidPGNError
    y las demás se leen igual. Sirve para importar un archivo y decir cuáles fallaron.

    Solo lanza InvalidPGNError si el texto no contiene ninguna partida.
    """
    stream = io.StringIO(text.lstrip("﻿"))  # BOM de algunos editores de Windows
    items: list[ParsedGame | InvalidPGNError] = []
    while (game := chess.pgn.read_game(stream, Visitor=_SilentGameBuilder)) is not None:
        try:
            items.append(_convert(game, index=len(items)))
        except InvalidPGNError as e:
            items.append(e)
    if not items:
        raise InvalidPGNError("El texto está vacío: no contiene ninguna partida PGN.")
    return items


# ---------------------------------------------------------------- internos


def _convert(game: chess.pgn.Game, index: int) -> ParsedGame:
    moves: list[ParsedMove] = []
    board = game.board()
    initial_fen = board.fen()
    for ply, move in enumerate(game.mainline_moves(), start=1):
        san = board.san(move)  # el SAN depende de la posición: calcularlo antes del push
        board.push(move)
        moves.append(ParsedMove(ply=ply, san=san, uci=move.uci(), fen_after=board.fen()))

    if game.errors:
        # python-chess corta en la primera jugada mala: la siguiente a la última leída.
        ply = len(moves) + 1
        numero = f"{(ply + 1) // 2}." if ply % 2 else f"{ply // 2}..."
        raise InvalidPGNError(
            f"Partida {index + 1}: jugada {numero} inválida ({game.errors[0]}).",
            game_index=index,
        )

    headers = dict(game.headers)
    if not moves and headers == _HEADERS_VACIOS:
        raise InvalidPGNError(
            f"Partida {index + 1}: no se encontraron headers ni jugadas; ¿es un PGN?",
            game_index=index,
        )

    result = headers.get("Result", "*")
    if result not in RESULTADOS_VALIDOS:
        raise InvalidPGNError(
            f"Partida {index + 1}: resultado {result!r} no válido.", game_index=index
        )

    return ParsedGame(
        white=_known(headers.get("White")),
        black=_known(headers.get("Black")),
        result=result,
        played_at=_played_at(headers),
        initial_fen=initial_fen,
        moves=tuple(moves),
        headers=headers,
        pgn=str(game),
    )


def _known(value: str | None) -> str | None:
    """En PGN, "?" significa desconocido."""
    return None if value in (None, "", "?") else value


def _played_at(headers: dict[str, str]) -> datetime | None:
    """Fecha y hora UTC. chess.com da UTCDate + UTCTime; si faltan, se usa Date a las 00:00."""
    utc_date, utc_time = headers.get("UTCDate"), headers.get("UTCTime")
    if utc_date and utc_time:
        try:
            return datetime.strptime(f"{utc_date} {utc_time}", "%Y.%m.%d %H:%M:%S").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            pass
    try:
        return datetime.strptime(headers.get("Date", ""), "%Y.%m.%d").replace(tzinfo=timezone.utc)
    except ValueError:  # "????.??.??", "2026.??.??" o ausente
        return None
