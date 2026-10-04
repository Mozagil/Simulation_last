"""Şablon: Hopkinson (SHPB) çubuğu — çarpıcı + giriş çubuğu, solid (Faz 1, K9).

Parça 0 (önce kurulur): giriş çubuğu, Ø D, x ∈ [0, Li]. Parça 1: çarpıcı
çubuk, Ø D, x ∈ [−g − Ls, −g]. Eksen x. Crash'te çarpıcı +x ile v0'da gelir,
giriş çubuğu serbest (BC yok); çarpıcı → giriş TYPE7.

Referans (1B elastik dalga, aynı malzeme / çap): giriş çubuğunda gerilme
σ = ρ·c·v0/2, kuvvet σ·A, darbe süresi 2·Ls/c, c = √(E/ρ). Kuvvet x = Li/4
kesitinden (yansıma dönmeden önce). Bölgeler: giris_on (x = 0), giris_arka,
carpici_on (x = −g).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.templates.base import GeometryTemplate, Region, plane_at

REGION_BAR_FRONT = "giris_on"
REGION_BAR_BACK = "giris_arka"
REGION_STRIKER_FRONT = "carpici_on"


class HopkinsonBarParams(BaseModel):
    """Tüm boyutlar mm."""

    diameter: float = Field(20.0, gt=0, description="Çubuk çapı D", json_schema_extra={"unit": "mm", "symbol": "D"})
    striker_length: float = Field(100.0, gt=0, description="Çarpıcı boyu Ls", json_schema_extra={"unit": "mm", "symbol": "Ls"})
    bar_length: float = Field(500.0, gt=0, description="Giriş çubuğu boyu Li", json_schema_extra={"unit": "mm", "symbol": "Li"})
    gap: float = Field(0.5, ge=0, description="Çarpıcı – giriş çubuğu boşluğu g", json_schema_extra={"unit": "mm", "symbol": "g"})


def _build(p: HopkinsonBarParams) -> None:
    import gmsh

    r = p.diameter / 2.0
    gmsh.model.occ.addCylinder(0.0, 0.0, 0.0, p.bar_length, 0.0, 0.0, r)
    gmsh.model.occ.addCylinder(-p.gap - p.striker_length, 0.0, 0.0, p.striker_length, 0.0, 0.0, r)


HOPKINSON_BAR = GeometryTemplate(
    id="hopkinson_bar",
    name="Hopkinson çubuğu — çarpıcı + giriş çubuğu (solid)",
    description=(
        "Çarpıcı çubuk (Ls) giriş çubuğuna (Li) v0 ile çarpar; 1B elastik dalga referansı "
        "σ = ρ·c·v0/2, süre 2·Ls/c. İki solid parça (0 giriş, 1 çarpıcı)."
    ),
    params_model=HopkinsonBarParams,
    build=_build,
    regions=(
        Region(name=REGION_BAR_FRONT, description="Giriş çubuğu ön yüzü (x = 0)", select=plane_at("x", 0.0), dim=2,
               expected_faces=1),
        Region(name=REGION_BAR_BACK, description="Giriş çubuğu arka yüzü (x = Li)", select=plane_at("x", lambda p: p.bar_length),
               dim=2, expected_faces=1),
        Region(name=REGION_STRIKER_FRONT, description="Çarpıcı ön yüzü (x = −g)", select=plane_at("x", lambda p: -p.gap),
               dim=2, expected_faces=1),
    ),
    analytic=None,
    characteristic_length=lambda p: p.diameter,
    default_element_ratio=(0.15, 0.25),
    default_bcs=(
        {"type": "fixed", "region": REGION_BAR_BACK},
        {"type": "pressure", "region": REGION_STRIKER_FRONT, "magnitude": 1.0},
    ),
    tags=("crash", "solid", "dalga"),
)
