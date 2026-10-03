r"""Eski crash işlerini ham çıktılarından güncel post-process ile yeniden işler (1.17g).

Yeni skalerler (1.14f silme / starter mesajları, 1.15a Δt / eklenen kütle,
1.17b global enerji + hourglass, …) eski işlerde yok. Bu betik her çözülmüş
kaydın klasörünü `parse_openradioss_dir` ile yeniden okur:
- job.json `scalars` / `curves` / `diagnostics` güncellenir; İLK seferde eski
  skalerler `scalars_prev` olarak saklanır (geri alınabilir), `reprocessed_at`
  yazılır;
- crash_runs kaydı `record_from_meta` ile güncellenir.
Varsayılan KURU koşu (yalnız sayar); yazmak için `--apply`.

Kullanım (backend kökünden):
    .\.venv\Scripts\python.exe scripts/reprocess_crash_jobs.py [--apply]
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.api.crash_runs import record_from_meta  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.crash_run import CrashRun  # noqa: E402
from app.postprocess.openradioss_th import parse_openradioss_dir  # noqa: E402


def reprocess(db, root: Path, apply: bool) -> dict[str, int]:
    stats = {"seen": 0, "changed": 0, "unchanged": 0, "no_output": 0, "new_keys": 0}
    for run in db.query(CrashRun).filter(CrashRun.solver_ran.is_(True)).order_by(CrashRun.id):
        work = root / run.job_id
        meta_p = work / "job.json"
        stats["seen"] += 1
        if not meta_p.is_file() or not any(work.glob("*T01*.csv")):
            stats["no_output"] += 1
            continue
        meta = json.loads(meta_p.read_text(encoding="utf-8"))
        rs = parse_openradioss_dir(work)
        old = meta.get("scalars") or {}
        new = rs.scalars
        changed = set(new) != set(old) or any(
            abs(float(new[k]) - float(old[k])) > 1e-9 * max(1.0, abs(float(old[k]))) for k in new if k in old
        )
        if not changed:
            stats["unchanged"] += 1
            continue
        stats["changed"] += 1
        stats["new_keys"] += len(set(new) - set(old))
        if apply:
            meta.setdefault("scalars_prev", old)
            meta["scalars"] = new
            meta["curves"] = rs.curves
            meta["diagnostics"] = rs.diagnostics
            meta["reprocessed_at"] = datetime.now(timezone.utc).isoformat()
            meta_p.write_text(json.dumps(meta, indent=2), encoding="utf-8")
            record_from_meta(db, meta)
    return stats


def main() -> None:
    apply = "--apply" in sys.argv
    db = SessionLocal()
    try:
        stats = reprocess(db, ROOT / "uploads" / "crash", apply)
    finally:
        db.close()
    print(("yazıldı" if apply else "kuru koşu") + ": " + " ".join(f"{k}={v}" for k, v in stats.items()))


if __name__ == "__main__":
    main()
