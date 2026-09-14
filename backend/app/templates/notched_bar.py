"""Şablon: iki kenar çentikli çekme çubuğu, U veya V (Grup 4).

x = boy, y = genişlik, z = kalınlık. Ortada y=0 ve y=W kenarlarında çentik.
Analitik yalnız σ_max: Neuber Kt × net çekme. Deplasman kapalı formu yok.
"""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.templates.base import AnalyticInput, BBox, GeometryTemplate, Region, plane_at

REGION_FIXED = "tutulan_uc"
REGION_LOAD = "yuk_cekme"
REGION_NOTCH = "centik_civari"


class NotchedBarParams(BaseModel):
    """Tüm boyutlar mm."""

    length: float = Field(200.0, gt=0, description="Boy L (x, çekme)", json_schema_extra={"unit": "mm"})
    width: float = Field(40.0, gt=0, description="Brüt genişlik W (y)", json_schema_extra={"unit": "mm"})
    thickness: float = Field(8.0, gt=0, description="Kalınlık T (z)", json_schema_extra={"unit": "mm"})
    notch_kind: Literal["u", "v"] = Field("u", description="Çentik tipi: u (yarım daire) veya v")
    notch_radius: float = Field(4.0, gt=0, description="U: yarıçap (=derinlik); V: uç yarıçapı r", json_schema_extra={"unit": "mm"})
    notch_depth: float = Field(
        6.0, gt=0, description="V çentik derinliği a (U'da yok sayılır, a=r)", json_schema_extra={"unit": "mm"}
    )
    v_angle_deg: float = Field(90.0, gt=0, lt=180, description="V dahil açı (derece)")

    @model_validator(mode="after")
    def _notch_fits(self) -> "NotchedBarParams":
        depth = self.notch_radius if self.notch_kind == "u" else self.notch_depth
        if 2.0 * depth >= self.width:
            raise ValueError("İki çentik birleşmesin: 2 × derinlik < width.")
        net = self.width - 2.0 * depth
        if net < 0.2 * self.width:
            raise ValueError("Net kesit çok dar (net ≥ 0.2 × width).")
        if self.length < 6.0 * depth:
            raise ValueError("length, 6 × çentik derinliğinden büyük olmalı (uç etkisi).")
        if self.notch_kind == "v" and self.notch_radius > self.notch_depth:
            raise ValueError("V uç yarıçapı (notch_radius) derinlikten büyük olamaz.")
        return self

    @property
    def depth(self) -> float:
        return self.notch_radius if self.notch_kind == "u" else self.notch_depth


def neuber_kt(depth: float, tip_radius: float, v_angle_deg: float | None = None) -> float:
    """Neuber: Kt ≈ 1 + 2 √(a/r); V'de açı küçüldükçe (sivri) çarpan artar."""
    kt = 1.0 + 2.0 * math.sqrt(depth / tip_radius)
    if v_angle_deg is not None:
        kt *= (180.0 - v_angle_deg) / 90.0
    return min(kt, 6.0)


def _notch_zone(bbox: BBox, params: BaseModel, tol: float = 0.35) -> bool:
    xmin, ymin, zmin, xmax, ymax, zmax = bbox
    p = params
    assert isinstance(p, NotchedBarParams)
    depth = p.depth
    t = p.thickness
    L = p.length
    W = p.width
    dx, dy, dz = xmax - xmin, ymax - ymin, zmax - zmin
    if abs(dz - t) > max(t * 0.08, 1e-3):
        return False
    cx = 0.5 * (xmin + xmax)
    if abs(cx - L / 2.0) > max(depth * 1.2, 2.0):
        return False
    # Kenar çentiği: y≈0 veya y≈W civarı, x-span ~ 2*depth
    if dx > 4.0 * depth + 1.0:
        return False
    near_low = ymin < depth * (1.0 + tol) and ymax < W * 0.45
    near_high = ymax > W - depth * (1.0 + tol) and ymin > W * 0.55
    return near_low or near_high


def _add_v_prism(p: NotchedBarParams, y_edge: float, inward: float) -> int:
    """Üçgen prizma (z boyunca) — V kesici. inward: +1 y=0'dan içeri."""
    import gmsh

    a = p.notch_depth
    half = a * math.tan(math.radians(p.v_angle_deg) / 2.0)
    x0 = p.length / 2.0
    z0 = -1.0
    y_tip = y_edge + inward * a
    pts = [
        (x0 - half, y_edge, z0),
        (x0 + half, y_edge, z0),
        (x0, y_tip, z0),
    ]
    vs = [gmsh.model.occ.addPoint(*q) for q in pts]
    ls = [
        gmsh.model.occ.addLine(vs[0], vs[1]),
        gmsh.model.occ.addLine(vs[1], vs[2]),
        gmsh.model.occ.addLine(vs[2], vs[0]),
    ]
    cl = gmsh.model.occ.addCurveLoop(ls)
    surf = gmsh.model.occ.addPlaneSurface([cl])
    gmsh.model.occ.synchronize()
    extruded = gmsh.model.occ.extrude([(2, surf)], 0.0, 0.0, p.thickness + 2.0)
    solids = [tag for dim, tag in extruded if dim == 3]
    if not solids:
        raise RuntimeError("V çentik prizması hacim üretmedi.")
    return solids[0]


def _build(p: NotchedBarParams) -> None:
    import gmsh

    plate = gmsh.model.occ.addBox(0.0, 0.0, 0.0, p.length, p.width, p.thickness)
    tools: list[tuple[int, int]] = []
    if p.notch_kind == "u":
        r = p.notch_radius
        c1 = gmsh.model.occ.addCylinder(p.length / 2.0, 0.0, -1.0, 0.0, 0.0, p.thickness + 2.0, r)
        c2 = gmsh.model.occ.addCylinder(
            p.length / 2.0, p.width, -1.0, 0.0, 0.0, p.thickness + 2.0, r
        )
        tools = [(3, c1), (3, c2)]
    else:
        v1 = _add_v_prism(p, 0.0, 1.0)
        v2 = _add_v_prism(p, p.width, -1.0)
        tools = [(3, v1), (3, v2)]
    gmsh.model.occ.cut([(3, plate)], tools)


def _analytic(p: NotchedBarParams, a: AnalyticInput) -> dict[str, float]:
    depth = p.depth
    net = (p.width - 2.0 * depth) * p.thickness
    sigma_nom = a.force_n / net
    angle = None if p.notch_kind == "u" else p.v_angle_deg
    kt = neuber_kt(depth, p.notch_radius, angle)
    return {"max_von_mises": kt * sigma_nom}


NOTCHED_BAR = GeometryTemplate(
    id="notched_bar",
    name="Çentikli çubuk (U / V, çekme)",
    description=(
        "Dikdörtgen çubuk, orta açıklıkta karşılıklı U (yarım daire) veya V çentik. "
        "σ_max = Kt F / ((W−2a) T); Kt Neuber 1+2√(a/r)."
    ),
    params_model=NotchedBarParams,
    build=_build,
    regions=(
        Region(name=REGION_FIXED, description="Tutulan uç (x=0)", select=plane_at("x", 0.0)),
        Region(
            name=REGION_LOAD,
            description="Çekme ucu (x=L) — CLOAD +x",
            select=plane_at("x", lambda p: p.length),
        ),
        Region(
            name=REGION_NOTCH,
            description="Çentik cidarı — gerilme yığılması",
            select=_notch_zone,
        ),
    ),
    analytic=_analytic,
    tags=("grup4", "analitik", "gerilme_yigilmasi"),
)
