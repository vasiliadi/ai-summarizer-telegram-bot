"""swap x-ai/grok-4.7 for anthropic/claude-opus-5.5

Revision ID: c3f8a1d27e94
Revises: b7e4c2d915a6
Create Date: 2026-10-06 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3f8a1d27e94"
down_revision: Union[str, None] = "b7e4c2d915a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # x-ai/grok-4.7 leaves MODEL_SPECS. Its rows move to the default rather
    # than to its replacement, anthropic/claude-opus-5.5, which is expensive and
    # meant to be picked by hand for reference summaries.
    # A row the previous release writes after this ran is not caught here:
    # handlers.MessageHandlers._settings substitutes the default for it.
    op.execute(
        "UPDATE users SET summarizing_model = 'openai/gpt-6-luna' "
        "WHERE summarizing_model NOT IN ("
        "'anthropic/claude-opus-5.5', 'deepseek/deepseek-v4.1-flash', "
        "'openai/gpt-6-luna')",
    )


def downgrade() -> None:
    # The row rewrite is not reversed: which rows held grok-4.7 was not kept.
    # Same choice as b7e4c2d915a6.
    pass
