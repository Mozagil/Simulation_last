"""Crash DOE kuyruğu — 1.19c-2: örnekleri sırayla `/crash/scenario` ile koşar.

Durability `doe/runner.py` deseni: bir örnek patlarsa diğerlerine devam;
bitmiş (solved / rad_only) örnek tekrar koşulmaz → yarıda kalan çalışma
`run_study` ile kaldığı yerden sürer. Yeni çözücü mantığı yok.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.doe.crash_sampling import CrashDoeError, CrashDoeSpec, sample_crash_cases
from app.models.crash_doe import CrashDoeCase, CrashDoeStudy

logger = logging.getLogger(__name__)

DONE = ("solved", "rad_only")

# 1.25a2 — çalışan örneğin işi (bellekte; şema değişmez). study_id → {case_index, job_id}.
# Sunucu yeniden başlarsa kaybolur — o anda koşu da kesilmiş olur.
_CURRENT: dict[int, dict[str, Any]] = {}
_CURRENT_LOCK = threading.Lock()


def current_job(study_id: int) -> dict[str, Any] | None:
    """Çalışmanın o an koşan örneği: {"case_index", "job_id"} ya da None."""
    with _CURRENT_LOCK:
        cur = _CURRENT.get(study_id)
        return dict(cur) if cur else None


def _set_current(study_id: int, value: dict[str, Any] | None) -> None:
    with _CURRENT_LOCK:
        if value is None:
            _CURRENT.pop(study_id, None)
        else:
            _CURRENT[study_id] = value


class _CollectBackground:
    """`crash_solve`'un arka plan işini toplar; runner job_id'yi kaydedip aynı süreçte koşturur."""

    def __init__(self) -> None:
        self.tasks: list[tuple[Callable[..., Any], tuple[Any, ...], dict[str, Any]]] = []

    def add_task(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        self.tasks.append((func, args, kwargs))


def persist_study(db: Session, spec: CrashDoeSpec) -> CrashDoeStudy:
    cases = sample_crash_cases(spec)
    if not cases:
        raise CrashDoeError("Aralıklarda şablon doğrulamasından geçen örnek yok.")
    template_id = str(cases[0]["request"]["template_id"])
    study = CrashDoeStudy(
        name=spec.name or template_id,
        template_id=template_id,
        seed=spec.seed,
        spec=spec.model_dump(mode="json"),
        status="pending",
        message=None if len(cases) == spec.n_samples else f"{len(cases)}/{spec.n_samples} geçerli örnek",
    )
    db.add(study)
    db.flush()
    for c in cases:
        db.add(CrashDoeCase(study_id=study.id, index=c["index"], values=c["values"],
                            request=c["request"], status="pending"))
    db.commit()
    db.refresh(study)
    return study


def _execute_case(db: Session, study: CrashDoeStudy, case: CrashDoeCase) -> None:
    from app.api.crash import _read_job
    from app.api.crash_scenario import CrashScenarioRequest, crash_scenario

    # 1.25a2: wait=False → iş oluşur, job_id döner; çözüm (toplanan arka plan işi) burada,
    # aynı süreçte koşar. Bu arada job_id "çalışan iş" olarak okunabilir (canlı ilerleme).
    body = {**case.request, "wait": False, "name": f"DOE {study.id} · {case.index}"}
    bg = _CollectBackground()
    result = crash_scenario(CrashScenarioRequest.model_validate(body), bg, db)  # type: ignore[arg-type]
    crash = result.get("crash") or {}
    case.geometry_id = result.get("geometry_id")
    case.run_id = crash.get("run_id")
    job_id = crash.get("job_id")
    if bg.tasks:
        case.status = "running"  # DONE değil → yarıda kalırsa devamda yeniden koşulur
        db.commit()  # geometri / koşu no'su çalışma sırasında görünsün
        _set_current(study.id, {"case_index": case.index, "job_id": job_id})
        try:
            for func, args, kwargs in bg.tasks:
                func(*args, **kwargs)
        finally:
            _set_current(study.id, None)
        done = (_read_job(job_id) if job_id else None) or crash
    else:
        done = crash
    status = str(done.get("status") or "failed")
    case.status = status if status in DONE else "failed"
    case.message = done.get("message")


def run_study(db: Session, study_id: int) -> CrashDoeStudy:
    """Bekleyen / başarısız örnekleri işler."""
    study = db.get(CrashDoeStudy, study_id)
    if study is None:
        raise HTTPException(status_code=404, detail="Crash DOE çalışması yok.")
    study.status = "running"
    db.commit()

    cases = db.query(CrashDoeCase).filter(CrashDoeCase.study_id == study_id).order_by(CrashDoeCase.index).all()
    for case in cases:
        if case.status in DONE:
            continue
        try:
            _execute_case(db, study, case)
        except Exception as exc:  # noqa: BLE001 — bir örnek çalışmayı durdurmaz
            db.rollback()
            logger.warning("Crash DOE %s/%s hata: %s", study_id, case.index, exc)
            case.status = "failed"
            case.message = str(exc.detail if isinstance(exc, HTTPException) else exc)
        db.commit()

    n_ok = sum(1 for c in cases if c.status in DONE)
    study.status = "completed" if n_ok == len(cases) else "completed_with_errors"
    study.message = f"{n_ok}/{len(cases)} başarılı"
    db.commit()
    db.refresh(study)
    return study


def study_progress(study: CrashDoeStudy, with_cases: bool = True) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for c in study.cases:
        counts[c.status] = counts.get(c.status, 0) + 1
    out: dict[str, Any] = {
        "id": study.id,
        "name": study.name,
        "template_id": study.template_id,
        "seed": study.seed,
        "status": study.status,
        "message": study.message,
        "created_at": study.created_at.isoformat() if study.created_at else None,
        "vary": study.spec.get("vary"),
        "n_cases": len(study.cases),
        "counts": counts,
    }
    cur = current_job(study.id)
    out["current_job_id"] = cur["job_id"] if cur else None
    out["current_case_index"] = cur["case_index"] if cur else None
    if with_cases:
        out["cases"] = [
            {
                "id": c.id,
                "index": c.index,
                "status": c.status,
                "values": c.values,
                "geometry_id": c.geometry_id,
                "run_id": c.run_id,
                "message": c.message,
            }
            for c in study.cases
        ]
    return out
