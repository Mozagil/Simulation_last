"""Şablon: direk yan çarpması kirişi — kabuk dikdörtgen tüp (Faz 1, K3).

Yan kiriş / kapı eşiği temsili: orta yüzey dikdörtgen tüp, ekseni y (boy L),
kesit derinliği h çarpma yönünde (x), genişlik b (z), cidar t. Orta yüzey
x ∈ [t/2, h − t/2], z ∈ [t/2, b − t/2]; dış ön yüz x = 0. Uçlar açık.

Crash'te direk /RWALL/CYL (eksen z, çap D — senaryo girdisi), ön yüzden g
boşlukla x < 0'da, kiriş ortasında (y = L/2). İki uç halkası rijit gövde
(araç kütlesi temsili, kütle senaryo girdisi), kiriş −x ile gelir.
Referans (veri): üç nokta eğilme plastik çökme yükü P = 4·Mp/L, Mp = σy·Zp,
ince cidarlı kutu Zp ≈ t·(h'·b' + h'²/2) (orta yüzey ölçüleri).

Bölgeler: uc_1 (y = 0 halkası), uc_2 (y = L halkası), on_yuz (x = t/2 yüzü).
Varsayılan BC'ler yalnız durability akışı için (uçlar sabit, ön yüze basınç).
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from app.templates.base import GeometryTemplate, Region, plane_at

REGION_END_1 = "uc_1"
REGION_END_2 = "uc_2"
REGION_FRONT = "on_yuz"


class PoleBeamShellParams(BaseModel):
    """Tüm boyutlar mm."""

    length: float = Field(800.0, gt=0, description="Kiriş boyu L (y)", json_schema_extra={"unit": "mm", "symbol": "L"})
    depth: float = Field(60.0, gt=0, description="Kesit derinliği h (x, çarpma yönü)", json_schema_extra={"unit": "mm", "symbol": "h"})
    width: float = Field(40.0, gt=0, description="Kesit genişliği b (z)", json_schema_extra={"unit": "mm", "symbol": "b"})
    wall: float = Field(2.0, gt=0, description="Cidar kalınlığı t (kabuk kalınlığı)", json_schema_extra={"unit": "mm", "symbol": "t"})
    gap: float = Field(1.0, ge=0, description="Ön yüz – direk boşluğu g", json_schema_extra={"unit": "mm", "symbol": "g"})

    @model_validator(mode="after")
    def _ok(self) -> "PoleBeamShellParams":
        if self.depth <= 2.0 * self.wall or self.width <= 2.0 * self.wall:
            raise ValueError("depth ve width, 2 × wall değerinden büyük olmalı.")
        if self.length < 4.0 * self.depth:
            raise ValueError(f"length ({self.length}) en az 4 × depth olmalı (kiriş).")
        return self

    @property
    def mid_depth(self) -> float:
        return self.depth - self.wall

    @property
    def mid_width(self) -> float:
        return self.width - self.wall


def plastic_modulus_mm3(p: PoleBeamShellParams) -> float:
    """İnce cidarlı kutu, z ekseni çevresinde eğilme (x yönünde yük): Zp ≈ t·(h'·b' + h'²/2)."""
    h, b = p.mid_depth, p.mid_width
    return p.wall * (h * b + h * h / 2.0)


def _build(p: PoleBeamShellParams) -> None:
    import gmsh

    occ = gmsh.model.occ
    h2 = p.wall / 2.0
    corners = ((h2, h2), (p.depth - h2, h2), (p.depth - h2, p.width - h2), (h2, p.width - h2))
    pts = [occ.addPoint(x, 0.0, z) for x, z in corners]
    lines = [occ.addLine(pts[i], pts[(i + 1) % 4]) for i in range(4)]
    occ.extrude([(1, ln) for ln in lines], 0.0, p.length, 0.0)


POLE_BEAM_SHELL = GeometryTemplate(
    id="pole_beam_shell",
    name="Direk yan çarpması — kabuk kiriş (dikdörtgen tüp)",
    description=(
        "Yan kiriş temsili açık uçlu dikdörtgen tüp (orta yüzey), ekseni y; crash'te silindirik "
        "rijit direk (/RWALL/CYL, eksen z) ortadan, uç halkaları rijit gövde + kütle. "
        "Referans üç nokta eğilme P = 4·Mp/L."
    ),
    params_model=PoleBeamShellParams,
    build=_build,
    regions=(
        Region(name=REGION_END_1, description="y = 0 uç halkası", select=plane_at("y", 0.0), dim=1, expected_faces=4),
        Region(name=REGION_END_2, description="y = L uç halkası", select=plane_at("y", lambda p: p.length), dim=1,
               expected_faces=4),
        Region(name=REGION_FRONT, description="Ön yüz (x = t/2, direğe bakan)", select=plane_at("x", lambda p: p.wall / 2.0),
               dim=2, expected_faces=1),
    ),
    analytic=None,
    characteristic_length=lambda p: min(p.mid_depth, p.mid_width),
    default_element_ratio=(0.1, 0.25),
    default_bcs=(
        {"type": "fixed", "region": REGION_END_1},
        {"type": "fixed", "region": REGION_END_2},
        {"type": "pressure", "region": REGION_FRONT, "magnitude": 0.1},
    ),
    tags=("crash", "kabuk", "yan_carpma"),
    surface_only=True,
)
