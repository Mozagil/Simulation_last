"""crash_doe_studies + crash_doe_cases tabloları

Revision ID: a7b8c9d0e1f2
Revises: f3a4b5c6d7e8
Create Date: 2026-10-07

1.19c-2: crash DOE çalışması kendi tablolarında; doe_studies / crash_runs
değişmez. Yalnız tablo eklenir.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, Sequence[str], None] = "f3a4b5c6d7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "crash_doe_studies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("template_id", sa.String(length=80), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("spec", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("message", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "crash_doe_cases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "study_id", sa.Integer(),
            sa.ForeignKey("crash_doe_studies.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("index", sa.Integer(), nullable=False),
        sa.Column("values", sa.JSON(), nullable=False),
        sa.Column("request", sa.JSON(), nullable=False),
        sa.Column("geometry_id", sa.Integer(), nullable=True),
        sa.Column(
            "run_id", sa.Integer(), sa.ForeignKey("crash_runs.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("message", sa.String(), nullable=True),
    )
    op.create_index("ix_crash_doe_cases_study_id", "crash_doe_cases", ["study_id"])
    op.create_index("ix_crash_doe_cases_run_id", "crash_doe_cases", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_crash_doe_cases_run_id", table_name="crash_doe_cases")
    op.drop_index("ix_crash_doe_cases_study_id", table_name="crash_doe_cases")
    op.drop_table("crash_doe_cases")
    op.drop_table("crash_doe_studies")
