"""default gemini-3.5-flash-lite and high thinking

Revision ID: 96da01ef8da4
Revises: 75c166144434
Create Date: 2026-07-21 14:18:18.761526

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "96da01ef8da4"
down_revision: Union[str, None] = "75c166144434"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "users",
        "summarizing_model",
        existing_type=sa.VARCHAR(),
        server_default="gemini-3.5-flash-lite",
        existing_nullable=False,
    )
    op.alter_column(
        "users",
        "thinking_level",
        existing_type=sa.VARCHAR(),
        server_default="HIGH",
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "users",
        "summarizing_model",
        existing_type=sa.VARCHAR(),
        server_default="gemini-3.5-flash",
        existing_nullable=False,
    )
    op.alter_column(
        "users",
        "thinking_level",
        existing_type=sa.VARCHAR(),
        server_default="MINIMAL",
        existing_nullable=False,
    )
