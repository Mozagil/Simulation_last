"""uploads/crash/*/job.json → crash_runs (1.16a, tek seferlik içe aktarma).

job_id ile tekrarsız: yeniden çalıştırmak kayıtları günceller, çoğaltmaz.
Geometrisi silinmiş işler atlanır (FK). created_at = job.json değişme zamanı.

Kullanım (backend kökünden):
    .\\.venv\\Scripts\\python.exe scripts/import_crash_jobs.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.api.crash_runs import import_job_dirs  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402


def main() -> None:
    db = SessionLocal()
    try:
        stats = import_job_dirs(db, ROOT / "uploads" / "crash")
    finally:
        db.close()
    print(" ".join(f"{k}={v}" for k, v in stats.items()))


if __name__ == "__main__":
    main()
