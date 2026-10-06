"""Crash DOE kuyruğu — 1.19c-2: örnekleri sırayla `/crash/scenario` ile koşar.

Durability `doe/runner.py` deseni: bir örnek patlarsa diğerlerine devam;
bitmiş (solved / rad_only) örnek tekrar koşulmaz → yarıda kalan çalışma
`run_study` ile kaldığı yerden sürer. Yeni çözücü mantığı yok.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.doe.crash_sampling import CrashDoeError, CrashDoeSpec, sample_crash_cases
from app.models.crash_doe import CrashDoeCase, CrashDoeStudy

logger = logging.getLogger(__name__)

DONE = ("solved", "rad_only")


class _NoopBackground:
    def add_task(self, *args: Any, **kwargs: Any) -> None:
        return None


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
    from app.api.crash_scenario import CrashScenarioRequest, crash_scenario

    body = {**case.request, "wait": True, "name": f"DOE {study.id} · {case.index}"}
    result = crash_scenario(CrashScenarioRequest.model_validate(body), _NoopBackground(), db)  # type: ignore[arg-type]
    crash = result.get("crash") or {}
    case.geometry_id = result.get("geometry_id")
    case.run_id = crash.get("run_id")
    status = str(crash.get("status") or "failed")
    case.status = status if status in DONE else "failed"
    case.message = crash.get("message")


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
