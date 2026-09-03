"""Add optional explicit habit tracking start date."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "ab12cd34ef56"
down_revision: Union[str, Sequence[str], None] = "6d7e8f9a0b1c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("habits", sa.Column("tracking_start_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("habits", "tracking_start_date")
