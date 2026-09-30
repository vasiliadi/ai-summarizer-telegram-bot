"""default gemini-3.8-flash, swap openrouter models, reset thinking levels

Revision ID: a9d2f4c6e813
Revises: e5c3a91b8d47
Create Date: 2026-09-29 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a9d2f4c6e813"
down_revision: Union[str, None] = "e5c3a91b8d47"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # MODEL_SPECS is replaced wholesale, and an id no longer in it is a KeyError
    # in llm.build_model on every message, so every stored row moves: to the
    # same vendor's successor where one is registered, to the new default
    # otherwise. gemini-3.8-flash is the only Google model, so it takes over as
    # the column's server_default and as the model that serves documents whose
    # selected model has supports_files=False.
    op.execute(
        "UPDATE users SET summarizing_model = CASE summarizing_model "
        "WHEN 'openai/gpt-5.6-luna' THEN 'openai/gpt-6-luna' "
        "ELSE 'gemini-3.8-flash' END "
        "WHERE summarizing_model NOT IN ("
        "'deepseek/deepseek-v4.1-flash', 'gemini-3.8-flash', "
        "'openai/gpt-6-luna', 'x-ai/grok-4.7')",
    )
    op.alter_column(
        "users",
        "summarizing_model",
        existing_type=sa.VARCHAR(),
        server_default="gemini-3.8-flash",
        existing_nullable=False,
    )
    # A level picked for the old model says nothing about the new one, so every
    # user restarts from DEFAULT_THINKING_LEVEL.
    op.execute("UPDATE users SET thinking_level = 'medium'")


def downgrade() -> None:
    # The row rewrites are not reversed: the old ids are gone from MODEL_SPECS,
    # and the previous thinking levels were not kept. Same choice as
    # e5c3a91b8d47. The server_default is restored so the column matches the
    # schema the previous revision left behind.
    op.alter_column(
        "users",
        "summarizing_model",
        existing_type=sa.VARCHAR(),
        server_default="gemini-3.7-flash",
        existing_nullable=False,
    )
