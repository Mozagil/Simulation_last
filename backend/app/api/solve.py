"""CalculiX solve API — .inp üret + isteğe bağlı ccx çalıştır."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload

from app.api.geometry import MESH_DIR, UPLOAD_DIR, _get_geometry_or_404
from app.db.session import get_db
from app.models.material import MaterialAssignment
from app.solvers.base import SolverError
from app.solvers.calculix import CalculiXAdapter, _ccx_executable

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/geometry", tags=["solve"])

RUNS_DIR = Path("uploads") / "runs"


class SolveBC(BaseModel):
    type: str
    face_ids: list[int] | None = None
    edge_ids: list[int] | None = None
    node_ids: list[int] | None = None
    fx: float | None = None
    fy: float | None = None
    fz: float | None = None
    magnitude: float | None = None
    dx: float | None = None
    dy: float | None = None
    dz: float | None = None
    gx: float | None = None
    gy: float | None = None
    gz: float | None = None
    dofs: dict[str, float] | None = None
    axis: list[float] | None = None
    normal: list[float] | None = None


class SolveRequest(BaseModel):
    dimension: int = Field(..., description="2 | 3")
    shell_thickness: float = Field(default=3.0, gt=0)
    run_solver: bool = Field(
        default=False,
        description="True ise ccx çalıştırılır (kurulu olmalı)",
    )
    bcs: list[SolveBC] = Field(default_factory=list)


@router.post("/{geometry_id}/solve")
def solve_geometry(
    geometry_id: int, body: SolveRequest, db: Session = Depends(get_db)
) -> dict[str, Any]:
    """Mesh + malzeme atamalarından CalculiX .inp üretir; isteğe bağlı ccx."""
    if body.dimension not in (2, 3):
        raise HTTPException(status_code=400, detail="dimension 2 veya 3 olmalı.")

    geo = _get_geometry_or_404(db, geometry_id)
    stem = Path(geo.current_filename).stem
    mesh_path = MESH_DIR / f"{stem}_d{body.dimension}.msh"
    if not mesh_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Önce dimension={body.dimension} mesh üretin ({mesh_path.name}).",
        )

    assignments = (
        db.query(MaterialAssignment)
        .options(joinedload(MaterialAssignment.material))
        .filter(MaterialAssignment.geometry_id == geometry_id)
        .all()
    )
    if not assignments:
        raise HTTPException(
            status_code=422,
            detail="En az bir parça için malzeme atayın.",
        )

    materials = [
        {
            "part_id": a.part_id,
            "name": a.material.name,
            "density": a.material.density,
            "youngs_modulus": a.material.youngs_modulus,
            "poisson_ratio": a.material.poisson_ratio,
        }
        for a in assignments
    ]

    run_dir = RUNS_DIR / str(geometry_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    job_name = f"geo{geometry_id}_d{body.dimension}"

    bcs = [bc.model_dump(exclude_none=True) for bc in body.bcs]
    # En az bir fixed yoksa ve bcs boşsa — hardcoded basit senaryo
    if not bcs:
        bcs = [
            {"type": "fixed", "face_ids": []},  # adapter atlar
            {"type": "gravity", "gx": 0.0, "gy": 0.0, "gz": -9810.0},
        ]

    adapter = CalculiXAdapter()
    try:
        artifact = adapter.build_input(
            {
                "mesh_path": mesh_path,
                "dimension": body.dimension,
                "output_dir": run_dir,
                "job_name": job_name,
                "materials": materials,
                "shell_thickness": body.shell_thickness,
                "bcs": bcs,
            }
        )
    except SolverError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    inp_text = artifact.path.read_text(encoding="utf-8")
    cards_ok = {
        "has_material": "*MATERIAL" in inp_text,
        "has_elastic": "*ELASTIC" in inp_text,
        "has_density": "*DENSITY" in inp_text,
        "has_section": ("*SOLID SECTION" in inp_text) or ("*SHELL SECTION" in inp_text),
        "has_step": "*STEP" in inp_text,
    }

    result: dict[str, Any] = {
        "geometry_id": geometry_id,
        "dimension": body.dimension,
        "inp_path": str(artifact.path).replace("\\", "/"),
        "inp_url": f"/files/runs/{geometry_id}/{artifact.path.name}",
        "ccx_available": _ccx_executable() is not None,
        "cards": cards_ok,
        "solver_ran": False,
        "job_id": None,
        "frd_path": None,
        "message": "inp üretildi",
    }

    if body.run_solver:
        try:
            handle = adapter.submit(artifact)
            status = adapter.poll_status(handle)
            parsed = adapter.parse_results(handle)
            result["solver_ran"] = True
            result["job_id"] = handle.job_id
            result["frd_path"] = (
                str(parsed.raw_result_path).replace("\\", "/")
                if parsed.raw_result_path
                else None
            )
            result["message"] = f"ccx bitti ({status.state})"
            result["scalars"] = parsed.scalars
            result["results_preview_url"] = (
                f"/files/runs/{geometry_id}/{parsed.results_preview_path.name}"
                if parsed.results_preview_path
                else None
            )
        except SolverError as exc:
            result["message"] = str(exc)
            # .inp yine döner; 200 ile uyarı
            logger.warning("ccx çalıştırılamadı: %s", exc)

    logger.info(
        "Solve: geometry_id=%d dim=%d inp=%s ran=%s",
        geometry_id,
        body.dimension,
        artifact.path,
        result["solver_ran"],
    )
    return result


# Static mount için dizin
Path(RUNS_DIR).mkdir(parents=True, exist_ok=True)
_ = UPLOAD_DIR
