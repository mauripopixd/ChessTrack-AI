"""Schemas de Pydantic: lo que entra y sale de la API.

Van separados de los modelos de SQLAlchemy (decisión del proyecto, no SQLModel):
la forma de la tabla y la forma de la API cambian por motivos distintos, y así
nunca se devuelve por error un campo interno como `hashed_password`.
"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, StringConstraints

# Email y username se guardan en minúsculas: "Ana" y "ana" son el mismo usuario.
Email = Annotated[EmailStr, Field(max_length=320), AfterValidator(str.lower)]
Username = Annotated[
    str,
    StringConstraints(strip_whitespace=True, to_lower=True, pattern=r"^[A-Za-z0-9_-]{3,50}$"),
]
# 128 como máximo: Argon2 acepta más, pero limita el coste de un ataque con contraseñas enormes.
Password = Annotated[str, Field(min_length=8, max_length=128)]


class UserCreate(BaseModel):
    email: Email
    username: Username = Field(description="3-50 caracteres: letras, números, _ o -")
    password: Password


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)  # permite construirlo desde un User

    id: int
    email: str
    username: str
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="segundos hasta que caduca")


# ---------------------------------------------------------------- partidas


class GameSummary(BaseModel):
    """Una partida en listados: sin el PGN ni las jugadas, que pueden pesar mucho."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    white: str | None
    black: str | None
    result: str
    played_at: datetime | None
    user_color: str | None = Field(description="'white', 'black' o null si no jugaste tú")
    move_count: int = Field(description="medios movimientos (ply)")
    created_at: datetime


class GameDetail(GameSummary):
    pgn: str


class MoveRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ply: int
    san: str
    uci: str
    fen_after: str


class GamePage(BaseModel):
    items: list[GameSummary]
    total: int = Field(description="partidas que cumplen los filtros, sin paginar")
    limit: int
    offset: int


class ImportDuplicate(BaseModel):
    index: int = Field(description="posición en el archivo, desde 0")
    game_id: int = Field(description="partida ya guardada")


class ImportFailure(BaseModel):
    index: int
    detail: str


class ImportResult(BaseModel):
    created: list[GameSummary]
    duplicates: list[ImportDuplicate]
    errors: list[ImportFailure]


# ---------------------------------------------------------------- análisis


class MoveAnalysisRead(BaseModel):
    ply: int
    move_number: int = Field(description="número de jugada como en una planilla (1. e4 e5 → 1 y 1)")
    san: str
    mover: str = Field(description="'white' o 'black'")
    is_user: bool | None = Field(description="null si no se sabe con qué color jugaste")
    eval_before: int = Field(description="centipeones desde blancas antes de la jugada (mate = ±10000)")
    eval_after: int
    cp_loss: int
    win_drop: float = Field(description="puntos de probabilidad de ganar perdidos (0-100)")
    label: str = Field(description="buena, imprecision, error o error_grave")
    best_move: str | None = Field(description="mejor jugada según Stockfish (SAN)")
    error_prob: float | None = Field(description="probabilidad de error según el clasificador")
    model_flag: bool | None = Field(description="el clasificador la marca como error")
    brilliant: bool = Field(default=False, description="sacrificio que es la mejor jugada (!!)")


class FlaggedMove(BaseModel):
    ply: int
    move_number: int
    san: str
    label: str
    cp_loss: int
    best_move: str | None


class AnalysisSummary(BaseModel):
    user_color: str | None
    moves_analyzed: int = Field(description="jugadas del usuario (o todas si no se sabe su color)")
    acpl: float | None = Field(description="pérdida media de centipeones por jugada")
    labels: dict[str, int]
    errors: list[FlaggedMove] = Field(description="errores y errores graves, en orden")


class ModelComparison(BaseModel):
    """Clasificador frente a Stockfish en esta partida (las mismas jugadas que el resumen)."""

    threshold: float
    stockfish_errors: int
    model_flags: int
    both: int = Field(description="errores que marcan los dos")
    precision: float | None = Field(description="de lo que marca el modelo, cuánto es error de verdad")
    recall: float | None = Field(description="de los errores de Stockfish, cuántos detecta el modelo")


class GameAnalysisRead(BaseModel):
    game_id: int
    depth: int
    analyzed_at: datetime
    summary: AnalysisSummary
    model: ModelComparison | None = Field(description="null si no hay clasificador cargado")
    moves: list[MoveAnalysisRead]


# ---------------------------------------------------------------- RAG de aperturas


class AskRequest(BaseModel):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=500)]


class CitationRead(BaseModel):
    n: int = Field(description="número de la marca [n] en la respuesta")
    title: str
    url: str
    license: str = Field(description="licencia de la fuente (CC BY-SA 4.0 obliga a citarla)")
    source: str = Field(description="wikibooks o lichess")
    opening: str | None = Field(description="nombre de la apertura según Lichess")
    eco: str | None
    moves: str


class AskResponse(BaseModel):
    question: str
    answer: str
    citations: list[CitationRead]
    provider: str | None = Field(description="groq u ollama (null si no hizo falta el LLM)")
    model: str | None
    latency_ms: int | None
    invalid_citations: list[int] = Field(description="marcas [n] sin fuente: posible invención")


# ---------------------------------------------------------------- coach (Etapa 5B)


class CoachGameCreate(BaseModel):
    color: Literal["white", "black"] = Field(default="white", description="con qué color juegas")
    level: int = Field(default=5, ge=0, le=20, description="fuerza del coach (Skill Level de Stockfish)")


class CoachMoveRequest(BaseModel):
    move: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=10)] = Field(
        description="SAN (Nf3, O-O, exd5) o UCI (g1f3)"
    )


class CoachAskRequest(BaseModel):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=500)]


class CoachMoveRead(BaseModel):
    ply: int
    san: str
    uci: str
    by: Literal["user", "coach"]
    label: str = Field(description="buena, imprecision, error o error_grave")
    eval_before: int = Field(description="centipeones desde blancas; mate = ±10.000")
    eval_after: int
    cp_loss: int
    win_drop: float = Field(description="puntos de probabilidad de ganar perdidos (0-100)")
    best_move: str | None = Field(description="mejor jugada según Stockfish (SAN)")
    fen_after: str | None = Field(default=None, description="posición tras la jugada (para animarla)")
    brilliant: bool = Field(default=False, description="sacrificio que es la mejor jugada (!!)")


class CoachMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    role: Literal["user", "coach"]
    content: str
    model: str | None
    created_at: datetime


class CoachGameSummary(BaseModel):
    id: int
    color: Literal["white", "black"]
    level: int
    result: str
    termination: str | None
    move_count: int
    created_at: datetime
    updated_at: datetime


class CoachGameRead(CoachGameSummary):
    fen: str
    your_turn: bool
    draw_offer: Literal["coach"] | None = Field(default=None, description="el coach ofrece tablas")
    legal_moves: list[str] = Field(description="tus jugadas legales en UCI (vacía si no es tu turno)")
    moves: list[CoachMoveRead]
    messages: list[CoachMessageRead]


class CoachGamePage(BaseModel):
    items: list[CoachGameSummary]
    total: int
    limit: int
    offset: int


class CoachTurnRead(BaseModel):
    your_move: CoachMoveRead | None
    coach_move: CoachMoveRead | None
    answer: str | None = Field(description="explicación del coach (pregunta o comentario de un error)")
    sources: list[str] = Field(description="fuentes citadas con [n]: '[n] título — url (licencia)'")
    model: str | None = Field(description="LLM que respondió")
    note: str | None = Field(description="por qué no hay comentario: límite alcanzado o LLM caído")
    fen: str
    your_turn: bool
    result: str
    termination: str | None
    draw_offer: Literal["coach"] | None = Field(default=None, description="el coach ofrece tablas")


class CoachDrawRead(BaseModel):
    accepted: bool
    message: str = Field(description="la respuesta del coach")
    result: str
    termination: str | None
