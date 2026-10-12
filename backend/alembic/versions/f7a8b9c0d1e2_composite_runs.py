"""composite_runs tablosu (Faz 3.9)

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-10-12

analysis_runs / /solve değişmez.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f7a8b9c0d1e2"
down_revision: Union[str, Sequence[str], None] = "e6f7a8b9c0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "composite_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column(
            "geometry_id",
            sa.Integer(),
            sa.ForeignKey("geometries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("part_id", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("dimension", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("message", sa.String(), nullable=True),
        sa.Column("solver_ran", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("inp_path", sa.String(), nullable=True),
        sa.Column("request", sa.JSON(), nullable=False),
        sa.Column("layup_snapshot", sa.JSON(), nullable=False),
        sa.Column("orientation_snapshot", sa.JSON(), nullable=True),
        sa.Column("bcs", sa.JSON(), nullable=False),
        sa.Column("scalars", sa.JSON(), nullable=False),
    )
    op.create_index("ix_composite_runs_job_id", "composite_runs", ["job_id"], unique=True)
    op.create_index("ix_composite_runs_geometry_id", "composite_runs", ["geometry_id"])


def downgrade() -> None:
    op.drop_index("ix_composite_runs_geometry_id", table_name="composite_runs")
    op.drop_index("ix_composite_runs_job_id", table_name="composite_runs")
    op.drop_table("composite_runs")
