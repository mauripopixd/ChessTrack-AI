"""Tablas de la base de datos (SQLAlchemy 2.0, estilo tipado con Mapped).

Esquema (docs/etapa1-guia.md, Bloque 2):
    users  1 ── * games  1 ── * moves  1 ── 1 move_analysis
    users  1 ── * coach_games  1 ── * coach_messages      (Etapa 5B)

Las reglas importantes se aplican en la propia BD (UNIQUE, CHECK, FK), no solo
en Python: así ninguna ruta del código puede saltárselas.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

RESULTADOS = ("1-0", "0-1", "1/2-1/2", "*")
ETIQUETAS = ("buena", "imprecision", "error", "error_grave")  # app/analysis.py
COLORES = ("white", "black")
ROLES = ("user", "coach")


def _in(columna: str, valores: tuple[str, ...]) -> str:
    return f"{columna} IN ({', '.join(repr(v) for v in valores)})"


class User(Base):
    __tablename__ = "users"
    # eager_defaults: el INSERT devuelve (RETURNING) los valores que pone la BD, como
    # created_at; sin esto, con expire_on_commit=False quedarían en None tras el commit.
    __mapper_args__ = {"eager_defaults": True}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)  # 320 = máximo de RFC 5321
    username: Mapped[str] = mapped_column(String(50), unique=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    games: Mapped[list["Game"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )

    def __repr__(self) -> str:
        return f"User(id={self.id}, username={self.username!r})"


class Game(Base):
    __tablename__ = "games"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        # La misma partida no se guarda dos veces para un usuario,
        # pero dos usuarios sí pueden subir la misma partida.
        UniqueConstraint("user_id", "pgn_hash"),
        CheckConstraint(_in("result", RESULTADOS), name="result_valido"),
        CheckConstraint(f"user_color IS NULL OR {_in('user_color', COLORES)}", name="user_color_valido"),
        # GET /games filtra por user_id y ordena por (created_at, id). Con el id en el índice,
        # PostgreSQL lee solo las 20 filas de la página, sin ordenar (ver docs/decisiones.md).
        Index("ix_games_user_id_created_at_id", "user_id", "created_at", "id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    pgn_raw: Mapped[str] = mapped_column(Text)
    pgn_hash: Mapped[str] = mapped_column(String(64))  # SHA-256 en hexadecimal
    white: Mapped[str | None] = mapped_column(String(100))
    black: Mapped[str | None] = mapped_column(String(100))
    result: Mapped[str] = mapped_column(String(7))
    played_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_color: Mapped[str | None] = mapped_column(String(5))  # None si no jugó el usuario
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Rellenos por POST /games/{id}/analysis; NULL = sin analizar.
    analysis_depth: Mapped[int | None] = mapped_column(Integer)
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="games")
    moves: Mapped[list["Move"]] = relationship(
        back_populates="game",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Move.ply",
    )

    def __repr__(self) -> str:
        return f"Game(id={self.id}, {self.white} vs {self.black}, {self.result})"


class Move(Base):
    __tablename__ = "moves"
    __table_args__ = (
        UniqueConstraint("game_id", "ply"),
        CheckConstraint("ply >= 1", name="ply_positivo"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"))
    ply: Mapped[int] = mapped_column(Integer)
    san: Mapped[str] = mapped_column(String(10))  # el más largo posible: "Qa1xb2+" / "exd8=Q#"
    uci: Mapped[str] = mapped_column(String(5))  # "e7e8q"
    fen_after: Mapped[str] = mapped_column(String(100))  # una FEN ocupa como mucho ~90

    game: Mapped[Game] = relationship(back_populates="moves")
    analysis: Mapped["MoveAnalysis | None"] = relationship(
        back_populates="move", cascade="all, delete-orphan", passive_deletes=True, uselist=False
    )

    def __repr__(self) -> str:
        return f"Move(game_id={self.game_id}, ply={self.ply}, san={self.san!r})"


class MoveAnalysis(Base):
    """Evaluación de Stockfish (y del clasificador) de una jugada. Tabla aparte de `moves`:
    las jugadas existen desde que se sube la partida; el análisis, solo si se pide, y se
    puede rehacer (p. ej. a más profundidad) sin tocar las jugadas."""

    __tablename__ = "move_analysis"
    __table_args__ = (CheckConstraint(_in("label", ETIQUETAS), name="label_valida"),)

    move_id: Mapped[int] = mapped_column(ForeignKey("moves.id", ondelete="CASCADE"), primary_key=True)
    eval_before: Mapped[int] = mapped_column(Integer)  # cp desde blancas; mate = ±10.000
    eval_after: Mapped[int] = mapped_column(Integer)
    cp_loss: Mapped[int] = mapped_column(Integer)
    win_drop: Mapped[float] = mapped_column(Float)  # puntos de probabilidad perdidos (0-100)
    label: Mapped[str] = mapped_column(String(12))
    best_uci: Mapped[str | None] = mapped_column(String(5))
    error_prob: Mapped[float | None] = mapped_column(Float)  # clasificador; NULL si no hay modelo
    brilliant: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())

    move: Mapped[Move] = relationship(back_populates="analysis")


class CoachGameRecord(Base):
    """Partida contra el coach (Etapa 5B). Las jugadas van como JSONB con su informe
    (app.coach.game.MoveReport): siempre se leen y escriben enteras con la partida, nunca
    se consultan sueltas, así que una tabla por jugada solo añadiría joins."""

    __tablename__ = "coach_games"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        CheckConstraint(_in("user_color", COLORES), name="user_color_valido"),
        CheckConstraint("level BETWEEN 0 AND 20", name="level_valido"),
        CheckConstraint(_in("result", RESULTADOS), name="result_valido"),
        Index("ix_coach_games_user_id_created_at_id", "user_id", "created_at", "id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    user_color: Mapped[str] = mapped_column(String(5))
    level: Mapped[int] = mapped_column(Integer)  # Skill Level de Stockfish
    moves: Mapped[list[dict]] = mapped_column(JSONB, default=list)  # MoveReport en orden
    result: Mapped[str] = mapped_column(String(7), default="*")
    termination: Mapped[str | None] = mapped_column(String(30))  # "checkmate", "agreement"…
    # Oferta de tablas del coach pendiente de respuesta ("coach") y jugada en que la hizo
    # (para no repetirla enseguida). Jugar una jugada la rechaza.
    draw_offer: Mapped[str | None] = mapped_column(String(5))
    last_draw_offer_ply: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    messages: Mapped[list["CoachMessage"]] = relationship(
        back_populates="game", cascade="all, delete-orphan", passive_deletes=True, order_by="CoachMessage.id"
    )

    def __repr__(self) -> str:
        return f"CoachGameRecord(id={self.id}, user_id={self.user_id}, jugadas={len(self.moves)})"


class CoachMessage(Base):
    """Chat de una partida con el coach: preguntas del usuario y respuestas del LLM.
    `user_id` repetido a propósito: el límite por usuario cuenta sus respuestas de la última
    hora con el índice (user_id, created_at), sin join con coach_games."""

    __tablename__ = "coach_messages"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        CheckConstraint(_in("role", ROLES), name="role_valido"),
        Index("ix_coach_messages_user_id_created_at", "user_id", "created_at"),
        Index("ix_coach_messages_game_id", "game_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("coach_games.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(5))
    content: Mapped[str] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(String(100))  # qué LLM respondió (solo role="coach")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    game: Mapped[CoachGameRecord] = relationship(back_populates="messages")
