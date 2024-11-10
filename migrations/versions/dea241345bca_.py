"""empty message

Revision ID: dea241345bca
Revises: 296e8837ca37
Create Date: 2024-11-10 14:06:38.606960

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "dea241345bca"
down_revision: Union[str, None] = "296e8837ca37"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column(
        "users",
        sa.Column(
            "parsing_strategy",
            sa.String(),
            server_default="requests",
            nullable=False,
        ),
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("users", "parsing_strategy")
    # ### end Alembic commands ###
