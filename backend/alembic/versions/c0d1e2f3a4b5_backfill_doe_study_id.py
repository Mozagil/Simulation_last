"""analysis_runs.doe_study_id: eski satırları DoeCase'ten doldur

`b9c0d1e2f3a4` sütunu ekledi ama mevcut satırları boş bıraktı; bu yüzden
geçmişteki DOE/kalite setleri run listesinde "DOE dışı" görünüyordu.
Bağ zaten veride: `doe_cases.run_id`. Bu revizyon o bağı run tarafına yazar.

Yalnız BOŞ olanı doldurur (dolu değer ezilmez), bir run birden fazla
çalışmaya bağlıysa dokunmaz. Geri alma yok: hangi satırın önceden boş
olduğu bilinmediği için downgrade veriyi silmez, no-op'tur.

Revision ID: c0d1e2f3a4b5
Revises: b9c0d1e2f3a4
"""

from __future__ import annotations

from alembic import op

from app.doe.backfill import backfill_doe_study_ids

revision = "c0d1e2f3a4b5"
down_revision = "b9c0d1e2f3a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    report = backfill_doe_study_ids(op.get_bind())
    print(
        f"[backfill] doe_study_id dolduruldu: {report['filled']} run, "
        f"calisma dagilimi: {report['per_study']}"
    )
    if report["ambiguous_run_ids"]:
        print(f"[backfill] belirsiz, dokunulmadi: {report['ambiguous_run_ids']}")
    if report["conflicts"]:
        print(f"[backfill] celiskili, dokunulmadi: {report['conflicts']}")


def downgrade() -> None:
    """Veri migration'ı — geri alınmaz (hangi satır boştu bilinmiyor)."""
