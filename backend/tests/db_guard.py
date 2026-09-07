"""Geliştirme veritabanını (cae_dev) test temizliğinden koru.

pytest fixture'ları eskiden `TRUNCATE analysis_runs` + `rmtree(uploads)`
yapıyordu. Aynı DATABASE_URL canlı uygulamayla paylaşıldığında kullanıcı
geçmişi ve CAD dosyaları siliniyordu. Yıkıcı temizlik yalnızca
`cae_test` URL'sinde veya açık `CAE_ALLOW_DB_TRUNCATE=1` ile çalışır.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from sqlalchemy import text

from app.db.session import DATABASE_URL, SessionLocal


def allows_destructive_cleanup() -> bool:
    if os.environ.get("CAE_ALLOW_DB_TRUNCATE") == "1":
        return True
    return "cae_test" in (DATABASE_URL or "")


def safe_cleanup(upload_dir: Path | None, truncate_sql: str) -> None:
    if not allows_destructive_cleanup():
        return
    if upload_dir is not None and upload_dir.exists():
        shutil.rmtree(upload_dir)
    db = SessionLocal()
    try:
        db.execute(text(truncate_sql))
        db.commit()
    finally:
        db.close()
