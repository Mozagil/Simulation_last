"""analysis_runs tablosu (kalicı analiz gecmisi)

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-09-02 14:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "analysis_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "geometry_id",
            sa.Integer(),
            sa.ForeignKey("geometries.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("dimension", sa.Integer(), nullable=False),
        sa.Column("element_size", sa.Float(), nullable=True),
        sa.Column("element_scheme", sa.String(), nullable=True),
        sa.Column("shell_thickness", sa.Float(), nullable=True),
        sa.Column("bcs", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("materials_snapshot", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("message", sa.String(), nullable=True),
        sa.Column("scalars", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("inp_path", sa.String(), nullable=True),
        sa.Column("frd_path", sa.String(), nullable=True),
        sa.Column("results_preview_path", sa.String(), nullable=True),
        sa.Column("mesh_preview_path", sa.String(), nullable=True),
    )
    op.create_index(
        "ix_analysis_runs_geometry_id", "analysis_runs", ["geometry_id"]
    )
    op.create_index(
        "ix_analysis_runs_created_at", "analysis_runs", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_analysis_runs_created_at", table_name="analysis_runs")
    op.drop_index("ix_analysis_runs_geometry_id", table_name="analysis_runs")
    op.drop_table("analysis_runs")
