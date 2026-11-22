"""Partidas contra el coach (Etapa 5B). Solo traduce HTTP ↔ CoachService.

Como en /games, una partida de otro usuario responde 404.
"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.coach.game import GameOverError, IllegalMoveError
from app.deps import CoachServiceDep, CurrentUser
from app.engine import EngineUnavailableError
from app.errors import CoachLLMUnavailableError, CoachRateLimitError
from app.schemas import (
    CoachAskRequest,
    CoachDrawRead,
    CoachGameCreate,
    CoachGamePage,
    CoachGameRead,
    CoachMoveRequest,
    CoachTurnRead,
)

router = APIRouter(prefix="/coach/games", tags=["coach"])

_SIN_MOTOR = {503: {"description": "Stockfish no está disponible"}}


def _no_encontrada() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Partida no encontrada")


def _sin_motor(e: EngineUnavailableError) -> HTTPException:
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))


@router.post("", response_model=CoachGameRead, status_code=status.HTTP_201_CREATED, responses=_SIN_MOTOR)
def create_game(user: CurrentUser, coach: CoachServiceDep, body: CoachGameCreate) -> CoachGameRead:
    """Nueva partida. Si juegas con negras, el coach hace ya su primera jugada."""
    try:
        return coach.create(user, body.color, elo=body.elo, level=body.level)
    except EngineUnavailableError as e:
        raise _sin_motor(e) from None


@router.get("", response_model=CoachGamePage)
def list_games(
    user: CurrentUser,
    coach: CoachServiceDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CoachGamePage:
    return coach.list(user, limit, offset)


@router.get("/{game_id}", response_model=CoachGameRead)
def get_game(game_id: int, user: CurrentUser, coach: CoachServiceDep) -> CoachGameRead:
    """Posición (FEN), jugadas con su etiqueta y el chat con el coach."""
    partida = coach.get(user, game_id)
    if partida is None:
        raise _no_encontrada()
    return partida


@router.post(
    "/{game_id}/move",
    response_model=CoachTurnRead,
    responses={
        **_SIN_MOTOR,
        409: {"description": "La partida ya terminó"},
        422: {"description": "Jugada ilegal o que no se entiende"},
    },
)
def play_move(
    game_id: int, body: CoachMoveRequest, user: CurrentUser, coach: CoachServiceDep
) -> CoachTurnRead:
    """Tu jugada: se etiqueta, el coach responde y, si fue un error, te lo comenta.

    Si has agotado tus respuestas del coach de esta hora, la jugada va igual pero sin
    comentario (lo dice `note`)."""
    try:
        turno = coach.move(user, game_id, body.move)
    except IllegalMoveError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from None
    except GameOverError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None
    except EngineUnavailableError as e:
        raise _sin_motor(e) from None
    if turno is None:
        raise _no_encontrada()
    return turno


@router.post(
    "/{game_id}/ask",
    response_model=CoachTurnRead,
    responses={
        429: {"description": "Has agotado tus respuestas del coach de la última hora"},
        503: {"description": "Ningún LLM ni Stockfish disponible"},
    },
)
def ask(game_id: int, body: CoachAskRequest, user: CurrentUser, coach: CoachServiceDep) -> CoachTurnRead:
    """Pregúntale al coach por la partida: quién va mejor, qué plan seguir, qué falló…"""
    try:
        turno = coach.ask(user, game_id, body.question)
    except CoachRateLimitError as e:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, str(e), headers={"Retry-After": "3600"}
        ) from None
    except (CoachLLMUnavailableError, EngineUnavailableError) as e:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, f"El coach no puede responder ahora: {e}"
        ) from None
    if turno is None:
        raise _no_encontrada()
    return turno


@router.post(
    "/{game_id}/draw",
    response_model=CoachDrawRead,
    responses={**_SIN_MOTOR, 409: {"description": "La partida ya terminó"}},
)
def offer_draw(game_id: int, user: CurrentUser, coach: CoachServiceDep) -> CoachDrawRead:
    """Ofreces tablas (o aceptas las que te ofreció el coach). El coach las acepta si va peor,
    o desde la jugada 15 si la posición está igualada; si no, te dice por qué sigue."""
    try:
        respuesta = coach.offer_draw(user, game_id)
    except GameOverError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None
    except EngineUnavailableError as e:
        raise _sin_motor(e) from None
    if respuesta is None:
        raise _no_encontrada()
    return respuesta


@router.post(
    "/{game_id}/resign",
    response_model=CoachGameRead,
    responses={409: {"description": "La partida ya terminó"}},
)
def resign(game_id: int, user: CurrentUser, coach: CoachServiceDep) -> CoachGameRead:
    """Te rindes: la partida termina con victoria del coach (`termination: resignation`)."""
    try:
        partida = coach.resign(user, game_id)
    except GameOverError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None
    if partida is None:
        raise _no_encontrada()
    return partida


@router.post("/{game_id}/draw/decline", status_code=status.HTTP_204_NO_CONTENT)
def decline_draw(game_id: int, user: CurrentUser, coach: CoachServiceDep) -> Response:
    """Rechazas la oferta de tablas del coach y sigues jugando."""
    if not coach.decline_draw(user, game_id):
        raise _no_encontrada()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{game_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_game(game_id: int, user: CurrentUser, coach: CoachServiceDep) -> Response:
    if not coach.delete(user, game_id):
        raise _no_encontrada()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
