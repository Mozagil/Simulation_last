"""Şablon: I-kesit ankastre kiriş (Grup 2).

Eksen: x = L, y = kesit yüksekliği h (yük −y), z = flanş genişliği b.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from app.templates.base import AnalyticInput, GeometryTemplate, Region, plane_at
from app.templates.beam_section import cantilever_fl_over_ei, i_beam_inertia

REGION_FIXED = "ankastre_uc"
REGION_LOAD = "yuk_yuzeyi"


class IBeamParams(BaseModel):
    """Tüm boyutlar mm."""

    length: float = Field(500.0, gt=0, description="Kiriş uzunluğu L (x)", json_schema_extra={"unit": "mm", "symbol": "L"})
    height: float = Field(80.0, gt=0, description="Kesit yüksekliği h (y)", json_schema_extra={"unit": "mm", "symbol": "h"})
    flange_width: float = Field(50.0, gt=0, description="Flanş genişliği b (z)", json_schema_extra={"unit": "mm", "symbol": "b"})
    web: float = Field(6.0, gt=0, description="Gövde kalınlığı tw", json_schema_extra={"unit": "mm", "symbol": "tw"})
    flange: float = Field(8.0, gt=0, description="Flanş kalınlığı tf", json_schema_extra={"unit": "mm", "symbol": "tf"})

    @model_validator(mode="after")
    def _section(self) -> "IBeamParams":
        if self.height <= 2.0 * self.flange:
            raise ValueError("height, 2 × flange (tf) değerinden büyük olmalı.")
        if self.flange_width <= self.web:
            raise ValueError("flange_width, web (tw) değerinden büyük olmalı.")
        if self.length < 5.0 * self.height:
            raise ValueError(
                f"length ({self.length}) en az 5 × height ({self.height}) olmalı "
                "(kiriş teorisi)."
            )
        return self


def _build(p: IBeamParams) -> None:
    import gmsh

    bot = gmsh.model.occ.addBox(0.0, 0.0, 0.0, p.length, p.flange, p.flange_width)
    web_y0 = p.flange
    web_h = p.height - 2.0 * p.flange
    z0 = (p.flange_width - p.web) / 2.0
    web = gmsh.model.occ.addBox(0.0, web_y0, z0, p.length, web_h, p.web)
    top = gmsh.model.occ.addBox(
        0.0, p.height - p.flange, 0.0, p.length, p.flange, p.flange_width
    )
    gmsh.model.occ.fuse([(3, bot)], [(3, web), (3, top)])


def _analytic(p: IBeamParams, a: AnalyticInput) -> dict[str, float]:
    inertia = i_beam_inertia(p.height, p.flange_width, p.web, p.flange)
    return cantilever_fl_over_ei(
        p.length, inertia, p.height / 2.0, a.force_n, a.youngs_modulus_pa
    )


I_BEAM = GeometryTemplate(
    id="i_beam",
    name="I-kesit kiriş (ankastre)",
    description=(
        "I-profil ankastre kiriş, uçtan −y yük. Euler-Bernoulli: I = (b h³ − (b−tw)(h−2tf)³)/12."
    ),
    params_model=IBeamParams,
    build=_build,
    regions=(
        Region(
            name=REGION_FIXED,
            description="Ankastre uç (x=0)",
            select=plane_at("x", 0.0),
        ),
        Region(
            name=REGION_LOAD,
            description="Serbest uç (x=L) — CLOAD −y",
            select=plane_at("x", lambda p: p.length),
        ),
    ),
    analytic=_analytic,
    # Karakteristik uzunluk: en ince cidar (gövde/başlık).
    characteristic_length=lambda p: min(p.web, p.flange),
    default_element_ratio=(0.5, 1.2),
    default_bcs=(
        {"type": "fixed", "region": REGION_FIXED},
        {"type": "cload", "region": REGION_LOAD, "fx": 0.0, "fy": -2000.0, "fz": 0.0},
    ),
    tags=("grup2", "analitik", "egilme", "profil"),
)
