"""indice de listado con id para desempatar

Revision ID: 57ca8e8495e7
Revises: 4cfb8e406362
Create Date: 2026-11-21

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "57ca8e8495e7"
down_revision: Union[str, Sequence[str], None] = "4cfb8e406362"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # (user_id, created_at, id) cubre el ORDER BY created_at DESC, id DESC de GET /games:
    # PostgreSQL lee solo las filas de la página en vez de ordenar todo el grupo con el
    # mismo created_at. Primero se crea el nuevo y luego se borra el viejo, para que la
    # tabla nunca se quede sin índice. Medición en docs/decisiones.md.
    op.create_index("ix_games_user_id_created_at_id", "games", ["user_id", "created_at", "id"], unique=False)
    op.drop_index("ix_games_user_id_created_at", table_name="games")


def downgrade() -> None:
    op.create_index("ix_games_user_id_created_at", "games", ["user_id", "created_at"], unique=False)
    op.drop_index("ix_games_user_id_created_at_id", table_name="games")
