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


def allows_upload_wipe() -> bool:
    """Dosya silme YALNIZ açık bayrakla.

    `uploads/` klasörü veritabanından bağımsız, süreç genelinde TEK yer:
    test veritabanına geçmek dosyaların da test dosyası olduğu anlamına
    gelmez. 2026-09-25'te `cae_test`'e geçiş bu fonksiyonu "izinli" saydı ve
    `rmtree(uploads/runs)` ~716 gerçek koşu klasörünü (538 eğitim dosyası,
    .frd, mesh'ler) geri dönüşsüz sildi. Tablo TRUNCATE'i test izolasyonu
    için yeter; artık dosya kalıntısı zararsızdır.
    """
    return os.environ.get("CAE_ALLOW_UPLOAD_WIPE") == "1"


def safe_cleanup(upload_dir: Path | None, truncate_sql: str) -> None:
    if not allows_destructive_cleanup():
        return
    if upload_dir is not None and upload_dir.exists() and allows_upload_wipe():
        shutil.rmtree(upload_dir)
    # RESTART IDENTITY yok: dosya silinmediği için kimlikler sıfırlanırsa
    # yeni geometri id=1 önceki testin `uploads/meshes/1_d3.msh` dosyasını
    # "kendi mesh'i" sanır. Sayaç artmaya devam eder (conftest 10M ofsetinden).
    truncate_sql = truncate_sql.replace("RESTART IDENTITY", "")
    db = SessionLocal()
    try:
        db.execute(text(truncate_sql))
        db.commit()
    finally:
        db.close()
