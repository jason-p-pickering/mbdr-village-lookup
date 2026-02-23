"""add icd10_codes table

Revision ID: 0003
Revises: 0002
Create Date: 2026-02-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "icd10_codes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("uid", sa.String(11), unique=True, nullable=False),
        sa.Column("code", sa.String(50), nullable=True),       # DHIS2 numeric key
        sa.Column("icd_code", sa.String(20), nullable=True),   # e.g. "A00.0"
        sa.Column("name", sa.String(500), nullable=False),     # full display name
    )

    # Trigram index for free-text search on the full name
    op.create_index(
        "idx_icd10_name_trgm",
        "icd10_codes",
        ["name"],
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )

    # Btree on icd_code for prefix lookups and natural ordering
    op.create_index("idx_icd10_icd_code", "icd10_codes", ["icd_code"])


def downgrade() -> None:
    op.drop_index("idx_icd10_icd_code", table_name="icd10_codes")
    op.drop_index("idx_icd10_name_trgm", table_name="icd10_codes")
    op.drop_table("icd10_codes")
