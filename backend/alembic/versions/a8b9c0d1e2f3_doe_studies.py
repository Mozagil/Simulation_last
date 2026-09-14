"""doe_studies + doe_cases (0.5.4)

Revision ID: a8b9c0d1e2f3
Revises: f6a7b8c9d0e1
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a8b9c0d1e2f3"
down_revision: Union[str, Sequence[str], None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "doe_studies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("template_id", sa.String(length=80), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("spec", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("message", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_table(
        "doe_cases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "study_id",
            sa.Integer(),
            sa.ForeignKey("doe_studies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("index", sa.Integer(), nullable=False),
        sa.Column("geometry_params", sa.JSON(), nullable=False),
        sa.Column("element_size", sa.Float(), nullable=False),
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.Column("scenario_name", sa.String(), nullable=False),
        sa.Column("bound_bcs", sa.JSON(), nullable=True),
        sa.Column("geometry_id", sa.Integer(), nullable=True),
        sa.Column("run_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("message", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("doe_cases")
    op.drop_table("doe_studies")
