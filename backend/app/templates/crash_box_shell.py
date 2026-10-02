"""Şablon: kabuk crash box — orta yüzey tüp (Faz 1, 1.13b).

`crash_box_plate` kutusunun kabuk karşılığı: aynı dış ölçüler (L, h, b) ve
cidar t; geometri cidarın ORTA yüzeyidir. Kesit (h−t)×(b−t), x ∈ [0, L],
uçlar açık; dört yüzey kenar paylaşır (uyumlu mesh, tek kabuk parçası).
Hacim yok (`surface_only`): 2D (kabuk) mesh ve OpenRadioss /SHELL içindir.

Kütle solid kutuyla birebir aynı: L·t·2(h+b−2t). t geometride yalnız orta
yüzeyin konumunu belirler; kabuk kalınlığı crash çözümünde parça kalınlığı
olarak ayrıca girilir (`parts[].thickness_mm`).

Koordinatlar solid şablonla aynı çerçevede: orta yüzey y ∈ [t/2, h−t/2],
z ∈ [t/2, b−t/2]. Bölgeler KENAR (dim 1): ön ve arka uç halkaları.
Analitik yok; varsayılan BC'ler durability akışı için (arka uç sabit, ön
uçta −x basma).
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from app.templates.base import GeometryTemplate, Region, plane_at

REGION_BOX_FRONT = "kutu_on"
REGION_BOX_BACK = "kutu_arka"


class CrashBoxShellParams(BaseModel):
    """Tüm boyutlar mm."""

    box_length: float = Field(300.0, gt=0, description="Kutu uzunluğu L (x)", json_schema_extra={"unit": "mm", "symbol": "L"})
    box_height: float = Field(50.0, gt=0, description="Kutu dış yüksekliği h (y)", json_schema_extra={"unit": "mm", "symbol": "h"})
    box_width: float = Field(40.0, gt=0, description="Kutu dış genişliği b (z)", json_schema_extra={"unit": "mm", "symbol": "b"})
    wall: float = Field(3.0, gt=0, description="Cidar kalınlığı t (orta yüzey konumu; kabuk kalınlığı)", json_schema_extra={"unit": "mm", "symbol": "t"})

    @model_validator(mode="after")
    def _geometry_ok(self) -> "CrashBoxShellParams":
        if self.box_height <= 2.0 * self.wall or self.box_width <= 2.0 * self.wall:
            raise ValueError("box_height ve box_width, 2 × wall değerinden büyük olmalı.")
        if self.box_length < self.box_height:
            raise ValueError(
                f"box_length ({self.box_length}) en az box_height ({self.box_height}) olmalı."
            )
        return self

    # Orta yüzey kesiti (bölge seçimi ve testler için tek kaynak).
    @property
    def mid_height(self) -> float:
        return self.box_height - self.wall

    @property
    def mid_width(self) -> float:
        return self.box_width - self.wall


def _build(p: CrashBoxShellParams) -> None:
    import gmsh

    # Orta yüzey kesitinin dikdörtgen çevresi (x = 0) x boyunca L kadar
    # ekstrüde edilir: tam dört yan yüzey, uç kapağı yok (açık tüp). Kutudan
    # kapak silmek OCC sınır kutusu toleransı yüzünden güvenilir değildi.
    h2 = p.wall / 2.0
    corners = (
        (h2, h2),
        (p.box_height - h2, h2),
        (p.box_height - h2, p.box_width - h2),
        (h2, p.box_width - h2),
    )
    pts = [gmsh.model.occ.addPoint(0.0, y, z) for y, z in corners]
    lines = [gmsh.model.occ.addLine(pts[i], pts[(i + 1) % 4]) for i in range(4)]
    gmsh.model.occ.extrude([(1, ln) for ln in lines], p.box_length, 0.0, 0.0)


def shell_area_mm2(p: CrashBoxShellParams) -> float:
    return 2.0 * (p.mid_height + p.mid_width) * p.box_length


def shell_volume_mm3(p: CrashBoxShellParams) -> float:
    """Orta yüzey alanı × t — solid kutu hacmine eşit."""
    return shell_area_mm2(p) * p.wall


CRASH_BOX_SHELL = GeometryTemplate(
    id="crash_box_shell",
    name="Crash box — kabuk (orta yüzey)",
    description=(
        "Açık uçlu kutu profilin orta yüzeyi (4 kabuk yüzey, tek parça). 2D kabuk mesh "
        "ve OpenRadioss /SHELL için; kalınlık t crash çözümünde parça kalınlığı. Analitik yok."
    ),
    params_model=CrashBoxShellParams,
    build=_build,
    regions=(
        Region(
            name=REGION_BOX_FRONT,
            description="Ön uç halkası (x = 0) — duvara/plakaya çarpan uç",
            select=plane_at("x", 0.0),
            dim=1,
            expected_faces=4,
        ),
        Region(
            name=REGION_BOX_BACK,
            description="Arka uç halkası (x = L)",
            select=plane_at("x", lambda p: p.box_length),
            dim=1,
            expected_faces=4,
        ),
    ),
    analytic=None,
    characteristic_length=lambda p: min(p.mid_height, p.mid_width),
    default_element_ratio=(0.1, 0.2),
    default_bcs=(
        {"type": "fixed", "region": REGION_BOX_BACK},
        {"type": "cload", "region": REGION_BOX_FRONT, "fx": 1000.0, "fy": 0.0, "fz": 0.0},
    ),
    tags=("crash", "kabuk", "profil"),
    surface_only=True,
)
