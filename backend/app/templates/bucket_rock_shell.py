"""Şablon: kepçe / taş darbesi — kavisli kepçe tabanı + rijit taş, kabuk (Faz 1, K11).

Parça 0: kepçe tabanı — R yarıçaplı, φ açılı silindirik kabuk (orta yüzey),
ekseni y (genişlik W), en alt noktası z = 0'da; kesit x–z düzleminde yay.
Uzun kenarları (yayın iki ucu, y boyunca) pim bağlantısını temsilen sabit.
Parça 1: taş — Ø D rijit küre (6 yamalı küp-küre, 1.18a), tabanın en alt
noktasının g + t/2 üstünde.

Crash (K11): taş rijit gövde + kütle + −z ilk hız (plaka–küre deseni),
taş → taban TYPE7, kenarlar /BCS. Referans (veri): momentum / ivme kanalı
(∫|a| dt = I/m), taban çökmesi ve iç enerji. Kriterler mühendisin.
Bölgeler: kepce_kenar (yayın iki uç kenarı), kepce (taban yüzü), tas (küre).
"""

from __future__ import annotations

import math

from pydantic import BaseModel, Field, model_validator

from app.templates.base import GeometryTemplate, Region
from app.templates.plate_ball_shell import add_cube_sphere

REGION_EDGE = "kepce_kenar"
REGION_BUCKET = "kepce"
REGION_ROCK = "tas"

_TOL = 1e-3


class BucketRockShellParams(BaseModel):
    """Tüm boyutlar mm, açı derece."""

    radius: float = Field(500.0, gt=0, description="Taban yarıçapı R (orta yüzey)", json_schema_extra={"unit": "mm", "symbol": "R"})
    angle: float = Field(90.0, gt=0, le=150, description="Taban yay açısı φ", json_schema_extra={"unit": "°", "symbol": "φ"})
    width: float = Field(600.0, gt=0, description="Kepçe genişliği W (y)", json_schema_extra={"unit": "mm", "symbol": "W"})
    thickness: float = Field(10.0, gt=0, description="Taban sac kalınlığı t", json_schema_extra={"unit": "mm", "symbol": "t"})
    rock_diameter: float = Field(200.0, gt=0, description="Taş çapı D", json_schema_extra={"unit": "mm", "symbol": "D"})
    gap: float = Field(1.0, ge=0, description="Taban üst yüzü – taş boşluğu g", json_schema_extra={"unit": "mm", "symbol": "g"})

    @model_validator(mode="after")
    def _ok(self) -> "BucketRockShellParams":
        if self.rock_diameter >= self.width or self.rock_diameter >= self.radius:
            raise ValueError("rock_diameter, width ve radius'tan küçük olmalı.")
        return self

    @property
    def rock_centre_z(self) -> float:
        return self.thickness / 2.0 + self.gap + self.rock_diameter / 2.0


def _build(p: BucketRockShellParams) -> None:
    import gmsh

    occ = gmsh.model.occ
    half = math.radians(p.angle) / 2.0
    # Yay x–z düzleminde, merkez (0, 0, R), en alt nokta (0, 0, 0); y = 0'dan W'ye ekstrüde.
    c = occ.addPoint(0.0, 0.0, p.radius)
    a = occ.addPoint(-p.radius * math.sin(half), 0.0, p.radius * (1.0 - math.cos(half)))
    m = occ.addPoint(0.0, 0.0, 0.0)
    b = occ.addPoint(p.radius * math.sin(half), 0.0, p.radius * (1.0 - math.cos(half)))
    arcs = [occ.addCircleArc(a, c, m), occ.addCircleArc(m, c, b)]
    occ.extrude([(1, arc) for arc in arcs], 0.0, p.width, 0.0)
    occ.remove([(0, c)])
    add_cube_sphere((0.0, p.width / 2.0, p.rock_centre_z), p.rock_diameter / 2.0)


def _edge(bbox, p: BaseModel) -> bool:
    # Yayın iki uç kenarı: x = ±R·sin(φ/2) doğruları, y boyunca.
    x0, y0, z0, x1, y1, z1 = bbox
    xe = p.radius * math.sin(math.radians(p.angle) / 2.0)  # type: ignore[attr-defined]
    return abs(x0 - x1) < _TOL and abs(abs(x0) - xe) < _TOL and (y1 - y0) > _TOL


def _bucket(bbox, p: BaseModel) -> bool:
    return (bbox[4] - bbox[1]) > p.width - _TOL  # type: ignore[attr-defined]


def _rock(bbox, p: BaseModel) -> bool:
    return not _bucket(bbox, p)


BUCKET_ROCK_SHELL = GeometryTemplate(
    id="bucket_rock_shell",
    name="Kepçe / taş darbesi — kavisli taban + rijit taş (kabuk)",
    description=(
        "Silindirik kavisli kepçe tabanı (R, φ, W, t; uzun kenarları sabit) ve üstünde Ø D rijit taş "
        "(küp-küre). Crash'te taş rijit gövde + kütle + −z ilk hız, TYPE7. Analitik yok."
    ),
    params_model=BucketRockShellParams,
    build=_build,
    regions=(
        Region(name=REGION_EDGE, description="Taban yayının iki uç kenarı (pim)", select=_edge, dim=1, expected_faces=2),
        Region(name=REGION_BUCKET, description="Kepçe taban yüzleri", select=_bucket, dim=2, expected_faces=2),
        Region(name=REGION_ROCK, description="Taş yüzü (6 yama)", select=_rock, dim=2, expected_faces=6),
    ),
    analytic=None,
    characteristic_length=lambda p: p.rock_diameter,
    default_element_ratio=(0.08, 0.15),
    default_bcs=(
        {"type": "fixed", "region": REGION_EDGE},
        {"type": "fixed", "region": REGION_ROCK},
        {"type": "pressure", "region": REGION_BUCKET, "magnitude": 0.1},
    ),
    tags=("crash", "kabuk", "is_makinesi"),
    surface_only=True,
)
