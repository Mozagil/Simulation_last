"""crash_runs: geometry_id nullable + import_id (1.21e-2b)

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-10-15

Kullanıcı kararı (2026-10-12): içe aktarılan LS-DYNA modeli (.k / .dyn) koşulabilir. Böyle bir
koşunun geometrisi yok — ağ `uploads/crash_import/{import_id}/import.json`'dan gelir. Kayıt ya
geometriye ya içe aktarmaya bağlı (en az biri). Mevcut satırlar değişmez.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d0e1f2a3b4c5"
down_revision: Union[str, Sequence[str], None] = "c9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("crash_runs", "geometry_id", existing_type=sa.Integer(), nullable=True)
    op.add_column("crash_runs", sa.Column("import_id", sa.String(length=32), nullable=True))
    op.create_index("ix_crash_runs_import_id", "crash_runs", ["import_id"])
    op.create_check_constraint(
        "ck_crash_runs_geometry_or_import", "crash_runs", "geometry_id IS NOT NULL OR import_id IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_constraint("ck_crash_runs_geometry_or_import", "crash_runs", type_="check")
    op.drop_index("ix_crash_runs_import_id", table_name="crash_runs")
    op.drop_column("crash_runs", "import_id")
    # İçe aktarma koşuları (geometrisiz) silinmeden NOT NULL'a dönülemez.
    op.execute("DELETE FROM crash_runs WHERE geometry_id IS NULL")
    op.alter_column("crash_runs", "geometry_id", existing_type=sa.Integer(), nullable=False)
