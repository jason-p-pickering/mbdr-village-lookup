"""add name_my translation column

Revision ID: 0002
Revises: 0001
Create Date: 2026-02-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("townships", sa.Column("name_my", sa.String(255), nullable=True))
    op.add_column("wards", sa.Column("name_my", sa.String(255), nullable=True))
    op.add_column("villages", sa.Column("name_my", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("villages", "name_my")
    op.drop_column("wards", "name_my")
    op.drop_column("townships", "name_my")
