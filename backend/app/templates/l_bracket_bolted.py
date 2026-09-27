"""Şablon: delikli L-braket — cıvatayla duvara bağlı dik bacak + yüklü yatay bacak (Grup 3).

Yerleşim: dik bacak x∈[0, t] · y∈[0, hv], yatay bacak x∈[0, lh] · y∈[0, t],
genişlik z∈[0, w]. Dik bacakta 2 cıvata deliği (çap d, eksen x) y = hv − e,
z = w/4 ve 3w/4. Ankastre BC DELİK YÜZEYLERİNE uygulanır (cıvata gövdesi
kabulü) — duvar yüzü serbest; bu, delik kenarında gerçek yığılma üretir.

Analitik referans: yatay bacak dikdörtgen kesitli konsol (I = w t³/12);
köşe esnekliği ve delik yığılması dahil değil.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from app.templates.base import BBox, GeometryTemplate, Region, plane_at
from app.templates.base import AnalyticInput
from app.templates.beam_section import cantilever_fl_over_ei

REGION_BOLTS = "civata_delikleri"
REGION_LOAD = "bacak_ucu"


class LBracketBoltedParams(BaseModel):
    """Tüm boyutlar mm."""

    vertical_height: float = Field(100.0, gt=0, description="Dik bacak yüksekliği hv (y)", json_schema_extra={"unit": "mm", "symbol": "hv"})
    horizontal_length: float = Field(120.0, gt=0, description="Yatay bacak boyu lh (x)", json_schema_extra={"unit": "mm", "symbol": "lh"})
    width: float = Field(60.0, gt=0, description="Genişlik w (z)", json_schema_extra={"unit": "mm", "symbol": "w"})
    thickness: float = Field(8.0, gt=0, description="Kalınlık t", json_schema_extra={"unit": "mm", "symbol": "t"})
    hole_diameter: float = Field(9.0, gt=0, description="Cıvata deliği çapı d", json_schema_extra={"unit": "mm", "symbol": "d"})
    edge_distance: float = Field(15.0, gt=0, description="Delik merkezi – üst kenar e", json_schema_extra={"unit": "mm", "symbol": "e"})

    @model_validator(mode="after")
    def _holes_fit(self) -> "LBracketBoltedParams":
        r = self.hole_diameter / 2.0
        if self.edge_distance <= r:
            raise ValueError("edge_distance delik yarıçapından büyük olmalı.")
        if self.vertical_height - self.edge_distance - r <= self.thickness:
            raise ValueError("Delik yatay bacağın içine giriyor: vertical_height artırın.")
        if self.width / 4.0 <= r:
            raise ValueError("Delikler genişliğe sığmıyor (w/4 > d/2 olmalı).")
        if self.horizontal_length < 3.0 * self.thickness:
            raise ValueError("horizontal_length en az 3 × thickness olmalı.")
        return self


def _hole_centers(p: LBracketBoltedParams) -> list[tuple[float, float]]:
    y = p.vertical_height - p.edge_distance
    return [(y, p.width / 4.0), (y, 3.0 * p.width / 4.0)]


def _build(p: LBracketBoltedParams) -> None:
    import gmsh

    t = p.thickness
    vert = gmsh.model.occ.addBox(0.0, 0.0, 0.0, t, p.vertical_height, p.width)
    horiz = gmsh.model.occ.addBox(0.0, 0.0, 0.0, p.horizontal_length, t, p.width)
    body, _ = gmsh.model.occ.fuse([(3, vert)], [(3, horiz)])
    holes = [
        (3, gmsh.model.occ.addCylinder(-1.0, y, z, t + 2.0, 0.0, 0.0, p.hole_diameter / 2.0))
        for y, z in _hole_centers(p)
    ]
    gmsh.model.occ.cut(body, holes)


def _is_hole_face(bbox: BBox, params: BaseModel, tol: float = 1e-3) -> bool:
    """Delik silindir yüzeyi: x∈[0,t], y ve z genişliği tam d, merkezi delik merkezinde."""
    p = params
    xmin, ymin, zmin, xmax, ymax, zmax = bbox
    d = p.hole_diameter
    if abs(xmin) > tol or abs(xmax - p.thickness) > tol:
        return False
    if abs((ymax - ymin) - d) > tol or abs((zmax - zmin) - d) > tol:
        return False
    cy, cz = (ymin + ymax) / 2.0, (zmin + zmax) / 2.0
    return any(abs(cy - y) < tol and abs(cz - z) < tol for y, z in _hole_centers(p))


def _analytic(p: LBracketBoltedParams, a: AnalyticInput) -> dict[str, float]:
    inertia = p.width * p.thickness**3 / 12.0
    return cantilever_fl_over_ei(p.horizontal_length, inertia, p.thickness / 2.0, a.force_n, a.youngs_modulus_pa)


L_BRACKET_BOLTED = GeometryTemplate(
    id="l_bracket_bolted",
    name="L-braket (cıvata delikli)",
    description=(
        "Dik bacağı iki cıvata deliğinden tutulan L-braket; yatay bacak ucundan −y yük. "
        "Ankastre BC delik yüzeylerinde."
    ),
    params_model=LBracketBoltedParams,
    build=_build,
    regions=(
        Region(
            name=REGION_BOLTS,
            description="İki cıvata deliğinin silindir yüzeyleri — ankastre",
            select=_is_hole_face,
            expected_faces=2,
        ),
        Region(
            name=REGION_LOAD,
            description="Yatay bacak ucu (x=lh) — CLOAD −y",
            select=plane_at("x", lambda p: p.horizontal_length),
            expected_faces=1,
        ),
    ),
    analytic=_analytic,
    characteristic_length=lambda p: p.thickness,
    default_element_ratio=(0.4, 0.8),
    default_bcs=(
        {"type": "fixed", "region": REGION_BOLTS},
        {"type": "cload", "region": REGION_LOAD, "fx": 0.0, "fy": -500.0, "fz": 0.0},
    ),
    tags=("grup3", "analitik", "egilme", "braket", "delik"),
)
