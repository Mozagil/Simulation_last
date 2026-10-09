"""CFD koşu geçmişi ve karşılaştırma — Faz 2.4 (``crash_runs`` deseni).

``/cfd/solve`` her işte ``cfd_runs`` satırı açar, iş bitince günceller
(``record_from_meta``). Eğriler job.json'dan okunur; DB'de yalnız skalerler.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.cfd_run import CfdRun
from app.models.geometry import Geometry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cfd/runs", tags=["cfd"])

CFD_DIR = Path("uploads") / "cfd"

#: job.json'dan isteğin girdi anlık görüntüsüne giren alanlar.
REQUEST_KEYS = ("case", "mesh", "forces", "rho_kg_m3", "end_iterations", "turbulence", "application", "rocket")


def record_from_meta(db: Session, meta: dict[str, Any]) -> CfdRun:
    """job.json meta'sından kayıt açar ya da günceller (job_id tekil)."""
    job_id = str(meta["job_id"])
    gid = meta.get("geometry_id")
    if gid is not None and db.get(Geometry, int(gid)) is None:
        gid = None
    run = db.query(CfdRun).filter(CfdRun.job_id == job_id).one_or_none()
    if run is None:
        run = CfdRun(job_id=job_id, geometry_id=gid)
        db.add(run)
    run.name = meta.get("name")
    run.application = meta.get("application")
    run.turbulence = meta.get("turbulence")
    run.mesh_kind = (meta.get("mesh") or {}).get("kind")
    run.status = str(meta.get("status") or "case_only")
    run.message = meta.get("message")
    run.solver_ran = bool(meta.get("solver_ran"))
    run.request = {k: meta[k] for k in REQUEST_KEYS if k in meta}
    run.scalars = dict(meta.get("scalars") or {})
    run.reference = meta.get("reference") or (
        {"kind": "rocket_r3", "aero": meta["rocket_aero"]} if meta.get("rocket_aero") else None
    )
    run.diagnostics = dict(meta.get("diagnostics") or {})
    db.commit()
    db.refresh(run)
    return run


def _summary(r: CfdRun) -> dict[str, Any]:
    return {
        "id": r.id,
        "job_id": r.job_id,
        "geometry_id": r.geometry_id,
        "name": r.name,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "application": r.application,
        "turbulence": r.turbulence,
        "mesh_kind": r.mesh_kind,
        "status": r.status,
        "message": r.message,
        "solver_ran": r.solver_ran,
        "scalars": r.scalars,
        "reference": r.reference,
        "excluded": r.excluded,
        "exclude_reason": r.exclude_reason,
    }


def _curves(job_id: str) -> dict[str, Any]:
    path = CFD_DIR / job_id / "job.json"
    if not path.is_file():
        return {}
    try:
        return dict(json.loads(path.read_text(encoding="utf-8")).get("curves") or {})
    except ValueError:
        return {}


def _get_or_404(db: Session, run_id: int) -> CfdRun:
    run = db.get(CfdRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="CFD koşusu bulunamadı.")
    return run


@router.get("")
def list_cfd_runs(
    geometry_id: int | None = None,
    include_excluded: bool = True,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """CFD koşuları, yeniden eskiye."""
    q = db.query(CfdRun)
    if geometry_id is not None:
        q = q.filter(CfdRun.geometry_id == geometry_id)
    if not include_excluded:
        q = q.filter(CfdRun.excluded.is_(False))
    rows = q.order_by(CfdRun.created_at.desc(), CfdRun.id.desc()).all()
    return {"count": len(rows), "runs": [_summary(r) for r in rows]}


@router.get("/compare")
def compare_cfd_runs(
    ids: str = Query(..., description="Virgülle koşu kimlikleri, örn. 3,5,9"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Seçili koşuların skalerleri + residual ve kuvvet katsayısı geçmişleri yan yana."""
    try:
        run_ids = [int(x) for x in ids.split(",") if x.strip()]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="ids tamsayı listesi olmalı.") from exc
    if not run_ids:
        raise HTTPException(status_code=422, detail="En az bir koşu kimliği gerekli.")
    return {"runs": [{**_summary(r), "curves": _curves(r.job_id)} for r in (_get_or_404(db, i) for i in run_ids)]}


@router.get("/{run_id}")
def get_cfd_run(run_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    run = _get_or_404(db, run_id)
    return {**_summary(run), "request": run.request, "diagnostics": run.diagnostics, "curves": _curves(run.job_id)}


class CfdRunPatch(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    excluded: bool | None = None
    exclude_reason: str | None = Field(default=None, max_length=500)


@router.patch("/{run_id}")
def patch_cfd_run(run_id: int, body: CfdRunPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
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
