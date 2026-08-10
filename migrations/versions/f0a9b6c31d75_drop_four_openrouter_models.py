"""drop four openrouter models

Revision ID: f0a9b6c31d75
Revises: d4e81f60c2ab
Create Date: 2026-08-10 12:40:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "f0a9b6c31d75"
down_revision: Union[str, None] = "d4e81f60c2ab"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # An id no longer in MODEL_SPECS is a KeyError in llm.build_model on every
    # message, so stored rows move to the nearest surviving model. None of the
    # four vendors has one left in the registry, so every row takes the default.
    #
    # Runs after b3f9c1d47a20, which parks qwen/qwen3.7-flash rows on
    # qwen/qwen3.8-max — an id this revision then drops. The order is what makes
    # that safe: those rows are caught here.
    op.execute(
        "UPDATE users SET summarizing_model = 'gemini-3.6-flash' "
        "WHERE summarizing_model IN ("
        "'inclusionai/ling-3.0-flash:free', "
        "'nvidia/nemotron-3-ultra-550b-a55b:free', "
        "'poolside/laguna-s-2.1:free', 'qwen/qwen3.8-max')",
    )


def downgrade() -> None:
    # Not reversed: the four ids are gone from MODEL_SPECS, so restoring them
    # would leave users on an unselectable id. Same choice as 6bb4ed473ffd,
    # 12d7c48a6e14, b3f9c1d47a20, c7a2e5b0913f and d4e81f60c2ab.
    pass
