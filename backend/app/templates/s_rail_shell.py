"""Şablon: S-kiriş (ön kiriş) — S yolu boyunca süpürülmüş dikdörtgen tüp, kabuk (Faz 1, K7).

Orta çizgi kesiti h (y) × b (z), cidar t; yol x–y düzleminde: düz L1 (+x),
θ açılı R yarıçaplı sola dönüş, θ açılı sağa dönüş, düz L2 (+x). Yanal
kaçıklık 2·R·(1 − cos θ). Ön uç (x = 0) rijit duvara çarpar; arka uç
halkası kızak (rijit gövde + kütle). Süpürme tek parça, uyumlu mesh (K4 deseni).

Referans: Altair Radioss Example Guide RD-E 0300 (S-beam crash) problem tanımı;
analitik yok — momentum / enerji ve aynı kesitli düz tüpün ortalama ezilme
kuvveti (Wierzbicki–Abramowicz) ile oran veri olarak (eğilmeli çökme düşük).
Bölgeler: on_halka (x = 0), arka_halka (son kesit). Durability BC'leri yalnız
şablon kütüphanesi testleri için.
"""

from __future__ import annotations

import math

from pydantic import BaseModel, Field, model_validator

from app.templates.base import GeometryTemplate, Region, plane_at

REGION_FRONT = "on_halka"
REGION_BACK = "arka_halka"


class SRailShellParams(BaseModel):
    """Tüm boyutlar mm, açı derece."""

    front_length: float = Field(100.0, gt=0, description="Ön düz boy L1", json_schema_extra={"unit": "mm", "symbol": "L1"})
    rear_length: float = Field(200.0, gt=0, description="Arka düz boy L2", json_schema_extra={"unit": "mm", "symbol": "L2"})
    bend_radius: float = Field(150.0, gt=0, description="Büküm yarıçapı R (eksen)", json_schema_extra={"unit": "mm", "symbol": "R"})
    bend_angle: float = Field(45.0, gt=0, le=80, description="Büküm açısı θ", json_schema_extra={"unit": "°", "symbol": "θ"})
    height: float = Field(60.0, gt=0, description="Kesit yüksekliği h (y, büküm düzleminde)", json_schema_extra={"unit": "mm", "symbol": "h"})
    width: float = Field(40.0, gt=0, description="Kesit genişliği b (z)", json_schema_extra={"unit": "mm", "symbol": "b"})
    wall: float = Field(2.0, gt=0, description="Cidar kalınlığı t (kabuk kalınlığı)", json_schema_extra={"unit": "mm", "symbol": "t"})

    @model_validator(mode="after")
    def _ok(self) -> "SRailShellParams":
        if self.bend_radius <= self.height / 2.0:
            raise ValueError("bend_radius, height / 2'den büyük olmalı.")
        if self.height <= self.wall or self.width <= self.wall:
            raise ValueError("height ve width, wall'dan büyük olmalı.")
        return self


def end_point(p: SRailShellParams) -> tuple[float, float]:
    """Yolun bitiş noktası (x, y)."""
    th = math.radians(p.bend_angle)
    x = p.front_length + 2.0 * p.bend_radius * math.sin(th) + p.rear_length
    y = 2.0 * p.bend_radius * (1.0 - math.cos(th))
    return x, y


def path_length(p: SRailShellParams) -> float:
    return p.front_length + p.rear_length + 2.0 * p.bend_radius * math.radians(p.bend_angle)


def _build(p: SRailShellParams) -> None:
    import gmsh

    occ = gmsh.model.occ
    th, R = math.radians(p.bend_angle), p.bend_radius
    P0 = (0.0, 0.0)
    P1 = (p.front_length, 0.0)
    C1 = (P1[0], R)
    P2 = (P1[0] + R * math.sin(th), R * (1.0 - math.cos(th)))
    C2 = (P2[0] + R * math.sin(th), P2[1] - R * math.cos(th))
    P3 = (C2[0], C2[1] + R)
    P4 = (P3[0] + p.rear_length, P3[1])
    pt = {k: occ.addPoint(x, y, 0.0) for k, (x, y) in
          {"P0": P0, "P1": P1, "C1": C1, "P2": P2, "C2": C2, "P3": P3, "P4": P4}.items()}
    path = occ.addWire([
        occ.addLine(pt["P0"], pt["P1"]),
        occ.addCircleArc(pt["P1"], pt["C1"], pt["P2"]),
        occ.addCircleArc(pt["P2"], pt["C2"], pt["P3"]),
        occ.addLine(pt["P3"], pt["P4"]),
    ])
    h2, b2 = p.height / 2.0, p.width / 2.0
    q = [occ.addPoint(0.0, y, z) for y, z in ((-h2, -b2), (h2, -b2), (h2, b2), (-h2, b2))]
    profile = [occ.addLine(q[i], q[(i + 1) % 4]) for i in range(4)]
    occ.addPipe([(1, c) for c in profile], path, "DiscreteTrihedron")
    occ.synchronize()
    keep = {c for _d, f in gmsh.model.getEntities(2) for _dd, c in gmsh.model.getBoundary([(2, f)], oriented=False)}
    stray = [(1, c) for _d, c in gmsh.model.getEntities(1) if c not in keep]
    if stray:
        occ.remove(stray, recursive=True)


S_RAIL_SHELL = GeometryTemplate(
    id="s_rail_shell",
    name="S-kiriş (ön kiriş) — süpürülmüş kabuk tüp",
    description=(
        "S yolu (düz – sol büküm – sağ büküm – düz) boyunca dikdörtgen tüp, kabuk. Ön uç rijit duvara "
        "çarpar, arka halka kızak (rijit gövde + kütle). RD-E 0300 problem tanımı; analitik yok."
    ),
    params_model=SRailShellParams,
    build=_build,
    regions=(
        Region(name=REGION_FRONT, description="Ön uç halkası (x = 0)", select=plane_at("x", 0.0), dim=1, expected_faces=4),
        Region(name=REGION_BACK, description="Arka uç halkası (son kesit)", select=plane_at("x", lambda p: end_point(p)[0]),
               dim=1, expected_faces=4),
    ),
    analytic=None,
    characteristic_length=lambda p: min(p.height, p.width),
    default_element_ratio=(0.1, 0.25),
    default_bcs=(
        {"type": "fixed", "region": REGION_BACK},
        {"type": "cload", "region": REGION_FRONT, "fx": 1000.0, "fy": 0.0, "fz": 0.0},
    ),
    tags=("crash", "kabuk", "s_kiris"),
    surface_only=True,
)
