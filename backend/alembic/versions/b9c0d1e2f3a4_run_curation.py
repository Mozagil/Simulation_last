"""analysis_runs: kürasyon alanları (excluded, exclude_reason, doe_study_id)

Neden: 900'e yakın run birikti ve ikinci şablon (plate_with_hole) girince
liste tamamen karışacak. Üç ayrım gerekiyor:

1. `doe_study_id` — hangi run hangi DOE/kalite setinden geldi. Şu an bu
   bilgi yalnız DoeCase tarafında; run'dan geriye bakılamıyor, bu yüzden
   geçmişte "bu 200'lük setin run'ları" diye süzülemiyor.
2. `excluded` — deneme amaçlı, mükerrer ya da kalitesiz koşuları ELLE
   işaretleyip hem listeden hem EĞİTİM SETİNDEN çıkarmak. Silmek yerine
   işaretlemek: run diskte kalır, kararı geri alabilirsin.
3. `exclude_reason` — neden dışlandığı. Altı ay sonra "bu neden kapalı"
   sorusunun cevabı kodda değil veride olmalı.

Revision ID: b9c0d1e2f3a4
Revises: a8b9c0d1e2f3
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b9c0d1e2f3a4"
down_revision = "a8b9c0d1e2f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analysis_runs",
        sa.Column("doe_study_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "analysis_runs",
        sa.Column(
            "excluded",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "analysis_runs",
        sa.Column("exclude_reason", sa.String(), nullable=True),
    )
    # Geçmiş süzmesi bu iki sütun üzerinden yapılacak.
    op.create_index(
        "ix_analysis_runs_doe_study_id", "analysis_runs", ["doe_study_id"]
    )
    op.create_index("ix_analysis_runs_excluded", "analysis_runs", ["excluded"])


def downgrade() -> None:
    op.drop_index("ix_analysis_runs_excluded", table_name="analysis_runs")
    op.drop_index("ix_analysis_runs_doe_study_id", table_name="analysis_runs")
    op.drop_column("analysis_runs", "exclude_reason")
    op.drop_column("analysis_runs", "excluded")
    op.drop_column("analysis_runs", "doe_study_id")
