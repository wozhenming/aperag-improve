"""add ontology table

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-07-31 00:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ontology",
        sa.Column("id", sa.String(24), primary_key=True),
        sa.Column("user", sa.String(256), nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("file_path", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("gmt_created", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("gmt_updated", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("gmt_deleted", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_ontology_user_status", "ontology", ["user", "status"])


def downgrade() -> None:
    op.drop_index("idx_ontology_user_status", table_name="ontology")
    op.drop_table("ontology")
