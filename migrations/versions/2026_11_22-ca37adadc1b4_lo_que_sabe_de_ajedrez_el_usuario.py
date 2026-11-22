"""lo que sabe de ajedrez el usuario

Revision ID: ca37adadc1b4
Revises: 1b051f793b87
Create Date: 2026-11-22 09:50:35.984725

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ca37adadc1b4"
down_revision: Union[str, Sequence[str], None] = "1b051f793b87"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Cómo le habla el coach: las partidas que ya existían, como hasta ahora ("advanced")
    op.add_column(
        "coach_games",
        sa.Column("knowledge", sa.String(length=8), server_default="advanced", nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_coach_games_knowledge_valido"), "coach_games", "knowledge IN ('none', 'basic', 'advanced')"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f("ck_coach_games_knowledge_valido"), "coach_games", type_="check")
    op.drop_column("coach_games", "knowledge")
