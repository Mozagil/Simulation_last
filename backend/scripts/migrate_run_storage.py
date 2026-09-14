"""Mevcut run klasörlerini 0.5.2 depolama biçimine taşır.

- Ham `.frd` varsa gzip'ler (orijinali siler)
- `analysis_runs.frd_path` yeni `.frd.gz` yoluna çekilir
- Çözülmüş run'ların `.inp` dosyası silinir (`inp_path` NULL)

Eğitim `.npz` üretmez: o çözüm anında nset eşlemesi ister; eksik örnekler
yeniden çözülerek doldurulur.

Kullanım (backend kökünden):
    .\\.venv\\Scripts\\python.exe scripts/migrate_run_storage.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.dataset.training_data import gzip_frd  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.run import AnalysisRun  # noqa: E402


def main() -> None:
    db = SessionLocal()
    n_gz = n_inp = 0
    try:
        runs = db.query(AnalysisRun).all()
        for run in runs:
            if run.frd_path:
                frd = Path(run.frd_path)
                if frd.suffix == ".frd" and frd.is_file():
                    gz = gzip_frd(frd)
                    if gz is not None:
                        run.frd_path = str(gz).replace("\\", "/")
                        n_gz += 1
            if run.status == "solved" and run.inp_path:
                inp = Path(run.inp_path)
                if inp.is_file():
                    inp.unlink()
                    n_inp += 1
                run.inp_path = None
        db.commit()
    finally:
        db.close()
    print(f"gzip: {n_gz}  inp silindi: {n_inp}")


if __name__ == "__main__":
    main()
