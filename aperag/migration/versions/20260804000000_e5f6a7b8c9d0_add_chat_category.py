"""add chat category column

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-08-04 00:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("chat", sa.Column("category", sa.String(50), nullable=True))
    op.create_index("ix_chat_category", "chat", ["category"])


def downgrade() -> None:
    op.drop_index("ix_chat_category", table_name="chat")
    op.drop_column("chat", "category")
