"""drop legacy gemini models

Revision ID: 6bb4ed473ffd
Revises: 10c9ae0e381a
Create Date: 2026-05-25 19:32:52.521315

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "6bb4ed473ffd"
down_revision: Union[str, None] = "10c9ae0e381a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE users SET summarizing_model = 'gemini-3.5-flash' "
        "WHERE summarizing_model IN ('gemini-2.5-flash', 'gemini-3-flash-preview')",
    )


def downgrade() -> None:
    pass
