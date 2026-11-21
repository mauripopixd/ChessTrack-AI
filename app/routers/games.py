"""Partidas del usuario autenticado. Solo traduce HTTP ↔ GameService.

Una partida de otro usuario responde 404, no 403: un 403 confirmaría que ese id
existe, y así nadie puede averiguar cuántas partidas hay ni sus ids.
"""

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, HTTPException, Query, Response, UploadFile, status

from app.deps import CurrentUser, GameServiceDep
from app.errors import ConcurrentImportError
from app.pgn_parser import InvalidPGNError
from app.repositories.games import GameFilter
from app.schemas import GameDetail, GamePage, ImportResult, MoveRead

router = APIRouter(prefix="/games", tags=["games"])

MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # ~2.000 partidas de chess.com
Result = Literal["1-0", "0-1", "1/2-1/2", "*"]


def _no_encontrada() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Partida no encontrada")


@router.post(
    "",
    response_model=ImportResult,
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {"description": "Ninguna nueva: todas estaban ya guardadas"},
        413: {"description": "Archivo de más de 5 MB"},
        422: {"description": "El archivo no tiene ninguna partida válida o no es UTF-8"},
    },
)
async def upload_games(
    user: CurrentUser,
    games: GameServiceDep,
    response: Response,
    file: Annotated[UploadFile, File(description="Archivo .pgn con una o varias partidas")],
    player: Annotated[
        str | None,
        Form(description="Tu nombre en el PGN (p. ej. usuario de chess.com); por defecto, tu username"),
    ] = None,
) -> ImportResult:
    contenido = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(contenido) > MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "El archivo supera los 5 MB")
    try:
        texto = contenido.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "El archivo no está en UTF-8") from None

    try:
        resultado = games.import_pgn(user, texto, player=player)
    except InvalidPGNError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from None
    except ConcurrentImportError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Subida simultánea de la misma partida; reintenta"
        ) from None

    if not resultado.created and not resultado.duplicates:
        # Todo el archivo era inválido.
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, [e.model_dump() for e in resultado.errors])
    if not resultado.created:
        response.status_code = status.HTTP_200_OK
    return resultado


@router.get("", response_model=GamePage)
def list_games(
    user: CurrentUser,
    games: GameServiceDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    result: Result | None = None,
    played_from: Annotated[date | None, Query(description="desde este día (UTC), incluido")] = None,
    played_to: Annotated[date | None, Query(description="hasta este día (UTC), incluido")] = None,
) -> GamePage:
    if played_from and played_to and played_from > played_to:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "played_from es posterior a played_to")
    filters = GameFilter(result=result, played_from=played_from, played_to=played_to)
    return games.list_games(user, limit=limit, offset=offset, filters=filters)


@router.get("/{game_id}", response_model=GameDetail)
def get_game(game_id: int, user: CurrentUser, games: GameServiceDep) -> GameDetail:
    detalle = games.get_detail(user, game_id)
    if detalle is None:
        raise _no_encontrada()
    return detalle


@router.get("/{game_id}/moves", response_model=list[MoveRead])
def get_moves(game_id: int, user: CurrentUser, games: GameServiceDep) -> list[MoveRead]:
    jugadas = games.get_moves(user, game_id)
    if jugadas is None:
        raise _no_encontrada()
    return jugadas


@router.delete("/{game_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_game(game_id: int, user: CurrentUser, games: GameServiceDep) -> None:
    if not games.delete(user, game_id):
        raise _no_encontrada()
