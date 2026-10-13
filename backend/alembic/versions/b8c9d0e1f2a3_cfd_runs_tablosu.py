"""cfd_runs tablosu (CFD koşu geçmişi)

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-10-08

Faz 2.4 (kullanıcı onayı 2026-10-08): OpenFOAM koşuları kendi tablosunda;
analysis_runs ve crash_runs değişmez. Eğriler DB'ye girmez (job.json'da
kalır). Yalnız tablo eklenir.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, Sequence[str], None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cfd_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("geometry_id", sa.Integer(), sa.ForeignKey("geometries.id"), nullable=True),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("application", sa.String(), nullable=True),
        sa.Column("turbulence", sa.String(), nullable=True),
        sa.Column("mesh_kind", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("message", sa.String(), nullable=True),
        sa.Column("solver_ran", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("request", sa.JSON(), nullable=False),
        sa.Column("scalars", sa.JSON(), nullable=False),
        sa.Column("reference", sa.JSON(), nullable=True),
        sa.Column("diagnostics", sa.JSON(), nullable=False),
        sa.Column("excluded", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("exclude_reason", sa.String(), nullable=True),
    )
    op.create_index("ix_cfd_runs_job_id", "cfd_runs", ["job_id"], unique=True)
    op.create_index("ix_cfd_runs_geometry_id", "cfd_runs", ["geometry_id"])
    op.create_index("ix_cfd_runs_excluded", "cfd_runs", ["excluded"])


def downgrade() -> None:
    op.drop_index("ix_cfd_runs_excluded", table_name="cfd_runs")
    op.drop_index("ix_cfd_runs_geometry_id", table_name="cfd_runs")
    op.drop_index("ix_cfd_runs_job_id", table_name="cfd_runs")
    op.drop_table("cfd_runs")
