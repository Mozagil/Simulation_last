"""Şablon: eşit L-köşebent, ankastre (Grup 2)."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from app.templates.base import AnalyticInput, GeometryTemplate, Region, plane_at
from app.templates.beam_section import cantilever_fl_over_ei, equal_l_angle_inertia_and_c

REGION_FIXED = "ankastre_uc"
REGION_LOAD = "yuk_yuzeyi"


class LAngleParams(BaseModel):
    """Tüm boyutlar mm. Eşit bacak: y ve z doğrultusunda `leg`."""

    length: float = Field(400.0, gt=0, description="Boy L (x)", json_schema_extra={"unit": "mm", "symbol": "L"})
    leg: float = Field(40.0, gt=0, description="Bacak uzunluğu a (y ve z)", json_schema_extra={"unit": "mm", "symbol": "a"})
    thickness: float = Field(5.0, gt=0, description="Kalınlık t", json_schema_extra={"unit": "mm", "symbol": "t"})

    @model_validator(mode="after")
    def _angle(self) -> "LAngleParams":
        if self.leg <= self.thickness:
            raise ValueError("leg, thickness değerinden büyük olmalı.")
        if self.length < 5.0 * self.leg:
            raise ValueError(
                f"length ({self.length}) en az 5 × leg ({self.leg}) olmalı (kiriş teorisi)."
            )
        return self


def _build(p: LAngleParams) -> None:
    import gmsh

    vert = gmsh.model.occ.addBox(0.0, 0.0, 0.0, p.length, p.leg, p.thickness)
    horiz = gmsh.model.occ.addBox(0.0, 0.0, 0.0, p.length, p.thickness, p.leg)
    gmsh.model.occ.fuse([(3, vert)], [(3, horiz)])


def _analytic(p: LAngleParams, a: AnalyticInput) -> dict[str, float]:
    inertia, c = equal_l_angle_inertia_and_c(p.leg, p.thickness)
    return cantilever_fl_over_ei(p.length, inertia, c, a.force_n, a.youngs_modulus_pa)


L_ANGLE = GeometryTemplate(
    id="l_angle",
    name="L-köşebent (ankastre)",
    description="Eşit bacaklı L profil, ankastre uç yükü −y. I ve c kesit ağırlık merkezine göre.",
    params_model=LAngleParams,
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
    # Karakteristik uzunluk: kanat kalınlığı.
    characteristic_length=lambda p: p.thickness,
    default_element_ratio=(0.5, 1.2),
    default_bcs=(
        {"type": "fixed", "region": REGION_FIXED},
        {"type": "cload", "region": REGION_LOAD, "fx": 0.0, "fy": -500.0, "fz": 0.0},
    ),
    tags=("grup2", "analitik", "egilme", "profil"),
)
