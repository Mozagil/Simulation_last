"""Roket analitik referansı ve rüzgâr tüneli koşusu — Faz 2, R2 + R3.

POST /cfd/rocket/barrowman  {params | geometry_id, cg_mm?} → bileşen tablosu + toplam
POST /cfd/rocket/solve      {mesh_id, hız, α, CG, akışkan…} → /cfd/solve (serbest akım
                            sınırları, gövde kuvvetleri) + koşu sonunda CN, CA, CD, CL,
                            Cm, x_cp, kararlılık payı ve Barrowman ile yan yana

``geometry_id`` verilirse roket şablonundan üretilmiş geometrinin kayıtlı
parametreleri kullanılır. Sonuçlar veridir; yorum / öneri yok.
"""

from __future__ import annotations

import math
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from pydantic import BaseModel, Field, ValidationError, model_validator
from sqlalchemy.orm import Session

from app.api.cfd import CfdSolveRequest, RocketRun, auto_visualization, cfd_solve
from app.api.cfd_mesh import read_mesh_meta
from app.api.geometry import _get_geometry_or_404
from app.db.session import get_db
from app.mesh.cfd_mesher import TUNNEL_PATCHES
from app.postprocess.barrowman import barrowman
from app.postprocess.rocket_aero import freestream, speed_of_sound
from app.templates.rocket import RocketParams

router = APIRouter(prefix="/cfd/rocket", tags=["cfd"])


class BarrowmanRequest(BaseModel):
    #: Roket şablonu parametreleri (mm) — ya bu ya geometry_id.
    params: dict[str, Any] | None = None
    geometry_id: int | None = None
    #: Ağırlık merkezi, burun ucundan (mm) — verilirse kararlılık payı (kalibre).
    cg_mm: float | None = Field(None, ge=0)

    @model_validator(mode="after")
    def _one(self) -> "BarrowmanRequest":
        if (self.params is None) == (self.geometry_id is None):
            raise ValueError("'params' ya da 'geometry_id' alanlarından tam biri verilmeli.")
        return self


@router.post("/barrowman")
def rocket_barrowman(body: BarrowmanRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    raw = body.params
    if body.geometry_id is not None:
        geo = _get_geometry_or_404(db, body.geometry_id)
        if geo.template_id != "rocket":
            raise HTTPException(status_code=422, detail="Geometri roket şablonundan üretilmemiş.")
        raw = geo.template_params or {}
    try:
        params = RocketParams.model_validate(raw or {})
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"params": params.model_dump(), **barrowman(params, body.cg_mm)}


class RocketSolveRequest(BaseModel):
    """Roket rüzgâr tüneli koşusu. Değerler mühendisin; varsayılan akışkan ISA deniz seviyesi havası."""

    mesh_id: str
    speed_m_s: float = Field(gt=0)
    alpha_deg: float = Field(0.0, ge=-30, le=30)
    #: Ağırlık merkezi, burun ucundan (mm). Verilmezse moment burun ucuna göre alınır.
    cg_mm: float | None = Field(None, ge=0)
    rho_kg_m3: float = Field(1.225, gt=0)
    nu_m2_s: float = Field(1.46e-5, gt=0)
    #: Mach sayısı için (veri): a = √(γ·R·T)
    temperature_k: float = Field(288.15, gt=0)
    turbulence_model: Literal["laminar", "kOmegaSST"] = "kOmegaSST"
    #: R4: çözücü seçimi (NLGEOM gibi; otomatik değil). Sıkıştırılabilirde serbest akım
    #: yoğunluğu ρ = p/(R·T)'den türetilir (rho_kg_m3 yok sayılır), basınç p_inf_pa.
    solver: Literal["simpleFoam", "rhoSimpleFoam", "rhoCentralFoam"] = "simpleFoam"
    p_inf_pa: float = Field(101325.0, gt=0)
    transonic: bool = False
    max_co: float = Field(0.5, gt=0)
    #: Paralel koşu (R4b) çekirdek sayısı
    n_procs: int = Field(1, ge=1, le=64)
    turbulence_intensity: float = Field(0.01, gt=0, le=1)
    iterations: int = Field(1000, gt=0)
    average_last: int = Field(100, gt=0)
    #: SIMPLE gevşetme katsayıları (mühendis ayarı; varsayılan pitzDaily 0.9 / 0.9).
    relax_u: float = Field(0.9, gt=0, le=1)
    relax_other: float = Field(0.9, gt=0, le=1)
    #: Yakınsama hedefi (ilk residual); varsayılan case yazıcınınki (p 1e-2, U 1e-3).
    residual_p: float = Field(1e-2, gt=0)
    residual_u: float = Field(1e-3, gt=0)
    name: str | None = Field(None, max_length=200)
    wait: bool = False


@router.post("/solve")
def rocket_solve(body: RocketSolveRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)) -> dict[str, Any]:
    mesh = read_mesh_meta(body.mesh_id)
    if mesh is None or mesh.get("status") != "meshed":
        raise HTTPException(status_code=422, detail=f"Mesh hazır değil ya da yok: {body.mesh_id}")
    geo = _get_geometry_or_404(db, int(mesh["geometry_id"]))
    if geo.template_id != "rocket":
        raise HTTPException(status_code=422, detail="Mesh roket şablonundan üretilmiş bir geometriye ait değil.")
    params = RocketParams.model_validate(geo.template_params or {})
    patches = list(mesh.get("patches") or [])
    if "ground" in patches:
        raise HTTPException(status_code=422, detail="Roket tünelinde zemin (ground) olmamalı.")
    body_patches = [n for n in patches if n not in TUNNEL_PATCHES]
    d_m = params.body_diameter / 1000.0
    x_ref = (body.cg_mm or 0.0) / 1000.0
    u_inf = freestream(body.speed_m_s, body.alpha_deg)
    a = math.radians(body.alpha_deg)
    mach = body.speed_m_s / speed_of_sound(body.temperature_k)
    b = barrowman(params, body.cg_mm)
    rho = body.rho_kg_m3
    if body.solver != "simpleFoam":
        rho = body.p_inf_pa / (8314.46 / 28.96 * body.temperature_k)
    case = {
        "nu_m2_s": body.nu_m2_s,
        "rho_kg_m3": rho,
        "solver": body.solver,
        "compressible": {
            "p_inf_pa": body.p_inf_pa,
            "t_inf_k": body.temperature_k,
            "transonic": body.transonic,
            "max_co": body.max_co,
        },
        "patches": [
            *({"name": n, "kind": "farfield", "velocity_m_s": list(u_inf)} for n in ("inlet", "outlet", "sides")),
            *({"name": n, "kind": "wall"} for n in body_patches),
        ],
        "turbulence": {"model": body.turbulence_model, "intensity": body.turbulence_intensity, "length_scale_m": 0.1 * d_m},
        "initial_velocity_m_s": list(u_inf),
        "visualization": auto_visualization(mesh, body_patches),
        "control": {
            "iterations": body.iterations,
            "write_interval": body.iterations,
            "relax_u": body.relax_u,
            "relax_other": body.relax_other,
            "residual_p": body.residual_p,
            "residual_u": body.residual_u,
            "residual_turbulence": body.residual_u,
            "n_procs": body.n_procs,
        },
        "forces": {
            "patches": body_patches,
            "cofr_m": [x_ref, 0.0, 0.0],
            "drag_dir": [math.cos(a), 0.0, math.sin(a)],
            "lift_dir": [-math.sin(a), 0.0, math.cos(a)],
            "pitch_axis": [0.0, 1.0, 0.0],
            "u_ref_m_s": body.speed_m_s,
            "l_ref_m": d_m,
            "a_ref_m2": math.pi * d_m * d_m / 4.0,
            "average_last": body.average_last,
        },
    }
    req = CfdSolveRequest(
        case=case,
        name=body.name,
        geometry_id=geo.id,
        mesh_id=body.mesh_id,
        wait=body.wait,
        rocket=RocketRun(
            speed_m_s=body.speed_m_s,
            alpha_deg=body.alpha_deg,
            diameter_m=d_m,
            x_ref_m=x_ref,
            cg_given=body.cg_mm is not None,
            mach=mach,
            barrowman={"cn_alpha": b["cn_alpha"], "x_cp_mm": b["x_cp_mm"]},
        ),
    )
    out = cfd_solve(req, background_tasks, db)
    return {**out, "mach": mach, "barrowman": b}


@router.post("/ork")
async def rocket_ork(file: UploadFile) -> dict[str, Any]:
    """R6: OpenRocket .ork → R1 şablon parametreleri (mm) + eşlenemeyenler notu.

    Geometri üretmez; değerler şablon formuna dolar, mühendis düzenleyip üretir.
    """
    from app.templates.rocket_ork import OrkError, ork_to_params, read_ork_xml

    data = await file.read(5 * 1024 * 1024 + 1)
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail=".ork 5 MB'tan büyük.")
    try:
        out = ork_to_params(read_ork_xml(data))
    except OrkError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    try:
        RocketParams.model_validate(out["params"])
        out["valid"] = True
    except ValidationError as e:
        out["valid"] = False
        out["notes"].append("Şablon doğrulaması: " + "; ".join(err["msg"] for err in e.errors()))
    return out
