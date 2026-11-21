"""Tablas de la base de datos (SQLAlchemy 2.0, estilo tipado con Mapped).

Esquema (docs/etapa1-guia.md, Bloque 2):
    users  1 ── * games  1 ── * moves

Las reglas importantes se aplican en la propia BD (UNIQUE, CHECK, FK), no solo
en Python: así ninguna ruta del código puede saltárselas.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

RESULTADOS = ("1-0", "0-1", "1/2-1/2", "*")
COLORES = ("white", "black")


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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

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

    def __repr__(self) -> str:
        return f"Move(game_id={self.game_id}, ply={self.ply}, san={self.san!r})"
