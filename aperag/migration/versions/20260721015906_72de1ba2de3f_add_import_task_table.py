"""add import_task table

Revision ID: 72de1ba2de3f
Revises: a1b2c3d4e5f6
Create Date: 2026-07-21 01:59:06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '72de1ba2de3f'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "import_task",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user", sa.String(256), nullable=False, index=True),
        sa.Column("zip_path", sa.Text, nullable=True),
        sa.Column("collection_title", sa.String(256), nullable=True),
        sa.Column("collection_id", sa.String(24), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="PENDING"),
        sa.Column("progress", sa.Integer, server_default="0"),
        sa.Column("message", sa.Text, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("gmt_created", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("gmt_updated", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("gmt_completed", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_import_task_user_status", "import_task", ["user", "status"])


def downgrade() -> None:
    op.drop_index("idx_import_task_user_status", table_name="import_task")
    op.drop_table("import_task")
