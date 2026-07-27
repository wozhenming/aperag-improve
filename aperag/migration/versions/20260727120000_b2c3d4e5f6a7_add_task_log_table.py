"""add task_log table

Revision ID: b2c3d4e5f6a7
Revises: 72de1ba2de3f
Create Date: 2026-07-27 12:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = '72de1ba2de3f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "task_log",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("collection_id", sa.String(24), nullable=True),
        sa.Column("document_id", sa.String(24), nullable=True),
        sa.Column("index_type", sa.String(32), nullable=True),
        sa.Column("level", sa.String(16), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_tasklog_coll_doc", "task_log", ["collection_id", "document_id"])
    op.create_index("ix_task_log_created_at", "task_log", ["created_at"])


def downgrade() -> None:
    op.drop_index("idx_tasklog_coll_doc", table_name="task_log")
    op.drop_index("ix_task_log_created_at", table_name="task_log")
    op.drop_table("task_log")
