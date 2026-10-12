"""Kompozit ply + CLT + layup + rozet + solve (Faz 3.1–3.9). `/solve` yok."""

from __future__ import annotations

import logging
import math
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.geometry import MESH_DIR
from app.composite.assemble import assemble_composite_layup, stack_thickness_mm
from app.composite.layup import Ply, abd_matrix
from app.db.session import get_db
from app.models.composite import (
    CompositeLayup,
    CompositeMaterial,
    CompositeOrientation,
    CompositeRun,
)
from app.models.geometry import Geometry
from app.solvers.base import SolverError
from app.solvers.calculix import CalculiXAdapter, _ccx_executable

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/composite", tags=["composite"])

COMPOSITE_RUNS_DIR = Path("uploads") / "composite_runs"
_CONSTRAINT_BC = ("fixed", "displacement", "sliding")
_TARGETED_BC = ("fixed", "cload", "pressure", "displacement", "sliding")


def _payload(m: CompositeMaterial) -> dict[str, Any]:
    return {
        "id": m.id,
        "name": m.name,
        "ply_kind": m.ply_kind,
        "category": m.category,
        "standard": m.standard,
        "density": m.density,
        "e1": m.e1,
        "e2": m.e2,
        "e3": m.e3,
        "nu12": m.nu12,
        "nu13": m.nu13,
        "nu23": m.nu23,
        "g12": m.g12,
        "g13": m.g13,
        "g23": m.g23,
        "xt": m.xt,
        "xc": m.xc,
        "yt": m.yt,
        "yc": m.yc,
        "s12": m.s12,
        "s13": m.s13,
        "s23": m.s23,
        "source": m.source,
        "is_editable": m.is_editable,
    }


@router.get("/materials")
def list_composite_materials(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Ply kütüphanesini listeler (tipik/nominal değerler)."""
    rows = db.query(CompositeMaterial).order_by(CompositeMaterial.name).all()
    return {
        "count": len(rows),
        "materials": [_payload(m) for m in rows],
    }


class CreateCompositeMaterialRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    ply_kind: str = Field(default="ud", description="ud | woven")
    category: str = Field(default="custom")
    density: float = Field(..., gt=0, description="kg/m³")
    e1: float = Field(..., gt=0, description="Pa")
    e2: float = Field(..., gt=0, description="Pa")
    e3: float = Field(..., gt=0, description="Pa")
    nu12: float = Field(..., gt=0, lt=0.5)
    nu13: float = Field(..., gt=0, lt=0.5)
    nu23: float = Field(..., gt=0, lt=0.5)
    g12: float = Field(..., gt=0, description="Pa")
    g13: float = Field(..., gt=0, description="Pa")
    g23: float = Field(..., gt=0, description="Pa")
    xt: float = Field(..., gt=0, description="Pa")
    xc: float = Field(..., gt=0, description="Pa")
    yt: float = Field(..., gt=0, description="Pa")
    yc: float = Field(..., gt=0, description="Pa")
    s12: float = Field(..., gt=0, description="Pa")
    s13: float | None = Field(default=None, gt=0, description="Pa")
    s23: float | None = Field(default=None, gt=0, description="Pa")


@router.post("/materials")
def create_composite_material(
    body: CreateCompositeMaterialRequest, db: Session = Depends(get_db)
) -> dict[str, Any]:
    """Kullanıcı tanımlı ortotrop ply ekler."""
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Malzeme adı boş olamaz.")
    ply_kind = (body.ply_kind or "ud").strip().lower()
    if ply_kind not in ("ud", "woven"):
        raise HTTPException(status_code=400, detail="ply_kind ud veya woven olmalı.")
    existing = (
        db.query(CompositeMaterial).filter(CompositeMaterial.name == name).one_or_none()
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"Malzeme adı kullanımda: {name}")

    mat = CompositeMaterial(
        name=name,
        ply_kind=ply_kind,
        category=body.category.strip() or "custom",
        standard=None,
        density=body.density,
        e1=body.e1,
        e2=body.e2,
        e3=body.e3,
        nu12=body.nu12,
        nu13=body.nu13,
        nu23=body.nu23,
        g12=body.g12,
        g13=body.g13,
        g23=body.g23,
        xt=body.xt,
        xc=body.xc,
        yt=body.yt,
        yc=body.yc,
        s12=body.s12,
        s13=body.s13,
        s23=body.s23,
        source="user_defined",
        is_editable=True,
    )
    db.add(mat)
    db.commit()
    db.refresh(mat)
    logger.info("Kompozit ply eklendi: id=%d name=%s", mat.id, mat.name)
    return {"material": _payload(mat)}


class CltPlyIn(BaseModel):
    """Tek katman; plies[0] alt. E Pa, t mm, θ° (laminat x → lif 1, CCW)."""

    e1: float = Field(..., gt=0, description="Pa")
    e2: float = Field(..., gt=0, description="Pa")
    g12: float = Field(..., gt=0, description="Pa")
    nu12: float
    thickness_mm: float = Field(..., gt=0)
    angle_deg: float = 0.0


class CltRequest(BaseModel):
    plies: list[CltPlyIn] = Field(..., min_length=1)


@router.post("/clt")
def compute_clt(body: CltRequest) -> dict[str, Any]:
    """Katman listesi → ABD. DB yok; yorum yok. A N/mm, B N, D N·mm."""
    try:
        plies = [
            Ply(
                e1=p.e1,
                e2=p.e2,
                g12=p.g12,
                nu12=p.nu12,
                thickness_mm=p.thickness_mm,
                angle_deg=p.angle_deg,
            )
            for p in body.plies
        ]
        abd = abd_matrix(plies)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "n_plies": len(plies),
        "h_mm": sum(p.thickness_mm for p in plies),
        **abd.as_lists(),
    }


class LayupPlyIn(BaseModel):
    material_id: int
    thickness_mm: float = Field(..., gt=0)
    angle_deg: float = 0.0


class PutLayupRequest(BaseModel):
    geometry_id: int
    part_id: int
    plies: list[LayupPlyIn] = Field(..., min_length=1)


def _stored_plies(plies: list[LayupPlyIn]) -> list[dict[str, float | int]]:
    return [
        {
            "material_id": p.material_id,
            "thickness_mm": p.thickness_mm,
            "angle_deg": p.angle_deg,
        }
        for p in plies
    ]


def _layup_payload(row: CompositeLayup, names: dict[int, str]) -> dict[str, Any]:
    out_plies: list[dict[str, Any]] = []
    for raw in row.plies or []:
        mid = int(raw["material_id"])
        out_plies.append(
            {
                "material_id": mid,
                "material_name": names.get(mid),
                "thickness_mm": float(raw["thickness_mm"]),
                "angle_deg": float(raw["angle_deg"]),
            }
        )
    return {
        "id": row.id,
        "geometry_id": row.geometry_id,
        "part_id": row.part_id,
        "n_plies": len(out_plies),
        "plies": out_plies,
    }


def _material_names(db: Session, material_ids: set[int]) -> dict[int, str]:
    if not material_ids:
        return {}
    rows = (
        db.query(CompositeMaterial)
        .filter(CompositeMaterial.id.in_(material_ids))
        .all()
    )
    return {m.id: m.name for m in rows}


@router.get("/layups")
def list_composite_layups(
    geometry_id: int,
    part_id: int | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Bir geometrinin dizilimlerini listeler (opsiyonel part_id)."""
    geo = db.get(Geometry, geometry_id)
    if geo is None:
        raise HTTPException(status_code=404, detail="Geometri bulunamadı.")
    q = db.query(CompositeLayup).filter(CompositeLayup.geometry_id == geometry_id)
    if part_id is not None:
        q = q.filter(CompositeLayup.part_id == part_id)
    rows = q.order_by(CompositeLayup.part_id).all()
    ids: set[int] = set()
    for row in rows:
        for raw in row.plies or []:
            ids.add(int(raw["material_id"]))
    names = _material_names(db, ids)
    return {
        "geometry_id": geometry_id,
        "count": len(rows),
        "layups": [_layup_payload(row, names) for row in rows],
    }


@router.put("/layups")
def put_composite_layup(body: PutLayupRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    """geometry + part için dizilimi yazar (yoksa oluşturur). plies[0] alt."""
    geo = db.get(Geometry, body.geometry_id)
    if geo is None:
        raise HTTPException(status_code=404, detail="Geometri bulunamadı.")

    wanted = {p.material_id for p in body.plies}
    names = _material_names(db, wanted)
    missing = wanted - names.keys()
    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"Ply malzemesi bulunamadı: {sorted(missing)[0]}",
        )

    existing = (
        db.query(CompositeLayup)
        .filter(
            CompositeLayup.geometry_id == body.geometry_id,
            CompositeLayup.part_id == body.part_id,
        )
        .one_or_none()
    )
    stored = _stored_plies(body.plies)
    if existing is None:
        existing = CompositeLayup(
            geometry_id=body.geometry_id,
            part_id=body.part_id,
            plies=stored,
        )
        db.add(existing)
    else:
        existing.plies = stored

    db.commit()
    db.refresh(existing)
    logger.info(
        "Kompozit layup: geometry_id=%d part_id=%d n_plies=%d",
        body.geometry_id,
        body.part_id,
        len(stored),
    )
    return {"layup": _layup_payload(existing, names)}


class PutOrientationRequest(BaseModel):
    geometry_id: int
    part_id: int
    kind: str = "parallel"
    dir0: list[float] = Field(default=[1.0, 0.0, 0.0], min_length=3, max_length=3)
    origin: list[float] = Field(default=[0.0, 0.0, 0.0], min_length=3, max_length=3)
    target: str = "part"
    face_ids: list[int] = Field(default_factory=list)


def _unit3(vec: list[float]) -> list[float]:
    n = math.sqrt(sum(float(c) * float(c) for c in vec))
    if n <= 0:
        raise HTTPException(status_code=400, detail="dir0 sıfır olamaz.")
    return [float(c) / n for c in vec]


def _orientation_payload(row: CompositeOrientation) -> dict[str, Any]:
    return {
        "id": row.id,
        "geometry_id": row.geometry_id,
        "part_id": row.part_id,
        "kind": row.kind,
        "dir0": [float(c) for c in row.dir0],
        "origin": [float(c) for c in row.origin],
        "target": row.target,
        "face_ids": [int(i) for i in (row.face_ids or [])],
    }


@router.get("/orientations")
def list_composite_orientations(
    geometry_id: int,
    part_id: int | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    geo = db.get(Geometry, geometry_id)
    if geo is None:
        raise HTTPException(status_code=404, detail="Geometri bulunamadı.")
    q = db.query(CompositeOrientation).filter(
        CompositeOrientation.geometry_id == geometry_id
    )
    if part_id is not None:
        q = q.filter(CompositeOrientation.part_id == part_id)
    rows = q.order_by(CompositeOrientation.part_id).all()
    return {
        "geometry_id": geometry_id,
        "count": len(rows),
        "orientations": [_orientation_payload(r) for r in rows],
    }


@router.put("/orientations")
def put_composite_orientation(
    body: PutOrientationRequest, db: Session = Depends(get_db)
) -> dict[str, Any]:
    """Paralel rozet + OSS. kind yalnız parallel; 0° = dir0 (varsayılan global X)."""
    geo = db.get(Geometry, body.geometry_id)
    if geo is None:
        raise HTTPException(status_code=404, detail="Geometri bulunamadı.")
    kind = (body.kind or "parallel").strip().lower()
    if kind != "parallel":
        raise HTTPException(status_code=400, detail="kind parallel olmalı.")
    target = (body.target or "part").strip().lower()
    if target not in ("part", "faces"):
        raise HTTPException(status_code=400, detail="target part veya faces olmalı.")
    face_ids = [int(i) for i in body.face_ids]
    if target == "faces" and not face_ids:
        raise HTTPException(status_code=400, detail="face_ids gerekli.")
    dir0 = _unit3(list(body.dir0))
    origin = [float(c) for c in body.origin]

    existing = (
        db.query(CompositeOrientation)
        .filter(
            CompositeOrientation.geometry_id == body.geometry_id,
            CompositeOrientation.part_id == body.part_id,
        )
        .one_or_none()
    )
    if existing is None:
        existing = CompositeOrientation(
            geometry_id=body.geometry_id,
            part_id=body.part_id,
            kind=kind,
            dir0=dir0,
            origin=origin,
            target=target,
            face_ids=face_ids if target == "faces" else [],
        )
        db.add(existing)
    else:
        existing.kind = kind
        existing.dir0 = dir0
        existing.origin = origin
        existing.target = target
        existing.face_ids = face_ids if target == "faces" else []

    db.commit()
    db.refresh(existing)
    logger.info(
        "Kompozit rozet: geometry_id=%d part_id=%d target=%s",
        body.geometry_id,
        body.part_id,
        target,
    )
    return {"orientation": _orientation_payload(existing)}


class CompositeSolveBC(BaseModel):
    type: str
    face_ids: list[int] | None = None
    edge_ids: list[int] | None = None
    node_ids: list[int] | None = None
    mesh_node_ids: list[int] | None = None
    fx: float | None = None
    fy: float | None = None
    fz: float | None = None
    magnitude: float | None = None
    dx: float | None = None
    dy: float | None = None
    dz: float | None = None


class CompositeSolveRequest(BaseModel):
    geometry_id: int
    part_id: int = 0
    dimension: int = 2
    run_solver: bool = False
    name: str | None = None
    bcs: list[CompositeSolveBC] = Field(default_factory=list)


def _material_dict(m: CompositeMaterial) -> dict[str, Any]:
    return {
        "name": m.name,
        "e1": m.e1,
        "e2": m.e2,
        "e3": m.e3,
        "nu12": m.nu12,
        "nu13": m.nu13,
        "nu23": m.nu23,
        "g12": m.g12,
        "g13": m.g13,
        "g23": m.g23,
        "density": m.density,
    }


def _run_payload(row: CompositeRun) -> dict[str, Any]:
    return {
        "id": row.id,
        "job_id": row.job_id,
        "geometry_id": row.geometry_id,
        "part_id": row.part_id,
        "name": row.name,
        "dimension": row.dimension,
        "status": row.status,
        "message": row.message,
        "solver_ran": row.solver_ran,
        "inp_path": row.inp_path,
        "inp_url": (
            f"/files/composite_runs/{row.id}/{Path(row.inp_path).name}"
            if row.inp_path
            else None
        ),
        "scalars": row.scalars or {},
        "ccx_available": _ccx_executable() is not None,
    }


@router.get("/runs")
def list_composite_runs(
    geometry_id: int, db: Session = Depends(get_db)
) -> dict[str, Any]:
    geo = db.get(Geometry, geometry_id)
    if geo is None:
        raise HTTPException(status_code=404, detail="Geometri bulunamadı.")
    rows = (
        db.query(CompositeRun)
        .filter(CompositeRun.geometry_id == geometry_id)
        .order_by(CompositeRun.id.desc())
        .all()
    )
    return {
        "geometry_id": geometry_id,
        "count": len(rows),
        "runs": [_run_payload(r) for r in rows],
    }


@router.post("/solve")
def composite_solve(
    body: CompositeSolveRequest, db: Session = Depends(get_db)
) -> dict[str, Any]:
    """Mesh + layup + BC → CalculiXAdapter. `/solve` (durability) dokunulmaz."""
    if body.dimension != 2:
        raise HTTPException(status_code=400, detail="dimension 2 olmalı.")
    geo = db.get(Geometry, body.geometry_id)
    if geo is None:
        raise HTTPException(status_code=404, detail="Geometri bulunamadı.")

    layup_row = (
        db.query(CompositeLayup)
        .filter(
            CompositeLayup.geometry_id == body.geometry_id,
            CompositeLayup.part_id == body.part_id,
        )
        .one_or_none()
    )
    if layup_row is None or not layup_row.plies:
        raise HTTPException(status_code=422, detail="Bu parça için dizilim yok.")

    bcs = [bc.model_dump(exclude_none=True) for bc in body.bcs]
    if not bcs:
        raise HTTPException(status_code=422, detail="En az bir sınır koşulu gerekli.")
    if not any(str(bc.get("type") or "") in _CONSTRAINT_BC for bc in bcs):
        raise HTTPException(
            status_code=422,
            detail="En az bir yer değiştirme kısıtı gerekli (fixed / displacement / sliding).",
        )
    empty = [
        f"#{i} {bc.get('type')}"
        for i, bc in enumerate(bcs)
        if str(bc.get("type") or "") in _TARGETED_BC
        and not (
            bc.get("face_ids")
            or bc.get("edge_ids")
            or bc.get("node_ids")
            or bc.get("mesh_node_ids")
        )
    ]
    if empty:
        raise HTTPException(status_code=422, detail="Hedefsiz BC var.")

    stem = Path(geo.current_filename).stem
    mesh_path = MESH_DIR / f"{stem}_d{body.dimension}.msh"
    if not mesh_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Önce dimension={body.dimension} mesh üretin ({mesh_path.name}).",
        )

    mat_ids = {int(p["material_id"]) for p in layup_row.plies}
    mats = {
        m.id: _material_dict(m)
        for m in db.query(CompositeMaterial)
        .filter(CompositeMaterial.id.in_(mat_ids))
        .all()
    }
    ori = (
        db.query(CompositeOrientation)
        .filter(
            CompositeOrientation.geometry_id == body.geometry_id,
            CompositeOrientation.part_id == body.part_id,
        )
        .one_or_none()
    )
    try:
        spec = assemble_composite_layup(
            part_id=body.part_id,
            plies=list(layup_row.plies),
            materials=mats,
            dir0=list(ori.dir0) if ori is not None else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    job_id = str(uuid.uuid4())
    run = CompositeRun(
        job_id=job_id,
        geometry_id=body.geometry_id,
        part_id=body.part_id,
        name=body.name,
        dimension=body.dimension,
        status="pending",
        request={"geometry_id": body.geometry_id, "part_id": body.part_id},
        layup_snapshot=spec["plies"],
        orientation_snapshot=(
            {"dir0": list(ori.dir0), "target": ori.target} if ori is not None else None
        ),
        bcs=bcs,
        scalars={},
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    run_dir = COMPOSITE_RUNS_DIR / str(run.id)
    run_dir.mkdir(parents=True, exist_ok=True)
    adapter = CalculiXAdapter()
    try:
        artifact = adapter.build_input(
            {
                "mesh_path": mesh_path,
                "dimension": 2,
                "output_dir": run_dir,
                "job_name": f"crun{run.id}",
                "materials": [],
                "shell_thickness": stack_thickness_mm(spec),
                "bcs": bcs,
                "analysis_type": "static",
                "composite_layup": spec,
            }
        )
    except SolverError as exc:
        run.status = "failed"
        run.message = str(exc)
        db.commit()
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    inp_text = artifact.path.read_text(encoding="utf-8")
    run.inp_path = str(artifact.path).replace("\\", "/")
    run.status = "inp_only"
    run.message = "inp üretildi"
    run.scalars = {
        "has_composite": "COMPOSITE" in inp_text,
        "has_engineering": "ENGINEERING CONSTANTS" in inp_text,
    }
    db.commit()

    result = _run_payload(run)
    result["cards"] = {
        "has_composite": "COMPOSITE" in inp_text,
        "has_engineering": "ENGINEERING CONSTANTS" in inp_text,
        "has_orientation": "*ORIENTATION" in inp_text,
        "has_step": "*STEP" in inp_text,
    }

    if body.run_solver:
        try:
            handle = adapter.submit(artifact)
            parsed = adapter.parse_results(handle)
            run.solver_ran = True
            run.status = "solved"
            run.message = "ccx bitti"
            run.scalars = {**(run.scalars or {}), **(parsed.scalars or {})}
            db.commit()
            result = _run_payload(run)
            result["cards"] = result.get("cards") or {}
        except SolverError as exc:
            run.status = "failed"
            run.message = str(exc)
            db.commit()
            result = _run_payload(run)
            result["message"] = str(exc)

    logger.info(
        "Kompozit solve: run_id=%d geometry_id=%d status=%s",
        run.id,
        body.geometry_id,
        run.status,
    )
    return {"run": result}
