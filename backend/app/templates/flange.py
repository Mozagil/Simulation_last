"""Şablon: cıvata delikli flanş — halka plaka, n cıvata deliği, boru deliğinden eksenel yük (Grup 3).

Eksen x. Plaka x∈[0, t]; dış yarıçap R, boru deliği yarıçapı ri, cıvata
çemberi yarıçapı Rb üzerinde n delik (çap d), ilki +y'de, eşit aralıklı.
Cıvata delik yüzeyleri ankastre; boru deliği yüzeyine +x yönünde eksenel
CLOAD (borunun flanşı çekmesi). Kapalı form referans yok (`analytic=None`) —
plaka eğilmesi + delik etkileşimi; DOE ön elemesi bu şablonda atlanır.
"""

from __future__ import annotations

import math

from pydantic import BaseModel, Field, model_validator

from app.templates.base import BBox, GeometryTemplate, Region

REGION_BOLTS = "civata_delikleri"
REGION_BORE = "boru_delik_yuzeyi"


class FlangeParams(BaseModel):
    """Tüm boyutlar mm."""

    outer_radius: float = Field(80.0, gt=0, description="Dış yarıçap R", json_schema_extra={"unit": "mm", "symbol": "R"})
    bore_radius: float = Field(30.0, gt=0, description="Boru deliği yarıçapı ri", json_schema_extra={"unit": "mm", "symbol": "ri"})
    bolt_circle_radius: float = Field(60.0, gt=0, description="Cıvata çemberi yarıçapı Rb", json_schema_extra={"unit": "mm", "symbol": "Rb"})
    bolt_diameter: float = Field(10.0, gt=0, description="Cıvata deliği çapı d", json_schema_extra={"unit": "mm", "symbol": "d"})
    bolt_count: int = Field(6, ge=3, le=24, description="Cıvata sayısı n", json_schema_extra={"unit": "-", "symbol": "n"})
    thickness: float = Field(12.0, gt=0, description="Plaka kalınlığı t (x)", json_schema_extra={"unit": "mm", "symbol": "t"})

    @model_validator(mode="after")
    def _rings(self) -> "FlangeParams":
        rb = self.bolt_diameter / 2.0
        if not (self.bore_radius + rb < self.bolt_circle_radius < self.outer_radius - rb):
            raise ValueError("Cıvata çemberi boru deliği ile dış kenar arasında, deliklere yer bırakacak şekilde olmalı.")
        pitch = 2.0 * self.bolt_circle_radius * math.sin(math.pi / self.bolt_count)
        if pitch <= self.bolt_diameter:
            raise ValueError("Cıvata delikleri birbirine değiyor: bolt_count azaltın ya da Rb artırın.")
        return self


def _bolt_centers(p: FlangeParams) -> list[tuple[float, float]]:
    return [
        (p.bolt_circle_radius * math.cos(math.pi / 2.0 + 2.0 * math.pi * k / p.bolt_count),
         p.bolt_circle_radius * math.sin(math.pi / 2.0 + 2.0 * math.pi * k / p.bolt_count))
        for k in range(p.bolt_count)
    ]


def _build(p: FlangeParams) -> None:
    import gmsh

    t = p.thickness
    disk = gmsh.model.occ.addCylinder(0.0, 0.0, 0.0, t, 0.0, 0.0, p.outer_radius)
    cuts = [(3, gmsh.model.occ.addCylinder(-1.0, 0.0, 0.0, t + 2.0, 0.0, 0.0, p.bore_radius))]
    cuts += [
        (3, gmsh.model.occ.addCylinder(-1.0, y, z, t + 2.0, 0.0, 0.0, p.bolt_diameter / 2.0))
        for y, z in _bolt_centers(p)
    ]
    gmsh.model.occ.cut([(3, disk)], cuts)


def _through_faces(bbox: BBox, p: FlangeParams, tol: float) -> bool:
    xmin, _, _, xmax, _, _ = bbox
    return abs(xmin) < tol and abs(xmax - p.thickness) < tol


def _is_bore_face(bbox: BBox, params: BaseModel, tol: float = 1e-3) -> bool:
    p = params
    xmin, ymin, zmin, xmax, ymax, zmax = bbox
    if not _through_faces(bbox, p, tol):
        return False
    d = 2.0 * p.bore_radius
    return (abs((ymax - ymin) - d) < tol and abs((zmax - zmin) - d) < tol
            and abs(ymin + ymax) < tol and abs(zmin + zmax) < tol)


def _is_bolt_face(bbox: BBox, params: BaseModel, tol: float = 1e-3) -> bool:
    p = params
    xmin, ymin, zmin, xmax, ymax, zmax = bbox
    if not _through_faces(bbox, p, tol):
        return False
    d = p.bolt_diameter
    if abs((ymax - ymin) - d) > tol or abs((zmax - zmin) - d) > tol:
        return False
    cy, cz = (ymin + ymax) / 2.0, (zmin + zmax) / 2.0
    return any(abs(cy - y) < tol and abs(cz - z) < tol for y, z in _bolt_centers(p))


FLANGE = GeometryTemplate(
    id="flange",
    name="Flanş (cıvata delikli)",
    description=(
        "Halka plaka, n cıvata deliği ankastre, boru deliği yüzeyinden eksenel çekme. "
        "Kapalı form referans yok."
    ),
    params_model=FlangeParams,
    build=_build,
    regions=(
        Region(
            name=REGION_BOLTS,
            description="Cıvata deliklerinin silindir yüzeyleri — ankastre",
            select=_is_bolt_face,
        ),
        Region(
            name=REGION_BORE,
            description="Boru deliği yüzeyi — eksenel CLOAD +x",
            select=_is_bore_face,
            expected_faces=1,
        ),
    ),
    analytic=None,
    characteristic_length=lambda p: p.thickness,
    default_element_ratio=(0.4, 0.8),
    default_bcs=(
        {"type": "fixed", "region": REGION_BOLTS},
        {"type": "cload", "region": REGION_BORE, "fx": 5000.0, "fy": 0.0, "fz": 0.0},
    ),
    tags=("grup3", "delik", "flans"),
)
