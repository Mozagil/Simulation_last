"""Şablon: kutu profil / dikdörtgen tüp, ankastre (Grup 2)."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from app.templates.base import AnalyticInput, GeometryTemplate, Region, plane_at
from app.templates.beam_section import box_tube_inertia, cantilever_fl_over_ei

REGION_FIXED = "ankastre_uc"
REGION_LOAD = "yuk_yuzeyi"


class BoxTubeParams(BaseModel):
    """Tüm boyutlar mm. height = y (yük), width = z."""

    length: float = Field(500.0, gt=0, description="Uzunluk L (x)", json_schema_extra={"unit": "mm"})
    height: float = Field(60.0, gt=0, description="Dış yükseklik h (y)", json_schema_extra={"unit": "mm"})
    width: float = Field(40.0, gt=0, description="Dış genişlik b (z)", json_schema_extra={"unit": "mm"})
    wall: float = Field(4.0, gt=0, description="Cidar kalınlığı t", json_schema_extra={"unit": "mm"})

    @model_validator(mode="after")
    def _hollow(self) -> "BoxTubeParams":
        if self.height <= 2.0 * self.wall or self.width <= 2.0 * self.wall:
            raise ValueError("height ve width, 2 × wall değerinden büyük olmalı.")
        if self.length < 5.0 * self.height:
            raise ValueError(
                f"length ({self.length}) en az 5 × height ({self.height}) olmalı (kiriş teorisi)."
            )
        return self


def _build(p: BoxTubeParams) -> None:
    import gmsh

    outer = gmsh.model.occ.addBox(0.0, 0.0, 0.0, p.length, p.height, p.width)
    inner = gmsh.model.occ.addBox(
        -1.0,
        p.wall,
        p.wall,
        p.length + 2.0,
        p.height - 2.0 * p.wall,
        p.width - 2.0 * p.wall,
    )
    gmsh.model.occ.cut([(3, outer)], [(3, inner)])


def _analytic(p: BoxTubeParams, a: AnalyticInput) -> dict[str, float]:
    inertia = box_tube_inertia(p.height, p.width, p.wall)
    return cantilever_fl_over_ei(
        p.length, inertia, p.height / 2.0, a.force_n, a.youngs_modulus_pa
    )


BOX_TUBE = GeometryTemplate(
    id="box_tube",
    name="Kutu profil (ankastre)",
    description="Dikdörtgen içi boş profil, ankastre uç yükü. I = (b h³ − bi hi³)/12.",
    params_model=BoxTubeParams,
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
