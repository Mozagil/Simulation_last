"""crash_runs tablosu (crash koşu geçmişi)

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-10-03

1.16a: OpenRadioss koşuları kendi tablosunda; analysis_runs değişmez.
Eğriler DB'ye girmez (job.json'da kalır). Yalnız tablo eklenir.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f3a4b5c6d7e8"
down_revision: Union[str, Sequence[str], None] = "e2f3a4b5c6d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "crash_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("geometry_id", sa.Integer(), sa.ForeignKey("geometries.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("dimension", sa.Integer(), nullable=True),
        sa.Column("t_end_ms", sa.Float(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("message", sa.String(), nullable=True),
        sa.Column("solver_ran", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("request", sa.JSON(), nullable=False),
        sa.Column("materials_snapshot", sa.JSON(), nullable=False),
        sa.Column("scalars", sa.JSON(), nullable=False),
        sa.Column("diagnostics", sa.JSON(), nullable=False),
        sa.Column("excluded", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("exclude_reason", sa.String(), nullable=True),
    )
    op.create_index("ix_crash_runs_job_id", "crash_runs", ["job_id"], unique=True)
    op.create_index("ix_crash_runs_geometry_id", "crash_runs", ["geometry_id"])
    op.create_index("ix_crash_runs_excluded", "crash_runs", ["excluded"])


def downgrade() -> None:
    op.drop_index("ix_crash_runs_excluded", table_name="crash_runs")
    op.drop_index("ix_crash_runs_geometry_id", table_name="crash_runs")
    op.drop_index("ix_crash_runs_job_id", table_name="crash_runs")
    op.drop_table("crash_runs")
