"""drop five openrouter models

Revision ID: b3f9c1d47a20
Revises: 12d7c48a6e14
Create Date: 2026-08-07 19:05:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b3f9c1d47a20"
down_revision: Union[str, None] = "12d7c48a6e14"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # An id no longer in MODEL_SPECS is a KeyError in llm.build_model on every
    # message, so stored rows move to the nearest surviving model: the same
    # vendor where one is left, the default otherwise.
    op.execute(
        "UPDATE users SET summarizing_model = CASE summarizing_model "
        "WHEN 'deepseek/deepseek-v4-pro' THEN 'deepseek/deepseek-v4-flash-0731' "
        "WHEN 'openai/gpt-5.6-terra' THEN 'openai/gpt-5.6-luna' "
        "WHEN 'qwen/qwen3.7-flash' THEN 'qwen/qwen3.8-max' "
        "ELSE 'gemini-3.6-flash' END "
        "WHERE summarizing_model IN ("
        "'deepseek/deepseek-v4-pro', 'openai/gpt-5.6-terra', "
        "'qwen/qwen3.7-flash', 'tencent/hy3', 'xiaomi/mimo-v2.5')",
    )


def downgrade() -> None:
    # Not reversed: the five ids are gone from MODEL_SPECS, so restoring them
    # would leave users on an unselectable id. Same choice as 6bb4ed473ffd and
    # 12d7c48a6e14, which dropped the previous legacy models.
    pass
