"""Şablon: düşme testi kutusu — kapalı kabuk kutu (Faz 1, K2).

a × b × c kapalı kutu yüzeyi (6 yüz, kenar paylaşır → tek kabuk parçası).
Düşme yönü iki açıyla: önce x ekseni çevresinde rx, sonra y ekseni çevresinde
ry (derece, kutu merkezinde). rx = ry = 0 yüzey (taban) düşmesi; ör. rx = 45
kenar, rx = 35.26 / ry = 45 köşe düşmesi — seçim mühendisin. Döndürmeden sonra
en alt nokta z = g'de (zemin z = 0, crash'te rijit duvar).

Bölgeler (döndürmeden önceki yüzlere göre): taban (z = 0 yüzü), tavan
(z = c yüzü), kutu (6 yüz). İsteğe bağlı zemin plakası (floor_size > 0):
z = 0'da kutu merkezinin altında kare yüzey, ayrı parça (1) — rijit duvar
yerine ceza temaslı (TYPE7) zemin için; 0 = yok (varsayılan, rijit duvar). Analitik yok; crash referansı serbest düşme
kinematiği + momentum / enerji (K2 V7). Varsayılan BC'ler yalnız durability
akışı için (taban sabit, tavana basınç).
"""

from __future__ import annotations

import itertools
import math

from pydantic import BaseModel, Field, model_validator

from app.templates.base import GeometryTemplate, Region

REGION_BOTTOM = "taban"
REGION_TOP = "tavan"
REGION_BOX = "kutu"

_TOL = 1e-3


class DropBoxShellParams(BaseModel):
    """Tüm boyutlar mm, açılar derece."""

    size_x: float = Field(200.0, gt=0, description="Kutu boyu a (x)", json_schema_extra={"unit": "mm", "symbol": "a"})
    size_y: float = Field(150.0, gt=0, description="Kutu eni b (y)", json_schema_extra={"unit": "mm", "symbol": "b"})
    size_z: float = Field(50.0, gt=0, description="Kutu yüksekliği c (z)", json_schema_extra={"unit": "mm", "symbol": "c"})
    wall: float = Field(2.0, gt=0, description="Cidar kalınlığı t (kabuk kalınlığı)", json_schema_extra={"unit": "mm", "symbol": "t"})
    rot_x: float = Field(0.0, ge=-90, le=90, description="x ekseni çevresinde dönme rx", json_schema_extra={"unit": "°", "symbol": "rx"})
    rot_y: float = Field(0.0, ge=-90, le=90, description="y ekseni çevresinde dönme ry", json_schema_extra={"unit": "°", "symbol": "ry"})
    gap: float = Field(1.0, ge=0, description="En alt nokta – zemin boşluğu g", json_schema_extra={"unit": "mm", "symbol": "g"})
    floor_size: float = Field(
        0.0, ge=0, description="Zemin plakası kenarı F (0 = yok, rijit duvar /RWALL; > 0 sabit plaka + TYPE7, g > t)", json_schema_extra={"unit": "mm", "symbol": "F"}
    )

    @model_validator(mode="after")
    def _floor_gap(self) -> "DropBoxShellParams":
        # TYPE7 temas boşluğu ≈ (t_kutu + t_zemin)/2 = t: daha küçük g ilk anda
        # penetrasyon demek (deck geçersiz başlar).
        if self.floor_size > 0 and self.gap <= self.wall:
            raise ValueError(f"Zemin plakasıyla g > t olmalı (TYPE7 temas boşluğu ≈ t = {self.wall:g} mm).")
        return self


def _rotate(p: DropBoxShellParams, x: float, y: float, z: float) -> tuple[float, float, float]:
    """Kutu merkezinde rx (x ekseni) sonra ry (y ekseni)."""
    cx, cy, cz = p.size_x / 2.0, p.size_y / 2.0, p.size_z / 2.0
    x, y, z = x - cx, y - cy, z - cz
    a, b = math.radians(p.rot_x), math.radians(p.rot_y)
    y, z = y * math.cos(a) - z * math.sin(a), y * math.sin(a) + z * math.cos(a)
    x, z = x * math.cos(b) + z * math.sin(b), -x * math.sin(b) + z * math.cos(b)
    return x + cx, y + cy, z + cz


def _z_shift(p: DropBoxShellParams) -> float:
    corners = [_rotate(p, *c) for c in itertools.product((0.0, p.size_x), (0.0, p.size_y), (0.0, p.size_z))]
    return p.gap - min(c[2] for c in corners)


def placed_corners(p: DropBoxShellParams, face_z: float) -> list[tuple[float, float, float]]:
    """Yerleşik konumda z = face_z (0 ya da c) yüzünün 4 köşesi."""
    dz = _z_shift(p)
    out = []
    for x, y in itertools.product((0.0, p.size_x), (0.0, p.size_y)):
        rx, ry, rz = _rotate(p, x, y, face_z)
        out.append((rx, ry, rz + dz))
    return out


def lowest_z(p: DropBoxShellParams) -> float:
    return min(c[2] for z in (0.0, p.size_z) for c in placed_corners(p, z))


def _build(p: DropBoxShellParams) -> None:
    import gmsh

    occ = gmsh.model.occ
    box = occ.addBox(0.0, 0.0, 0.0, p.size_x, p.size_y, p.size_z)
    occ.remove([(3, box)], recursive=False)  # hacim yok, 6 yüz kalır
    occ.synchronize()
    faces = gmsh.model.getEntities(2)
    cx, cy, cz = p.size_x / 2.0, p.size_y / 2.0, p.size_z / 2.0
    if p.rot_x:
        occ.rotate(faces, cx, cy, cz, 1, 0, 0, math.radians(p.rot_x))
    if p.rot_y:
        occ.rotate(faces, cx, cy, cz, 0, 1, 0, math.radians(p.rot_y))
    occ.translate(faces, 0.0, 0.0, _z_shift(p))
    if p.floor_size > 0:
        half = p.floor_size / 2.0
        occ.addRectangle(p.size_x / 2.0 - half, p.size_y / 2.0 - half, 0.0, p.floor_size, p.floor_size)
    occ.synchronize()


def _is_floor(bbox, p: BaseModel) -> bool:
    f = getattr(p, "floor_size", 0.0)
    return f > 0 and abs(bbox[2]) < _TOL and abs(bbox[5]) < _TOL and abs((bbox[3] - bbox[0]) - f) < _TOL


def _face_select(face_z: float):
    def _select(bbox, p: BaseModel) -> bool:
        cs = placed_corners(p, face_z)  # type: ignore[arg-type]
        exp = (min(c[0] for c in cs), min(c[1] for c in cs), min(c[2] for c in cs),
               max(c[0] for c in cs), max(c[1] for c in cs), max(c[2] for c in cs))
        return all(abs(u - v) < _TOL for u, v in zip(bbox, exp))

    return _select


DROP_BOX_SHELL = GeometryTemplate(
    id="drop_box_shell",
    name="Düşme testi kutusu — kapalı kabuk",
    description=(
        "Kapalı a × b × c kabuk kutu; rx / ry açılarıyla yüzey, kenar ya da köşe düşmesi, en alt "
        "nokta zeminden g yukarıda. Crash'te zemin rijit duvar z = 0, /GRAV, v0 = √(2·g·H)."
    ),
    params_model=DropBoxShellParams,
    build=_build,
    regions=(
        Region(name=REGION_BOTTOM, description="Taban (döndürmeden önce z = 0 yüzü)", select=_face_select(0.0),
               dim=2, expected_faces=1),
        Region(name=REGION_TOP, description="Tavan (döndürmeden önce z = c yüzü)",
               select=lambda bb, p: _face_select(p.size_z)(bb, p), dim=2, expected_faces=1),  # type: ignore[attr-defined]
        Region(name=REGION_BOX, description="Kutunun 6 yüzü", select=lambda bb, p: not _is_floor(bb, p), dim=2,
               expected_faces=6),
    ),
    analytic=None,
    characteristic_length=lambda p: min(p.size_x, p.size_y, p.size_z),
    default_element_ratio=(0.1, 0.2),
    default_bcs=(
        {"type": "fixed", "region": REGION_BOTTOM},
        {"type": "pressure", "region": REGION_TOP, "magnitude": 0.1},
    ),
    tags=("crash", "kabuk", "dusme"),
    surface_only=True,
)
