"""drop anthropic/claude-opus-5.5

Revision ID: d9b3e7a1c452
Revises: c3f8a1d27e94
Create Date: 2026-10-18 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d9b3e7a1c452"
down_revision: Union[str, None] = "c3f8a1d27e94"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # anthropic/claude-opus-5.5 leaves MODEL_SPECS; its rows move to the default.
    # A row the previous release writes after this ran is not caught here:
    # handlers.MessageHandlers._settings substitutes the default for it.
    op.execute(
        "UPDATE users SET summarizing_model = 'openai/gpt-6-luna' "
        "WHERE summarizing_model NOT IN ("
        "'deepseek/deepseek-v4.1-flash', 'openai/gpt-6-luna')",
    )


def downgrade() -> None:
    # The row rewrite is not reversed: which rows held claude-opus-5.5 was not
    # kept. Same choice as b7e4c2d915a6.
    pass
