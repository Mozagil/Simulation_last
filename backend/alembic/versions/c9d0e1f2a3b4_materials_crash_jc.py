"""materials.crash_jc (Johnson–Cook seti, 1.24f)

Revision ID: c9d0e1f2a3b4
Revises: 0c1d2e3f4a5b
Create Date: 2026-10-15

Kullanıcı kararı A (2026-10-15): malzeme başına tek Johnson–Cook seti, JSON kolon. Seed yalnız
birincil kaynakta doğrulanan set (docs/CRASH_MATERIALS.md): kütüphanede yalnız 7075-T6 — Brar,
Joshi, Harris 2009 (yazarların özet metni). ε̇₀ ve T_m özette yok → null. Diğer malzemeler NULL.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c9d0e1f2a3b4"
down_revision: Union[str, Sequence[str], None] = "0c1d2e3f4a5b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JC_7075_T6 = {
    "a_mpa": 546.0,
    "b_mpa": 674.0,
    "n": 0.72,
    "c": 0.059,
    "m": 1.56,
    "eps_dot0_per_s": None,
    "t_melt_k": None,
    "t_ref_k": None,
    "d": None,
    "source": "Brar, Joshi, Harris 2009 — AIP Conf. Proc. 1195, 945 (APS SCCM 2009 özeti); docs/CRASH_MATERIALS.md",
}


def upgrade() -> None:
    op.add_column("materials", sa.Column("crash_jc", sa.JSON(), nullable=True))
    materials = sa.table("materials", sa.column("name", sa.String), sa.column("crash_jc", sa.JSON))
    op.execute(materials.update().where(materials.c.name == "7075-T6").values(crash_jc=JC_7075_T6))


def downgrade() -> None:
    op.drop_column("materials", "crash_jc")
