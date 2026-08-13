"""default gemini-3.7-flash and drop gemini-3.6-flash

Revision ID: e5c3a91b8d47
Revises: f0a9b6c31d75
Create Date: 2026-08-13 11:15:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "e5c3a91b8d47"
down_revision: Union[str, None] = "f0a9b6c31d75"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # gemini-3.7-flash replaces gemini-3.6-flash in MODEL_SPECS, so stored rows
    # move with it — an id no longer in the registry is a KeyError in
    # llm.build_model on every message. It is also the only Google model, so it
    # takes over as the column's server_default and as the model that serves
    # documents whose selected model has supports_files=False.
    op.execute(
        "UPDATE users SET summarizing_model = 'gemini-3.7-flash' "
        "WHERE summarizing_model = 'gemini-3.6-flash'",
    )
    op.alter_column(
        "users",
        "summarizing_model",
        existing_type=sa.VARCHAR(),
        server_default="gemini-3.7-flash",
        existing_nullable=False,
    )


def downgrade() -> None:
    # The row rewrite is not reversed: gemini-3.6-flash is gone from
    # MODEL_SPECS, so restoring it would leave users on an unselectable id.
    # Same choice as 6bb4ed473ffd, 12d7c48a6e14, b3f9c1d47a20, c7a2e5b0913f,
    # d4e81f60c2ab and f0a9b6c31d75. The server_default is restored so the
    # column matches the schema the previous revision left behind.
    op.alter_column(
        "users",
        "summarizing_model",
        existing_type=sa.VARCHAR(),
        server_default="gemini-3.6-flash",
        existing_nullable=False,
    )
