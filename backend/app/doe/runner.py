"""DOE kuyruğu: örnekleri sırayla işler, hata tüm çalışmayı durdurmaz (0.5.4)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.api.geometry import GenerateMeshRequest, generate_mesh
from app.api.solve import SolveBC, SolveRequest, solve_geometry
from app.doe.regions import DoeBindError, bind_scenario_bcs, groups_by_name
from app.doe.sampling import DoeSample, DoeSpec, sample_spec
from app.models.doe import DoeCase, DoeStudy
from app.models.material import Material, MaterialAssignment
from app.templates.service import create_geometry_from_template

logger = logging.getLogger(__name__)


class _NoopBackground:
    def add_task(self, *args: Any, **kwargs: Any) -> None:
        return None


def _material_map(db: Session, spec: DoeSpec) -> dict[int, dict[str, Any]]:
    """Ön eleme için malzeme özellikleri (E, akma)."""
    out: dict[int, dict[str, Any]] = {}
    for mid in spec.material_ids:
        m = db.get(Material, mid)
        if m is not None:
            out[mid] = {
                "youngs_modulus": m.youngs_modulus,
                "yield_strength": m.yield_strength,
            }
    return out


def persist_study(db: Session, spec: DoeSpec) -> DoeStudy:
    samples = sample_spec(spec, _material_map(db, spec))
    study = DoeStudy(
        name=spec.name or spec.template_id,
        template_id=spec.template_id,
        seed=spec.seed,
        spec=spec.model_dump(),
        status="pending",
    )
    db.add(study)
    db.flush()
    for s in samples:
        db.add(
            DoeCase(
                study_id=study.id,
                index=s.index,
                geometry_params=s.geometry_params,
                element_size=s.element_size,
                material_id=s.material_id,
                scenario_name=s.scenario.name,
                status="pending",
            )
        )
    db.commit()
    db.refresh(study)
    return study


def _execute_sample(db: Session, spec: DoeSpec, sample: DoeSample, case: DoeCase) -> None:
    mat = db.get(Material, sample.material_id)
    if mat is None:
        raise RuntimeError(f"Malzeme yok: id={sample.material_id}")

    geo, _regions, _tess = create_geometry_from_template(
        db, spec.template_id, sample.geometry_params
    )
    case.geometry_id = geo.id
    db.add(
        MaterialAssignment(geometry_id=geo.id, part_id=0, material_id=sample.material_id)
    )
    db.commit()

    generate_mesh(
        geo.id,
        GenerateMeshRequest(
            element_size=sample.element_size,
            dimension=spec.dimension,
            element_scheme=spec.element_scheme,
        ),
        db,
    )

    groups = groups_by_name(db, geo.id)
    bound = bind_scenario_bcs(groups, sample.scenario.bcs)
    case.bound_bcs = bound
    db.commit()

    body = SolveRequest(
        dimension=spec.dimension,
        run_solver=spec.run_solver,
        wait=True,
        name=f"DOE {case.index} · {sample.scenario.name}",
        element_size=sample.element_size,
        element_scheme=spec.element_scheme,
        analysis_type=spec.analysis_type,
        bcs=[SolveBC.model_validate(bc) for bc in bound],
    )
    result = solve_geometry(geo.id, body, _NoopBackground(), db)  # type: ignore[arg-type]
    case.run_id = result.get("run_id")
    status = str(result.get("status") or "failed")
    if status == "solved":
        case.status = "solved"
    elif status == "inp_only":
        case.status = "inp_only"
    else:
        case.status = "failed"
    case.message = result.get("message")


def run_study(db: Session, study_id: int) -> DoeStudy:
    """Bekleyen örnekleri işler. Bir örnek patlarsa diğerlerine devam."""
    study = db.get(DoeStudy, study_id)
    if study is None:
        raise HTTPException(status_code=404, detail="DOE çalışması yok.")
    spec = DoeSpec.model_validate(study.spec)
    study.status = "running"
    db.commit()

    cases = (
        db.query(DoeCase)
        .filter(DoeCase.study_id == study_id)
        .order_by(DoeCase.index)
        .all()
    )
    samples = {s.index: s for s in sample_spec(spec, _material_map(db, spec))}
    failed = 0
    for case in cases:
        if case.status in ("solved", "inp_only"):
            continue
        sample = samples.get(case.index)
        if sample is None:
            case.status = "failed"
            case.message = "örnek indeksi kayıp"
            failed += 1
            db.commit()
            continue
        try:
            _execute_sample(db, spec, sample, case)
        except (HTTPException, DoeBindError, Exception) as exc:  # noqa: BLE001
            logger.warning("DOE case %s/%s hata: %s", study_id, case.index, exc)
            case.status = "failed"
            detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
            case.message = str(detail)
            failed += 1
        db.commit()

    n = len(cases)
    n_ok = sum(1 for c in cases if c.status in ("solved", "inp_only"))
    study.status = "completed" if failed == 0 else "completed_with_errors"
    study.message = f"{n_ok}/{n} başarılı"
    db.commit()
    db.refresh(study)
    return study


def study_progress(study: DoeStudy) -> dict[str, Any]:
    cases = list(study.cases)
    counts: dict[str, int] = {}
    for c in cases:
        counts[c.status] = counts.get(c.status, 0) + 1
    return {
        "id": study.id,
        "name": study.name,
        "template_id": study.template_id,
        "seed": study.seed,
        "status": study.status,
        "message": study.message,
        "n_cases": len(cases),
        "counts": counts,
        "cases": [
            {
                "id": c.id,
                "index": c.index,
                "status": c.status,
                "scenario": c.scenario_name,
                "element_size": c.element_size,
                "geometry_params": c.geometry_params,
                "geometry_id": c.geometry_id,
                "run_id": c.run_id,
                "message": c.message,
            }
            for c in sorted(cases, key=lambda x: x.index)
        ],
    }
