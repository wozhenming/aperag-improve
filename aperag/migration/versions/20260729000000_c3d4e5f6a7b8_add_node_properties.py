"""add node properties JSONB

Revision ID: c3d4e5f6a7b8
Revises: 72de1ba2de3f
Create Date: 2026-07-29 00:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = '72de1ba2de3f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("lightrag_graph_nodes", sa.Column("properties", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("lightrag_graph_nodes", "properties")
