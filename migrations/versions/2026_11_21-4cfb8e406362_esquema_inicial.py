"""esquema inicial: users, games, moves

Revision ID: 4cfb8e406362
Revises:
Create Date: 2026-11-21

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4cfb8e406362"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("username", sa.String(length=50), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
        sa.UniqueConstraint("username", name=op.f("uq_users_username")),
    )
    op.create_table(
        "games",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("pgn_raw", sa.Text(), nullable=False),
        sa.Column("pgn_hash", sa.String(length=64), nullable=False),
        sa.Column("white", sa.String(length=100), nullable=True),
        sa.Column("black", sa.String(length=100), nullable=True),
        sa.Column("result", sa.String(length=7), nullable=False),
        sa.Column("played_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_color", sa.String(length=5), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "result IN ('1-0', '0-1', '1/2-1/2', '*')", name=op.f("ck_games_result_valido")
        ),
        sa.CheckConstraint(
            "user_color IS NULL OR user_color IN ('white', 'black')",
            name=op.f("ck_games_user_color_valido"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_games_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_games")),
        sa.UniqueConstraint("user_id", "pgn_hash", name=op.f("uq_games_user_id_pgn_hash")),
    )
    op.create_index("ix_games_user_id_created_at", "games", ["user_id", "created_at"], unique=False)
    op.create_table(
        "moves",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("game_id", sa.BigInteger(), nullable=False),
        sa.Column("ply", sa.Integer(), nullable=False),
        sa.Column("san", sa.String(length=10), nullable=False),
        sa.Column("uci", sa.String(length=5), nullable=False),
        sa.Column("fen_after", sa.String(length=100), nullable=False),
        sa.CheckConstraint("ply >= 1", name=op.f("ck_moves_ply_positivo")),
        sa.ForeignKeyConstraint(
            ["game_id"], ["games.id"], name=op.f("fk_moves_game_id_games"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_moves")),
        sa.UniqueConstraint("game_id", "ply", name=op.f("uq_moves_game_id_ply")),
    )


def downgrade() -> None:
    op.drop_table("moves")
    op.drop_index("ix_games_user_id_created_at", table_name="games")
    op.drop_table("games")
    op.drop_table("users")
