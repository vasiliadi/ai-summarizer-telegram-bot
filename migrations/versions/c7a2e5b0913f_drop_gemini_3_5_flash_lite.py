"""drop gemini-3.5-flash-lite

Revision ID: c7a2e5b0913f
Revises: b3f9c1d47a20
Create Date: 2026-08-07 20:35:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c7a2e5b0913f"
down_revision: Union[str, None] = "b3f9c1d47a20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # gemini-3.6-flash is the only Google model left, and already the column's
    # server_default since 12d7c48a6e14, so no default has to move with it.
    op.execute(
        "UPDATE users SET summarizing_model = 'gemini-3.6-flash' "
        "WHERE summarizing_model = 'gemini-3.5-flash-lite'",
    )


def downgrade() -> None:
    # Not reversed: gemini-3.5-flash-lite is gone from MODEL_SPECS, so restoring
    # it would leave users on an unselectable id. Same choice as 6bb4ed473ffd,
    # 12d7c48a6e14 and b3f9c1d47a20.
    pass
