"""Crash koşu geçmişi ve karşılaştırma — 1.16a.

`/crash/solve` her işte `crash_runs` satırı açar, iş bitince günceller
(`record_from_meta`). Eğriler job.json'dan okunur; DB'de yalnız skalerler.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.crash_run import CrashRun
from app.models.geometry import Geometry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/crash/runs", tags=["crash"])

CRASH_DIR = Path("uploads") / "crash"

#: job.json'dan isteğin girdi anlık görüntüsüne giren alanlar.
REQUEST_KEYS = (
    "barrier", "model", "scenario", "parts", "contacts", "use_rigid_wall",
    "engine", "th", "sections", "t_end_ms", "dimension", "law36_curve_source",
    "added_masses", "rigid_bodies", "boundary_conditions", "imposed_velocities", "initial_velocities", "filters", "gravity", "pressure_loads", "sph_projectiles", "blast_loads", "springs",
    "raw_cards",  # 1.22a — ham kartlar koşuyla saklanır (1.22f etiket)
)


def record_from_meta(
    db: Session, meta: dict[str, Any], created_at: datetime | None = None
) -> CrashRun | None:
    """job.json meta'sından kayıt açar ya da günceller (job_id tekil).

    Geometrisi ya da içe aktarması (1.21e-2b, `import_id`) olmayan iş kaydedilmez; None döner.
    """
    job_id = str(meta.get("job_id") or "")
    gid = meta.get("geometry_id")
    import_id = meta.get("import_id")
    if gid is not None and db.get(Geometry, int(gid)) is None:
        gid = None
    if not job_id or (gid is None and not import_id):
        return None
    run = db.query(CrashRun).filter(CrashRun.job_id == job_id).one_or_none()
    if run is None:
        run = CrashRun(job_id=job_id, geometry_id=int(gid) if gid is not None else None,
                       import_id=str(import_id) if import_id else None)
        if created_at is not None:
            run.created_at = created_at
        db.add(run)
    run.name = meta.get("name")
    run.dimension = meta.get("dimension")
    run.t_end_ms = meta.get("t_end_ms")
    run.status = str(meta.get("status") or "rad_only")
    run.message = meta.get("message")
    run.solver_ran = bool(meta.get("solver_ran"))
    run.request = {k: meta[k] for k in REQUEST_KEYS if k in meta}
    run.materials_snapshot = list(meta.get("materials") or [])
    run.scalars = dict(meta.get("scalars") or {})
    run.diagnostics = dict(meta.get("diagnostics") or {})
    db.commit()
    db.refresh(run)
    return run


def _summary(r: CrashRun) -> dict[str, Any]:
    return {
        "id": r.id,
        "job_id": r.job_id,
        "geometry_id": r.geometry_id,
        "import_id": r.import_id,
        "name": r.name,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "dimension": r.dimension,
        "t_end_ms": r.t_end_ms,
        "status": r.status,
        "message": r.message,
        "solver_ran": r.solver_ran,
        "scalars": r.scalars,
        "excluded": r.excluded,
        "exclude_reason": r.exclude_reason,
        # 1.22f: koşu ham kartla üretildi (geçmişte etiket; ML korpusu varsayılan dışarıda).
        "has_raw_cards": bool(str((r.request or {}).get("raw_cards") or "").strip()),
    }


def _curves(job_id: str) -> dict[str, list[float]]:
    path = CRASH_DIR / job_id / "job.json"
    if not path.is_file():
        return {}
    try:
        return dict(json.loads(path.read_text(encoding="utf-8")).get("curves") or {})
    except ValueError:
        return {}


def _get_or_404(db: Session, run_id: int) -> CrashRun:
    run = db.get(CrashRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Crash koşusu bulunamadı.")
    return run


@router.get("")
def list_crash_runs(
    geometry_id: int | None = None,
    include_excluded: bool = True,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Crash koşuları, yeniden eskiye."""
    q = db.query(CrashRun)
    if geometry_id is not None:
        q = q.filter(CrashRun.geometry_id == geometry_id)
    if not include_excluded:
        q = q.filter(CrashRun.excluded.is_(False))
    rows = q.order_by(CrashRun.created_at.desc(), CrashRun.id.desc()).all()
    return {"count": len(rows), "runs": [_summary(r) for r in rows]}


@router.get("/compare")
def compare_crash_runs(
    ids: str = Query(..., description="Virgülle koşu kimlikleri, örn. 3,5,9"),
    curves: str | None = Query(
        default=None,
        description="Virgülle eğri adları; boş = kayıtlı tüm eğriler (1.25c)",
    ),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Seçili koşuların skalerleri + eğrileri yan yana (her koşu kendi zaman ekseniyle)."""
    try:
        run_ids = [int(x) for x in ids.split(",") if x.strip()]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="ids tamsayı listesi olmalı.") from exc
    if not run_ids:
        raise HTTPException(status_code=422, detail="En az bir koşu kimliği gerekli.")
    wanted = [c.strip() for c in curves.split(",")] if curves else None
    out = []
    for rid in run_ids:
        run = _get_or_404(db, rid)
        all_curves = _curves(run.job_id)
        # 1.25c — varsayılan: kayıtlı tüm eğriler (enerji, temas, kesit, düğüm, TH)
        # karşılaştırmada görünsün; 1.17e2'deki yalnız-kuvvet süzgeci kaldırıldı.
        keys = wanted if wanted is not None else [k for k in all_curves if k != "time"]
        sel = {k: all_curves[k] for k in keys if k in all_curves}
        if sel and "time" in all_curves:
            sel["time"] = all_curves["time"]
        out.append({**_summary(run), "curves": sel})
    return {"runs": out}


def _cache_complete(path: Path) -> bool:
    """anim.json geçerli mi: '}' ile biter (yarım değil) ve NaN/Infinity içermez
    (eski sürüm ıraksamış koşuda bunları yazıyordu, tarayıcı okuyamıyordu)."""
    try:
        with path.open("rb") as fh:
            fh.seek(-1, 2)
            if fh.read(1) != b"}":
                return False
        text = path.read_text(encoding="utf-8", errors="replace")
        return "NaN" not in text and "Infinity" not in text
    except OSError:
        return False


@router.get("/{run_id}/animation")
def crash_run_animation(run_id: int, db: Session = Depends(get_db)) -> Any:
    """Deforme şekil (1.17d): yüzey + kare başına koordinat / skaler. İlk istekte
    anim_to_vtk ile üretilir, iş klasöründe `anim.json` olarak önbelleklenir."""
    from fastapi.responses import FileResponse

    from app.postprocess.openradioss_anim import build_animation, write_animation_cache
    from app.solvers.openradioss import convert_animation, resolve_openradioss

    run = _get_or_404(db, run_id)
    work = CRASH_DIR / run.job_id
    cache = work / "anim.json"
    if cache.is_file() and not _cache_complete(cache):
        cache.unlink(missing_ok=True)  # yarım yazılmış önbellek (eski sürüm) — yeniden üret
    if not cache.is_file():
        bins = resolve_openradioss()
        if bins is None:
            raise HTTPException(status_code=503, detail="OpenRadioss (anim_to_vtk) bulunamadı.")
        texts = convert_animation(bins, work)
        if not texts:
            raise HTTPException(status_code=404, detail="Bu koşuda animasyon dosyası yok.")
        data = build_animation(texts)
        if not data["frames"]:
            raise HTTPException(status_code=422, detail="Animasyon okunamadı.")
        write_animation_cache(work, data)
    return FileResponse(cache, media_type="application/json")


@router.get("/{run_id}")
def get_crash_run(run_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    run = _get_or_404(db, run_id)
    return {
        **_summary(run),
        "request": run.request,
        "materials_snapshot": run.materials_snapshot,
        "diagnostics": run.diagnostics,
        "curves": _curves(run.job_id),
    }


class CrashRunPatch(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    excluded: bool | None = None
    exclude_reason: str | None = Field(default=None, max_length=500)


@router.patch("/{run_id}")
def patch_crash_run(run_id: int, body: CrashRunPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Ad ve dışlama işareti; girdi / sonuç değiştirilemez."""
    run = _get_or_404(db, run_id)
    data = body.model_dump(exclude_unset=True)
    if "name" in data:
        run.name = data["name"]
    if "excluded" in data:
        run.excluded = bool(data["excluded"])
        if not run.excluded:
            run.exclude_reason = None
    if "exclude_reason" in data and run.excluded:
        run.exclude_reason = data["exclude_reason"]
    db.commit()
    db.refresh(run)
    return _summary(run)


def import_job_dirs(db: Session, root: Path = CRASH_DIR) -> dict[str, int]:
    """uploads/crash/*/job.json → crash_runs (tek seferlik; job_id ile tekrarsız).

    created_at = job.json değişme zamanı. Geometrisi silinmiş iş atlanır.
    """
    stats = {"imported": 0, "updated": 0, "skipped_no_geometry": 0, "unreadable": 0}
    for path in sorted(root.glob("*/job.json")):
        try:
            meta = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            stats["unreadable"] += 1
            continue
        existed = db.query(CrashRun.id).filter(CrashRun.job_id == str(meta.get("job_id"))).first()
        ts = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        if record_from_meta(db, meta, created_at=ts) is None:
            stats["skipped_no_geometry"] += 1
        elif existed:
            stats["updated"] += 1
        else:
            stats["imported"] += 1
    return stats
