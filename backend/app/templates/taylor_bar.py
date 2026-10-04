"""Şablon: Taylor çubuğu — rijit duvara çarpan dolu silindir (Faz 1, K1).

Dolu silindir, ekseni x; çarpma yüzü x = 0, arka yüz x = L0. Tek solid parça
(3D mesh). Crash senaryosunda rijit duvar x = 0 düzlemi (normal +x), çubuk
−x yönünde v0 ile gelir (1.17a duvar deseni).

Referans (veri; kabul kriteri yok): Taylor (1948) tek boyutlu rijit-plastik
kuram; Wilkins & Guinan (1973) yaklaşığı L1/L0 ≈ exp(−ρ·v0²/(2·σ0)) (h = 0).
Bölgeler: on_yuz (x = 0), arka_yuz (x = L0), yan (silindirik yüzey).
Varsayılan BC'ler yalnız durability akışı için (arka yüz sabit, ön yüze
basınç).
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from app.templates.base import GeometryTemplate, Region, plane_at

REGION_FRONT = "on_yuz"
REGION_BACK = "arka_yuz"
REGION_SIDE = "yan"

_TOL = 1e-6


class TaylorBarParams(BaseModel):
    """Tüm boyutlar mm."""

    length: float = Field(50.0, gt=0, description="Çubuk boyu L0 (x)", json_schema_extra={"unit": "mm", "symbol": "L0"})
    diameter: float = Field(10.0, gt=0, description="Çubuk çapı D0", json_schema_extra={"unit": "mm", "symbol": "D0"})

    @model_validator(mode="after")
    def _ok(self) -> "TaylorBarParams":
        if self.length < self.diameter:
            raise ValueError(f"length ({self.length}) en az diameter ({self.diameter}) olmalı.")
        return self


def _build(p: TaylorBarParams) -> None:
    import gmsh

    gmsh.model.occ.addCylinder(0.0, 0.0, 0.0, p.length, 0.0, 0.0, p.diameter / 2.0)


def _side(bbox, p: BaseModel) -> bool:
    x0, _y0, _z0, x1, _y1, _z1 = bbox
    return (x1 - x0) > _TOL


TAYLOR_BAR = GeometryTemplate(
    id="taylor_bar",
    name="Taylor çubuğu — dolu silindir (solid)",
    description=(
        "Rijit duvara (x = 0) çarpan dolu silindir; tek solid parça, 3D mesh. Referans "
        "Taylor (1948) / Wilkins–Guinan (1973): son boy L1/L0 ≈ exp(−ρ·v0²/(2·σ0))."
    ),
    params_model=TaylorBarParams,
    build=_build,
    regions=(
        Region(name=REGION_FRONT, description="Çarpma yüzü (x = 0)", select=plane_at("x", 0.0), dim=2, expected_faces=1),
        Region(name=REGION_BACK, description="Arka yüz (x = L0)", select=plane_at("x", lambda p: p.length), dim=2,
               expected_faces=1),
        Region(name=REGION_SIDE, description="Silindirik yan yüzey", select=_side, dim=2, expected_faces=1),
    ),
    analytic=None,
    characteristic_length=lambda p: p.diameter,
    default_element_ratio=(0.1, 0.2),
    default_bcs=(
        {"type": "fixed", "region": REGION_BACK},
        {"type": "pressure", "region": REGION_FRONT, "magnitude": 10.0},
    ),
    tags=("crash", "solid", "darbe"),
)
