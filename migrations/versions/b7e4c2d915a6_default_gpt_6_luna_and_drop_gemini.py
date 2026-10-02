"""default openai/gpt-6-luna, drop gemini-3.8-flash

Revision ID: b7e4c2d915a6
Revises: a9d2f4c6e813
Create Date: 2026-10-02 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b7e4c2d915a6"
down_revision: Union[str, None] = "a9d2f4c6e813"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # OpenRouter is the only provider left, so gemini-3.8-flash leaves
    # MODEL_SPECS. A stored id outside the registry is a KeyError in
    # summary.summarize_with_document and a 400 from OpenRouter everywhere else,
    # so every such row moves to the new default, which also serves documents
    # for models with supports_files=False.
    op.execute(
        "UPDATE users SET summarizing_model = 'openai/gpt-6-luna' "
        "WHERE summarizing_model NOT IN ("
        "'deepseek/deepseek-v4.1-flash', 'openai/gpt-6-luna', 'x-ai/grok-4.7')",
    )
    op.alter_column(
        "users",
        "summarizing_model",
        existing_type=sa.VARCHAR(),
        server_default="openai/gpt-6-luna",
        existing_nullable=False,
    )


def downgrade() -> None:
    # The row rewrite is not reversed: which rows held gemini-3.8-flash was not
    # kept. Same choice as a9d2f4c6e813. The server_default is restored so the
    # column matches the schema the previous revision left behind.
    op.alter_column(
        "users",
        "summarizing_model",
        existing_type=sa.VARCHAR(),
        server_default="gemini-3.8-flash",
        existing_nullable=False,
    )
