"""Crash senaryo şablonu — 1.17a.

Tek çağrıda uçtan uca crash koşusu: geometri şablonu → 2D mesh → malzeme
ataması → /crash/solve (kabuk kalınlığı, bariyer, model, engine/th/kesitler).
Yeni çözücü mantığı yok: mevcut uçların fonksiyonlarını sırayla çağırır
(0.5.4 DOE runner deseni). Hangi parametrenin değişeceğine mühendis karar
verir; burada hepsi açık girdi, varsayılanlar 1.13–1.16 elle koşulan crash box
(geometri 3931) kurulumu.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field, ValidationError, model_validator
from sqlalchemy.orm import Session

from app.api.crash import CrashSolveRequest, crash_solve
from app.api.geometry import GenerateMeshRequest, generate_mesh
from app.db.session import get_db
from app.models.material import Material, MaterialAssignment
from app.solvers.crash_params import (
    CrashContactParams,
    CrashBcParams,
    CrashEngineParams,
    CrashFilterParams,
    CrashImpVelParams,
    CrashMassParams,
    CrashModelParams,
    CrashRigidBodyParams,
    CrashSectionParams,
    CrashThParams,
)
from app.templates import get_template
from app.templates.service import create_geometry_from_template

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/crash", tags=["crash"])

#: Crash senaryosu kurulabilen şablonlar → mesh boyutu (2 kabuk). Solid /
#: çok parçalı crash_box_plate ayrı adım (iki parça, temas, rol).
CRASH_TEMPLATES: dict[str, int] = {"crash_box_shell": 2}


class CrashWall(BaseModel):
    point: tuple[float, float, float]
    normal: tuple[float, float, float]


class CrashScenarioRequest(BaseModel):
    template_id: str = Field(default="crash_box_shell")
    geometry: dict[str, Any] = Field(
        default_factory=dict, description="Şablon parametreleri (mm); boş alan = şablon varsayılanı"
    )
    element_size_mm: float = Field(default=5.0, gt=0)
    element_scheme: str = Field(default="quad", description="2D: quad | tet (tri) | mix")
    material_id: int | None = Field(default=None, description="Boş = material_name ile aranır")
    material_name: str = Field(default="S235")
    thickness_mm: float | None = Field(
        default=None, gt=0, description="Kabuk kalınlığı; boş = şablonun cidar kalınlığı (wall)"
    )
    speed_m_s: float = Field(default=10.0)
    angle_deg: float = Field(default=0.0)
    wall: CrashWall | None = Field(
        default=None,
        description="Rijit duvar; boş = şablondan: ön uç (x = 0) kesit merkezi, normal +x",
    )
    t_end_ms: float = Field(default=4.0, gt=0)
    model: CrashModelParams = Field(default_factory=lambda: CrashModelParams(law="plastic"))
    engine: CrashEngineParams = Field(default_factory=CrashEngineParams)
    th: CrashThParams = Field(default_factory=CrashThParams)
    sections: list[CrashSectionParams] = Field(default_factory=list)
    contacts: list[CrashContactParams] = Field(default_factory=list)
    added_masses: list[CrashMassParams] = Field(default_factory=list)
    rigid_bodies: list[CrashRigidBodyParams] = Field(
        default_factory=list,
        description="Ör. kızak: region 'kutu_arka' + mass_kg (değer mühendisin)",
    )
    boundary_conditions: list[CrashBcParams] = Field(default_factory=list)
    imposed_velocities: list[CrashImpVelParams] = Field(default_factory=list)
    filters: CrashFilterParams = Field(default_factory=CrashFilterParams)
    name: str | None = None
    run_solver: bool = True
    wait: bool = False

    @model_validator(mode="after")
    def _template_ok(self) -> "CrashScenarioRequest":
        if self.template_id not in CRASH_TEMPLATES:
            raise ValueError(
                f"Crash senaryosu yalnız {sorted(CRASH_TEMPLATES)} şablonlarıyla kurulur."
            )
        return self


def _resolved_geometry(req: CrashScenarioRequest) -> dict[str, Any]:
    """Şablon parametreleri varsayılanlarla birleşik, doğrulanmış (wall vb. buradan)."""
    model = get_template(req.template_id).params_model
    return model.model_validate(req.geometry).model_dump()


def _default_wall(template_id: str, g: dict[str, Any]) -> dict[str, Any]:
    # crash_box_shell: kutu x ekseninde, ön uç x = 0; nokta dış kesit merkezi.
    return {"point": (0.0, g["box_height"] / 2.0, g["box_width"] / 2.0), "normal": (1.0, 0.0, 0.0)}


def _material(db: Session, req: CrashScenarioRequest) -> Material:
    if req.material_id is not None:
        mat = db.get(Material, req.material_id)
    else:
        mat = db.query(Material).filter(Material.name == req.material_name).one_or_none()
    if mat is None:
        raise HTTPException(status_code=404, detail="Malzeme bulunamadı.")
    return mat


@router.post("/scenario")
def crash_scenario(
    req: CrashScenarioRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Şablon → mesh → malzeme → crash çözümü; crash_runs kaydı /crash/solve'dan."""
    try:
        g = _resolved_geometry(req)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=f"Şablon parametresi geçersiz: {exc}") from exc
    mat = _material(db, req)
    dimension = CRASH_TEMPLATES[req.template_id]

    try:
        geo, _regions, _tess = create_geometry_from_template(db, req.template_id, g)
    except Exception as exc:  # noqa: BLE001 — şablon kurulum hataları 422
        raise HTTPException(status_code=422, detail=f"Geometri kurulamadı: {exc}") from exc
    db.add(MaterialAssignment(geometry_id=geo.id, part_id=0, material_id=mat.id))
    db.commit()

    generate_mesh(
        geo.id,
        GenerateMeshRequest(
            element_size=req.element_size_mm, dimension=dimension, element_scheme=req.element_scheme
        ),
        db,
    )

    thickness = req.thickness_mm if req.thickness_mm is not None else float(g["wall"])
    wall = req.wall.model_dump() if req.wall is not None else _default_wall(req.template_id, g)
    solve = CrashSolveRequest(
        geometry_id=geo.id,
        dimension=dimension,
        run_solver=req.run_solver,
        wait=req.wait,
        t_end_ms=req.t_end_ms,
        name=req.name,
        barrier={"speed_m_s": req.speed_m_s, "angle_deg": req.angle_deg, "wall": wall},
        parts=[{"part_id": 0, "role": "moving", "thickness_mm": thickness}],
        model=req.model,
        engine=req.engine,
        th=req.th,
        sections=req.sections,
        contacts=req.contacts,
        added_masses=req.added_masses,
        rigid_bodies=req.rigid_bodies,
        boundary_conditions=req.boundary_conditions,
        imposed_velocities=req.imposed_velocities,
        filters=req.filters,
    )
    result = crash_solve(solve, background_tasks, db)
    logger.info(
        "Crash senaryo: template=%s geometry_id=%s run_id=%s", req.template_id, geo.id, result.get("run_id")
    )
    return {
        "geometry_id": geo.id,
        "scenario": {
            "template_id": req.template_id,
            "geometry": g,
            "element_size_mm": req.element_size_mm,
            "element_scheme": req.element_scheme,
            "material_id": mat.id,
            "material_name": mat.name,
            "thickness_mm": thickness,
            "wall": wall,
        },
        "crash": result,
    }
