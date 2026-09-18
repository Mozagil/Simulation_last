"""Convergence taramasını koşturur: her basamak için geometri + mesh + çözüm.

`doe/runner.py` ile aynı boru hattını kullanır (create_geometry_from_template →
generate_mesh → bind BC → solve) ama örnekleme yok: eleman boyutu merdiveni
deterministik. Kalıcılık için ayrı tablo AÇMIYORUZ — DoeStudy/DoeCase birebir
uyuyor (sabit geometri + değişen element_size). Ayırt edici işaret:
`spec["kind"] == "convergence"`.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.api.geometry import GenerateMeshRequest, generate_mesh
from app.api.solve import SolveBC, SolveRequest, solve_geometry
from app.doe.convergence import (
    ConvergenceSpec,
    assess_convergence,
    element_size_ladder,
    recommended_ratio,
)
from app.doe.regions import DoeBindError, bind_scenario_bcs, groups_by_name
from app.models.doe import DoeCase, DoeStudy
from app.models.material import Material, MaterialAssignment
from app.models.run import AnalysisRun
from app.templates.service import create_geometry_from_template

logger = logging.getLogger(__name__)

CONVERGENCE_KIND = "convergence"


class _NoopBackground:
    def add_task(self, *args: Any, **kwargs: Any) -> None:
        return None


def persist_convergence(db: Session, spec: ConvergenceSpec) -> DoeStudy:
    """Merdiveni DoeCase satırlarına açar; henüz hiçbir şey çözülmez."""
    sizes = element_size_ladder(spec)
    payload = spec.model_dump()
    payload["kind"] = CONVERGENCE_KIND
    payload["element_sizes"] = sizes

    study = DoeStudy(
        name=spec.name or f"convergence · {spec.template_id}",
        template_id=spec.template_id,
        seed=0,
        spec=payload,
        status="pending",
    )
    db.add(study)
    db.flush()
    for i, size in enumerate(sizes):
        db.add(
            DoeCase(
                study_id=study.id,
                index=i,
                geometry_params=spec.geometry_params,
                element_size=size,
                material_id=spec.material_id,
                scenario_name=spec.scenario_name,
                status="pending",
            )
        )
    db.commit()
    db.refresh(study)
    return study


def _execute_step(db: Session, spec: ConvergenceSpec, case: DoeCase) -> None:
    mat = db.get(Material, spec.material_id)
    if mat is None:
        raise RuntimeError(f"Malzeme yok: id={spec.material_id}")

    geo, _regions, _tess = create_geometry_from_template(
        db, spec.template_id, spec.geometry_params
    )
    case.geometry_id = geo.id
    db.add(
        MaterialAssignment(geometry_id=geo.id, part_id=0, material_id=spec.material_id)
    )
    db.commit()

    generate_mesh(
        geo.id,
        GenerateMeshRequest(
            element_size=case.element_size,
            dimension=spec.dimension,
            element_scheme=spec.element_scheme,
        ),
        db,
    )

    groups = groups_by_name(db, geo.id)
    bound = bind_scenario_bcs(groups, spec.bcs)
    case.bound_bcs = bound
    db.commit()

    body = SolveRequest(
        dimension=spec.dimension,
        run_solver=True,  # convergence ölçmek için çözüm ŞART
        wait=True,
        name=f"convergence es={case.element_size} · {spec.scenario_name}",
        element_size=case.element_size,
        element_scheme=spec.element_scheme,
        analysis_type="static",
        bcs=[SolveBC.model_validate(bc) for bc in bound],
    )
    result = solve_geometry(geo.id, body, _NoopBackground(), db)  # type: ignore[arg-type]
    case.run_id = result.get("run_id")
    status = str(result.get("status") or "failed")
    case.status = "solved" if status == "solved" else "failed"
    case.message = result.get("message")


def run_convergence(db: Session, study_id: int) -> DoeStudy:
    """Bekleyen basamakları sırayla çözer. Bir basamak patlarsa devam eder."""
    study = db.get(DoeStudy, study_id)
    if study is None:
        raise HTTPException(status_code=404, detail="Çalışma yok.")
    if (study.spec or {}).get("kind") != CONVERGENCE_KIND:
        raise HTTPException(status_code=400, detail="Bu bir convergence çalışması değil.")

    spec = ConvergenceSpec.model_validate(
        {k: v for k, v in study.spec.items() if k not in ("kind", "element_sizes")}
    )
    study.status = "running"
    db.commit()

    cases = (
        db.query(DoeCase)
        .filter(DoeCase.study_id == study_id)
        .order_by(DoeCase.index)
        .all()
    )
    failed = 0
    for case in cases:
        if case.status == "solved":
            continue
        try:
            _execute_step(db, spec, case)
        except (HTTPException, DoeBindError, Exception) as exc:  # noqa: BLE001
            logger.warning("convergence %s/%s hata: %s", study_id, case.index, exc)
            case.status = "failed"
            detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
            case.message = str(detail)
            failed += 1
        db.commit()

    n_ok = sum(1 for c in cases if c.status == "solved")
    study.status = "completed" if failed == 0 else "completed_with_errors"
    study.message = f"{n_ok}/{len(cases)} basamak çözüldü"
    db.commit()
    db.refresh(study)
    return study


def convergence_report(db: Session, study_id: int) -> dict[str, Any]:
    """Basamakların skalerlerini toplayıp yakınsama kararını üretir."""
    study = db.get(DoeStudy, study_id)
    if study is None:
        raise HTTPException(status_code=404, detail="Çalışma yok.")
    if (study.spec or {}).get("kind") != CONVERGENCE_KIND:
        raise HTTPException(status_code=400, detail="Bu bir convergence çalışması değil.")

    spec_raw = study.spec or {}
    cases = (
        db.query(DoeCase)
        .filter(DoeCase.study_id == study_id)
        .order_by(DoeCase.index)
        .all()
    )

    steps: list[dict[str, Any]] = []
    for case in cases:
        row: dict[str, Any] = {
            "index": case.index,
            "element_size": case.element_size,
            "status": case.status,
            "run_id": case.run_id,
            "message": case.message,
            "node_count": None,
            "element_count": None,
            "max_displacement": None,
            "max_von_mises": None,
        }
        if case.run_id is not None:
            run = db.get(AnalysisRun, case.run_id)
            if run is not None:
                sc = run.scalars or {}
                row["node_count"] = sc.get("node_count")
                row["element_count"] = sc.get("element_count")
                row["max_displacement"] = sc.get("max_displacement")
                row["max_von_mises"] = sc.get("max_von_mises")
                # Analitik karşılaştırma varsa taşı: mesh incelirken teoriye
                # yaklaşıp yaklaşmadığını görmek asıl doğrulama.
                if "_analytic_comparison" in sc:
                    row["analytic"] = sc["_analytic_comparison"]
        steps.append(row)

    tol_d = float(spec_raw.get("tol_disp") or 0.02)
    tol_s = float(spec_raw.get("tol_stress") or 0.05)
    assessment = assess_convergence(steps, tol_disp=tol_d, tol_stress=tol_s)
    char_len = float(spec_raw.get("characteristic_length") or 0.0)
    assessment["recommended_ratio"] = recommended_ratio(assessment, char_len)

    return {
        "study_id": study.id,
        "name": study.name,
        "template_id": study.template_id,
        "status": study.status,
        "message": study.message,
        "characteristic_length": char_len,
        **assessment,
    }
