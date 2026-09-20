"""Eski run'larda boş kalan `doe_study_id` alanını `DoeCase`'ten doldurur.

NEDEN: `doe_study_id` sütunu `b9c0d1e2f3a4` ile eklendi ama mevcut satırlar
boş bırakıldı. Bağ zaten veride var — `doe_cases.run_id` hangi koşunun hangi
çalışmadan geldiğini biliyor — yalnız run tarafından geriye bakılamıyordu.
Bu yüzden `GET /geometry/runs?doe_study_id=` eski setleri (kalite-200,
kiriş-eğitim-v2, doğrulama setleri) hiç göremiyordu.

Kurallar:
  * Yalnız BOŞ olanı doldurur; dolu bir değeri asla ezmez.
  * Bir run iki farklı çalışmada görünüyorsa (belirsiz) dokunmaz, raporlar.
  * Tekrar çalıştırılabilir (idempotent): ikinci koşuda `filled=0` döner.

Migration `c0d1e2f3a4b5` bunu çağırır; elle de çalıştırılabilir:
    python -m app.doe.backfill          # rapor + yaz
    python -m app.doe.backfill --dry-run
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa

# Migration içinden de çağrıldığı için ORM modeli değil, düz tablo tanımı
# kullanılır: şema ileride değişse bile bu betik o günkü sütunlara bakar.
_RUNS = sa.table(
    "analysis_runs",
    sa.column("id", sa.Integer),
    sa.column("doe_study_id", sa.Integer),
)
_CASES = sa.table(
    "doe_cases",
    sa.column("run_id", sa.Integer),
    sa.column("study_id", sa.Integer),
)


def _ambiguous_run_ids(bind: sa.engine.Connection) -> list[int]:
    """Birden fazla çalışmaya bağlanmış run'lar — hangisi olduğu belli değil."""
    q = (
        sa.select(_CASES.c.run_id)
        .where(_CASES.c.run_id.isnot(None))
        .group_by(_CASES.c.run_id)
        .having(sa.func.count(sa.distinct(_CASES.c.study_id)) > 1)
    )
    return [int(r[0]) for r in bind.execute(q)]


def conflicting_rows(bind: sa.engine.Connection) -> list[dict[str, int]]:
    """Dolu `doe_study_id` ile `DoeCase` çelişiyorsa: elle bakılmalı."""
    q = (
        sa.select(_RUNS.c.id, _RUNS.c.doe_study_id, _CASES.c.study_id)
        .select_from(_RUNS.join(_CASES, _CASES.c.run_id == _RUNS.c.id))
        .where(
            _RUNS.c.doe_study_id.isnot(None),
            _RUNS.c.doe_study_id != _CASES.c.study_id,
        )
    )
    return [
        {"run_id": int(a), "run_study_id": int(b), "case_study_id": int(c)}
        for a, b, c in bind.execute(q)
    ]


def pending_counts(bind: sa.engine.Connection) -> dict[int, int]:
    """Doldurulabilir run sayısı, çalışma kimliğine göre (yazmadan bakar)."""
    q = (
        sa.select(_CASES.c.study_id, sa.func.count(_RUNS.c.id))
        .select_from(_CASES.join(_RUNS, _CASES.c.run_id == _RUNS.c.id))
        .where(_RUNS.c.doe_study_id.is_(None))
        .group_by(_CASES.c.study_id)
    )
    ambiguous = set(_ambiguous_run_ids(bind))
    if ambiguous:
        q = q.where(_RUNS.c.id.notin_(ambiguous))
    return {int(s): int(n) for s, n in bind.execute(q)}


def backfill_doe_study_ids(
    bind: sa.engine.Connection, *, dry_run: bool = False
) -> dict[str, Any]:
    """Boş `doe_study_id` alanlarını doldurur. Rapor döner."""
    ambiguous = _ambiguous_run_ids(bind)
    conflicts = conflicting_rows(bind)
    per_study = pending_counts(bind)
    fillable = sum(per_study.values())

    if not dry_run and fillable:
        matched = (
            sa.select(sa.func.min(_CASES.c.study_id))
            .where(_CASES.c.run_id == _RUNS.c.id)
            .scalar_subquery()
        )
        stmt = (
            sa.update(_RUNS)
            .where(_RUNS.c.doe_study_id.is_(None), matched.isnot(None))
            .values(doe_study_id=matched)
        )
        if ambiguous:
            stmt = stmt.where(_RUNS.c.id.notin_(ambiguous))
        bind.execute(stmt)

    return {
        "filled": 0 if dry_run else fillable,
        "fillable": fillable,
        "per_study": per_study,
        "ambiguous_run_ids": ambiguous,
        "conflicts": conflicts,
        "dry_run": dry_run,
    }


def _main() -> None:  # pragma: no cover - elle çalıştırma yolu
    import sys

    from app.db.session import SessionLocal

    dry = "--dry-run" in sys.argv
    db = SessionLocal()
    try:
        report = backfill_doe_study_ids(db.connection(), dry_run=dry)
        if not dry:
            db.commit()
    finally:
        db.close()

    for study_id, n in sorted(report["per_study"].items()):
        print(f"  calisma {study_id}: {n} run")
    print(f"{'doldurulabilir' if dry else 'dolduruldu'}: {report['fillable']}")
    if report["ambiguous_run_ids"]:
        print(f"belirsiz (dokunulmadi): {report['ambiguous_run_ids']}")
    if report["conflicts"]:
        print(f"celiskili (dokunulmadi): {report['conflicts']}")


if __name__ == "__main__":  # pragma: no cover
    _main()
