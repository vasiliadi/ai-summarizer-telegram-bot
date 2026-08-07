"""lowercase thinking levels and default gemini-3.6-flash

Revision ID: 12d7c48a6e14
Revises: 96da01ef8da4
Create Date: 2026-08-07 10:29:41.219649

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "12d7c48a6e14"
down_revision: Union[str, None] = "96da01ef8da4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE users SET thinking_level = lower(thinking_level)")
    op.execute(
        "UPDATE users SET summarizing_model = 'gemini-3.6-flash' "
        "WHERE summarizing_model = 'gemini-3.5-flash'",
    )
    op.alter_column(
        "users",
        "summarizing_model",
        existing_type=sa.VARCHAR(),
        server_default="gemini-3.6-flash",
        existing_nullable=False,
    )
    op.alter_column(
        "users",
        "thinking_level",
        existing_type=sa.VARCHAR(),
        server_default="medium",
        existing_nullable=False,
    )


def downgrade() -> None:
    # The summarizing_model rewrite is not reversed: gemini-3.5-flash is gone
    # from MODEL_SPECS, so restoring it would leave users on an unselectable id.
    # Same choice as 6bb4ed473ffd, which dropped the previous legacy models.
    # xhigh has no counterpart in the vocabulary being restored, so a plain
    # upper() would leave those users on XHIGH — absent from the old allow-list
    # and rejected by Gemini, with nothing to heal it but re-picking a level.
    # Collapse it onto HIGH, which is what pydantic-ai does going forward.
    op.execute(
        "UPDATE users SET thinking_level = CASE "
        "WHEN lower(thinking_level) = 'xhigh' THEN 'HIGH' "
        "ELSE upper(thinking_level) END",
    )
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
