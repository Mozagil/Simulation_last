"""Eğitilmiş modelleri ve korpus manifestlerini tek zip'e yedekler.

NEDEN: `uploads/models/` tek kopya. 2026-09-25'te bir test temizliği bu
klasörü sildi; skaler modeller DB'den dakikalar içinde yeniden eğitildi ama
manifest run listeleri birebir geri gelmedi (kiris-v2 200 -> 192).

Kullanım (backend/ içinden):
    python scripts/backup_models.py            -> backups/models-YYYYMMDD-HHMM.zip
    python scripts/backup_models.py --restore backups/models-….zip
"""

from __future__ import annotations

import argparse
import datetime as dt
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "uploads" / "models"
BACKUPS = ROOT / "backups"


def backup() -> Path:
    if not MODELS.is_dir():
        sys.exit(f"Model klasörü yok: {MODELS}")
    BACKUPS.mkdir(exist_ok=True)
    dest = BACKUPS / f"models-{dt.datetime.now():%Y%m%d-%H%M}.zip"
    n = 0
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(MODELS.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(MODELS))
                n += 1
    print(f"{n} dosya -> {dest} ({dest.stat().st_size / 1e6:.1f} MB)")
    return dest


def restore(src: Path) -> None:
    if not src.is_file():
        sys.exit(f"Yedek yok: {src}")
    if MODELS.exists():
        keep = MODELS.with_name(f"models.before-restore-{dt.datetime.now():%Y%m%d-%H%M}")
        shutil.move(str(MODELS), str(keep))
        print(f"mevcut klasör kenara alındı: {keep}")
    MODELS.mkdir(parents=True)
    with zipfile.ZipFile(src) as z:
        z.extractall(MODELS)
        print(f"{len(z.namelist())} dosya geri yüklendi -> {MODELS}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--restore", type=Path)
    a = ap.parse_args()
    restore(a.restore) if a.restore else backup()
