"""Crash DOE API — 1.19c-2 (`/crash/doe`).

Durability `/doe` ile aynı akış: çalışma oluştur (LHS örnekleri satır olarak),
arka planda ya da beklemeli koş, kaldığı yerden devam et, ilerlemeyi oku.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import SessionLocal, get_db
from app.doe.crash_runner import persist_study, run_study, study_progress
from app.doe.crash_sampling import CrashDoeError, CrashDoeSpec
from app.models.crash_doe import CrashDoeStudy

router = APIRouter(prefix="/crash/doe", tags=["crash-doe"])


def _run_in_background(study_id: int) -> None:
    db = SessionLocal()
    try:
        run_study(db, study_id)
    finally:
        db.close()


def _get_or_404(db: Session, study_id: int) -> CrashDoeStudy:
    study = db.get(CrashDoeStudy, study_id)
    if study is None:
        raise HTTPException(status_code=404, detail="Crash DOE çalışması yok.")
    return study


@router.post("/studies")
def create_study(
    spec: CrashDoeSpec,
    background_tasks: BackgroundTasks,
    wait: bool = False,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """LHS örnekler, satırları yazar; `wait=false` (varsayılan) arka planda koşar."""
    try:
        study = persist_study(db, spec)
    except CrashDoeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if wait:
        study = run_study(db, study.id)
    else:
        background_tasks.add_task(_run_in_background, study.id)
    return study_progress(study)


@router.get("/studies")
def list_studies(db: Session = Depends(get_db)) -> dict[str, Any]:
    rows = db.query(CrashDoeStudy).order_by(CrashDoeStudy.id.desc()).all()
    return {"studies": [study_progress(s, with_cases=False) for s in rows]}


@router.get("/studies/{study_id}")
def get_study(study_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    return study_progress(_get_or_404(db, study_id))


@router.post("/studies/{study_id}/run")
def resume_study(
    study_id: int, background_tasks: BackgroundTasks, wait: bool = False, db: Session = Depends(get_db)
) -> dict[str, Any]:
    """Bekleyen ve başarısız örnekleri yeniden koşar (bitmişler atlanır)."""
    study = _get_or_404(db, study_id)
    if study.status == "running":
        raise HTTPException(status_code=409, detail="Çalışma zaten koşuyor.")
    if wait:
        study = run_study(db, study_id)
    else:
        background_tasks.add_task(_run_in_background, study_id)
    return study_progress(study)
