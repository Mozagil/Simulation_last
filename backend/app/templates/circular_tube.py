"""Şablon: dairesel tüp, ankastre eğilme (Grup 2).

Kalın cidarlı borudan farkı: iç basınç değil, uç eğilme. I = π/4 (R⁴−r⁴).
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from app.templates.base import AnalyticInput, GeometryTemplate, Region, plane_at
from app.templates.beam_section import cantilever_fl_over_ei, circular_tube_inertia

REGION_FIXED = "ankastre_uc"
REGION_LOAD = "yuk_yuzeyi"


class CircularTubeParams(BaseModel):
    """Tüm boyutlar mm. Silindir ekseni x; merkez y=z=0."""

    length: float = Field(400.0, gt=0, description="Boy L (x)", json_schema_extra={"unit": "mm", "symbol": "L"})
    outer_radius: float = Field(20.0, gt=0, description="Dış yarıçap R", json_schema_extra={"unit": "mm", "symbol": "R"})
    inner_radius: float = Field(16.0, gt=0, description="İç yarıçap r", json_schema_extra={"unit": "mm", "symbol": "r"})

    @model_validator(mode="after")
    def _tube(self) -> "CircularTubeParams":
        if self.outer_radius <= self.inner_radius:
            raise ValueError("outer_radius inner_radius değerinden büyük olmalı.")
        if self.length < 5.0 * (2.0 * self.outer_radius):
            raise ValueError(
                f"length ({self.length}) en az 5 × dış çap ({2 * self.outer_radius}) olmalı."
            )
        return self


def _build(p: CircularTubeParams) -> None:
    import gmsh

    outer = gmsh.model.occ.addCylinder(0.0, 0.0, 0.0, p.length, 0.0, 0.0, p.outer_radius)
    inner = gmsh.model.occ.addCylinder(0.0, 0.0, 0.0, p.length, 0.0, 0.0, p.inner_radius)
    gmsh.model.occ.cut([(3, outer)], [(3, inner)])


def _analytic(p: CircularTubeParams, a: AnalyticInput) -> dict[str, float]:
    inertia = circular_tube_inertia(p.outer_radius, p.inner_radius)
    return cantilever_fl_over_ei(
        p.length, inertia, p.outer_radius, a.force_n, a.youngs_modulus_pa
    )


CIRCULAR_TUBE = GeometryTemplate(
    id="circular_tube",
    name="Dairesel tüp (ankastre eğilme)",
    description="İçi boş dairesel boru, ankastre uç yükü −y. I = π/4 (R⁴ − r⁴).",
    params_model=CircularTubeParams,
    build=_build,
    regions=(
        Region(name=REGION_FIXED, description="Ankastre uç (x=0)", select=plane_at("x", 0.0)),
        Region(
            name=REGION_LOAD,
            description="Serbest uç (x=L) — CLOAD −y",
            select=plane_at("x", lambda p: p.length),
        ),
    ),
    analytic=_analytic,
    default_bcs=(
        {"type": "fixed", "region": REGION_FIXED},
        {"type": "cload", "region": REGION_LOAD, "fx": 0.0, "fy": -1000.0, "fz": 0.0},
    ),
    tags=("grup2", "analitik", "egilme", "profil"),
)
