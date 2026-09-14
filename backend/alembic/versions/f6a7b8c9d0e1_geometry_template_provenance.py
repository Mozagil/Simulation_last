"""geometries tablosuna şablon kökeni (template_id + template_params)

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-09-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("geometries", sa.Column("template_id", sa.String(length=80), nullable=True))
    op.add_column("geometries", sa.Column("template_params", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("geometries", "template_params")
    op.drop_column("geometries", "template_id")
