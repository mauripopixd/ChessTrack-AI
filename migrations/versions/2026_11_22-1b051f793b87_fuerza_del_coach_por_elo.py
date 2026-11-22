"""fuerza del coach por elo

Revision ID: 1b051f793b87
Revises: 4dd576a09431
Create Date: 2026-11-22 09:07:05.171005

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1b051f793b87"
down_revision: Union[str, Sequence[str], None] = "4dd576a09431"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Las partidas nuevas eligen la fuerza por ELO; las viejas conservan su Skill Level
    op.add_column("coach_games", sa.Column("elo", sa.Integer(), nullable=True))
    op.alter_column("coach_games", "level", existing_type=sa.Integer(), nullable=True)
    op.create_check_constraint(op.f("ck_coach_games_elo_valido"), "coach_games", "elo BETWEEN 400 AND 3190")
    op.create_check_constraint(
        op.f("ck_coach_games_con_fuerza"), "coach_games", "level IS NOT NULL OR elo IS NOT NULL"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f("ck_coach_games_con_fuerza"), "coach_games", type_="check")
    op.drop_constraint(op.f("ck_coach_games_elo_valido"), "coach_games", type_="check")
    op.execute("UPDATE coach_games SET level = 5 WHERE level IS NULL")
    op.alter_column("coach_games", "level", existing_type=sa.Integer(), nullable=False)
    op.drop_column("coach_games", "elo")
