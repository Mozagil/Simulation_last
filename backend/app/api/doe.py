"""DOE / batch runner API (0.5.4)."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from app.db.session import SessionLocal, get_db
from app.doe.convergence import ConvergenceError, ConvergenceSpec, run_convergence
from app.doe.quality import scan_study
from app.doe.results import study_results
from app.doe.quality_set import QUALITY_SET_N, QualitySetError, quality_spec
from app.doe.runner import persist_study, run_study, study_progress
from app.doe.sampling import DoeSpec
from app.models.doe import DoeStudy
from app.models.material import Material
from app.templates import UnknownTemplateError

router = APIRouter(prefix="/doe", tags=["doe"])


def _run_in_background(study_id: int) -> None:
    db = SessionLocal()
    try:
        run_study(db, study_id)
    finally:
        db.close()


def _load_study(db: Session, study_id: int) -> DoeStudy | None:
    return (
        db.query(DoeStudy)
        .options(joinedload(DoeStudy.cases))
        .filter(DoeStudy.id == study_id)
        .one_or_none()
    )


@router.post("/studies")
def create_study(
    spec: DoeSpec,
    background_tasks: BackgroundTasks,
    wait: bool = True,
    db: Session = Depends(get_db),
) -> dict:
    """LHS örnekler, satırları yazar, isteğe bağlı hemen çalıştırır."""
    study = persist_study(db, spec)
    if wait:
        study = run_study(db, study.id)
    else:
        background_tasks.add_task(_run_in_background, study.id)
    loaded = _load_study(db, study.id)
    return study_progress(loaded or study)


@router.get("/studies")
def list_studies(db: Session = Depends(get_db)) -> dict:
    rows = (
        db.query(DoeStudy)
        .options(joinedload(DoeStudy.cases))
        .order_by(DoeStudy.id.desc())
        .all()
    )
    return {"count": len(rows), "studies": [study_progress(s) for s in rows]}


@router.get("/studies/{study_id}")
def get_study(study_id: int, db: Session = Depends(get_db)) -> dict:
    study = _load_study(db, study_id)
    if study is None:
        raise HTTPException(status_code=404, detail="DOE çalışması yok.")
    return study_progress(study)


@router.post("/studies/{study_id}/run")
def resume_study(study_id: int, db: Session = Depends(get_db)) -> dict:
    """Kalan/başarısız örnekleri yeniden dener."""
    from app.models.doe import DoeCase

    study = db.get(DoeStudy, study_id)
    if study is None:
        raise HTTPException(status_code=404, detail="DOE çalışması yok.")
    db.query(DoeCase).filter(
        DoeCase.study_id == study_id, DoeCase.status == "failed"
    ).update({"status": "pending", "message": None})
    db.commit()
    study = run_study(db, study_id)
    loaded = _load_study(db, study.id)
    return study_progress(loaded or study)


class QualitySetRequest(BaseModel):
    #: Hangi şablonun referans seti; varsayılan Faz 0 doğrulama vakası.
    template_id: str = "cantilever_beam"
    material_ids: list[int] | None = None
    run_solver: bool = False
    wait: bool = False


@router.post("/quality-set")
def start_quality_set(
    body: QualitySetRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict:
    """Sabit tohumlu 200'lük referans set (0.5.5) — şablon seçilebilir.

    Aralıklar şablona özgü ve SABİT; kullanıcının form aralıkları kullanılmaz.
    Kalite seti bir referanstır: aynı tohum aynı 200 örneği üretmeli ki farklı
    zamanlardaki koşular karşılaştırılabilsin.
    """
    ids = list(body.material_ids or [])
    if not ids:
        first = db.query(Material).order_by(Material.id).first()
        if first is None:
            raise HTTPException(status_code=422, detail="Malzeme kütüphanesi boş.")
        ids = [first.id]
    try:
        spec = quality_spec(body.template_id, ids, run_solver=body.run_solver)
    except UnknownTemplateError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except QualitySetError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    study = persist_study(db, spec)
    if body.wait:
        study = run_study(db, study.id)
    else:
        background_tasks.add_task(_run_in_background, study.id)
    loaded = _load_study(db, study.id)
    return study_progress(loaded or study)


@router.post("/convergence")
def run_convergence_endpoint(
    spec: ConvergenceSpec,
    db: Session = Depends(get_db),
) -> dict:
    """Mesh yakınsama taraması (0.6.1) — tek geometri, artan çözünürlük.

    Senkron çalışır: basamak sayısı azdır (tipik 5-8) ve ara sonuç saklanacak
    bir tablo yok; bitince tablo tek parça döner. Basamaklar kabadan inceye
    koşulur, biri patlarsa tarama devam eder.
    """
    try:
        return run_convergence(db, spec)
    except UnknownTemplateError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConvergenceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/studies/{study_id}/results")
def study_results_endpoint(study_id: int, db: Session = Depends(get_db)) -> dict:
    """Örnek başına tek satır: parametreler + skalerler + analitik sapma.

    Tek tek run'a girmeden dağılımı görmek için (0.5.5 okuma tarafı).
    """
    study = db.get(DoeStudy, study_id)
    if study is None:
        raise HTTPException(status_code=404, detail=f"DOE bulunamadı: id={study_id}")
    return study_results(db, study)


@router.get("/studies/{study_id}/quality")
def study_quality(study_id: int, db: Session = Depends(get_db)) -> dict:
    study = _load_study(db, study_id)
    if study is None:
        raise HTTPException(status_code=404, detail="DOE çalışması yok.")
    return scan_study(db, study)
