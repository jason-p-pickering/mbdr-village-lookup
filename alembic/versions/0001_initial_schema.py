"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-02-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table(
        "townships",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("uid", sa.String(11), unique=True, nullable=False),
        sa.Column("code", sa.String(255), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
    )

    op.create_table(
        "wards",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("uid", sa.String(11), unique=True, nullable=False),
        sa.Column("code", sa.String(255), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("township_id", sa.Integer, sa.ForeignKey("townships.id"), nullable=False),
    )

    op.create_table(
        "villages",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("uid", sa.String(11), unique=True, nullable=False),
        sa.Column("code", sa.String(255), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("township_id", sa.Integer, sa.ForeignKey("townships.id"), nullable=False),
    )

    op.create_index(
        "idx_wards_name_trgm",
        "wards",
        ["name"],
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )
    op.create_index("idx_wards_township", "wards", ["township_id"])

    op.create_index(
        "idx_villages_name_trgm",
        "villages",
        ["name"],
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )
    op.create_index("idx_villages_township", "villages", ["township_id"])


def downgrade() -> None:
    op.drop_index("idx_villages_township", table_name="villages")
    op.drop_index("idx_villages_name_trgm", table_name="villages")
    op.drop_table("villages")
    op.drop_index("idx_wards_township", table_name="wards")
    op.drop_index("idx_wards_name_trgm", table_name="wards")
    op.drop_table("wards")
    op.drop_table("townships")
