"""drop three openrouter models

Revision ID: d4e81f60c2ab
Revises: c7a2e5b0913f
Create Date: 2026-08-07 21:20:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "d4e81f60c2ab"
down_revision: Union[str, None] = "c7a2e5b0913f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # An id no longer in MODEL_SPECS is a KeyError in llm.build_model on every
    # message, so stored rows move to the nearest surviving model. Only
    # thinkingmachines still has one; the other two vendors are gone from the
    # registry entirely, so those rows take the default.
    #
    # Runs after b3f9c1d47a20, which parks deepseek/deepseek-v4-pro rows on
    # deepseek/deepseek-v4-flash-0731 — an id this revision then drops. The
    # order is what makes that safe: those rows are caught here.
    op.execute(
        "UPDATE users SET summarizing_model = CASE summarizing_model "
        "WHEN 'thinkingmachines/inkling-small' THEN 'thinkingmachines/inkling' "
        "ELSE 'gemini-3.6-flash' END "
        "WHERE summarizing_model IN ("
        "'deepseek/deepseek-v4-flash-0731', 'thinkingmachines/inkling-small', "
        "'z-ai/glm-5.2')",
    )


def downgrade() -> None:
    # Not reversed: the three ids are gone from MODEL_SPECS, so restoring them
    # would leave users on an unselectable id. Same choice as 6bb4ed473ffd,
    # 12d7c48a6e14, b3f9c1d47a20 and c7a2e5b0913f.
    pass
