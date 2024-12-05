"""empty message

Revision ID: e1d54080707f
Revises: dea241345bca
Create Date: 2024-12-05 12:36:58.474752

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e1d54080707f"
down_revision: Union[str, None] = "dea241345bca"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("users", "parsing_strategy")
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column(
        "users",
        sa.Column(
            "parsing_strategy",
            sa.VARCHAR(),
            server_default=sa.text("'requests'::character varying"),
            autoincrement=False,
            nullable=False,
        ),
    )
    # ### end Alembic commands ###
