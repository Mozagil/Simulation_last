"""Şablon: burulmaya maruz dairesel mil (τ = T r / J).

Eksen x = mil boyu. Serbest uç dış çemberine teğetsel CLOAD: T = F · R.
    J = π R⁴ / 2
    τ_max = T R / J
    σ_vm = √3 τ_max  (saf kayma)
    u_max = T L R / (G J)   G = E / (2(1+ν))
"""

from __future__ import annotations

import math

from pydantic import BaseModel, Field, model_validator

from app.templates.base import AnalyticInput, BBox, GeometryTemplate, Region, plane_at

REGION_FIXED = "ankastre_uc"
REGION_TORQUE = "yuk_burulma"


class TorsionShaftParams(BaseModel):
    """Tüm boyutlar mm."""

    length: float = Field(100.0, gt=0, description="Mil boyu L (x)", json_schema_extra={"unit": "mm", "symbol": "L"})
    radius: float = Field(10.0, gt=0, description="Yarıçap R", json_schema_extra={"unit": "mm", "symbol": "R"})

    @model_validator(mode="after")
    def _slender(self) -> "TorsionShaftParams":
        if self.length < 4.0 * self.radius:
            raise ValueError(
                f"length ({self.length}) en az 4 x radius ({self.radius}) olmalı "
                "(Saint-Venant; uç etkileri burulma teorisini bozar)."
            )
        return self


def polar_inertia(radius: float) -> float:
    return math.pi * radius**4 / 2.0


def _free_end_circle(bbox: BBox, params: BaseModel, tol: float = 0.15) -> bool:
    xmin, ymin, zmin, xmax, ymax, zmax = bbox
    length = float(getattr(params, "length"))
    rad = float(getattr(params, "radius"))
    if abs(xmin - length) > 1e-3 or abs(xmax - length) > 1e-3:
        return False
    dy, dz = ymax - ymin, zmax - zmin
    return abs(dy - 2.0 * rad) < rad * tol + 0.2 and abs(dz - 2.0 * rad) < rad * tol + 0.2


def _build(p: TorsionShaftParams) -> None:
    import gmsh

    gmsh.model.occ.addCylinder(0.0, 0.0, 0.0, p.length, 0.0, 0.0, p.radius)


def _analytic(p: TorsionShaftParams, a: AnalyticInput) -> dict[str, float]:
    """T = F·R [N·mm]; τ [MPa]; u [mm]."""
    torque = a.force_n * p.radius
    polar = polar_inertia(p.radius)
    tau = torque * p.radius / polar
    vm = math.sqrt(3.0) * tau
    shear_mod = a.youngs_modulus_pa / 1e6 / (2.0 * (1.0 + a.poisson_ratio))
    tip_u = torque * p.length * p.radius / (shear_mod * polar)
    return {"max_displacement": tip_u, "max_von_mises": vm}


TORSION_SHAFT = GeometryTemplate(
    id="torsion_shaft",
    name="Burulma mili (dairesel kesit)",
    description=(
        "Bir ucu ankastre dairesel mil. Serbest uç dış çemberine teğetsel CLOAD; "
        "T = F·R, τ = TR/J, von Mises = √3 τ."
    ),
    params_model=TorsionShaftParams,
    build=_build,
    regions=(
        Region(
            name=REGION_FIXED,
            description="Ankastre uç (x=0)",
            select=plane_at("x", 0.0),
            expected_faces=1,
        ),
        Region(
            name=REGION_TORQUE,
            description="Serbest uç dış çemberi (x=L) — teğetsel CLOAD, T=F·R",
            select=_free_end_circle,
            dim=1,
            expected_faces=1,
        ),
    ),
    analytic=_analytic,
    default_bcs=(
        {"type": "fixed", "region": REGION_FIXED},
        # NOT: CLOAD tek yönlü vektördür; çember üzerinde gerçek teğetsel dağılım
        # (tork) için solver'da tork BC'si gerekir (bkz. ROADMAP 0.4.7). Şimdilik
        # analitik tablonun varsaydığı büyüklük (T = F·R) ile başlangıç değeri.
        {"type": "cload", "region": REGION_TORQUE, "fx": 0.0, "fy": 0.0, "fz": 500.0},
    ),
    tags=("grup1", "analitik", "burulma"),
)
