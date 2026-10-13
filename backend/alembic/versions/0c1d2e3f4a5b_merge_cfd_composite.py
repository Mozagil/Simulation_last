"""cfd_runs ve kompozit zincirlerini birleştir (dallar main'de toplandı)

Revision ID: 0c1d2e3f4a5b
Revises: b8c9d0e1f2a3, f7a8b9c0d1e2
Create Date: 2026-10-13

Şema değişikliği yok; yalnız iki alembic başını tek başa indirir.
"""

from typing import Sequence, Union

revision: str = "0c1d2e3f4a5b"
down_revision: Union[str, Sequence[str], None] = ("b8c9d0e1f2a3", "f7a8b9c0d1e2")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
