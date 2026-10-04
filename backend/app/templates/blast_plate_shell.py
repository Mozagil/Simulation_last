"""Şablon: patlama yüklü plaka — kenarları ankastre kare plaka, kabuk (Faz 1, K10).

a × a kare plaka orta yüzeyi z = 0, merkez orijinde (1.18 plakasıyla aynı
çerçeve). Crash'te dört kenar /BCS, plaka yüzeyine zamana bağlı Friedlander
basıncı (/PLOAD, K10). Referans (veri): uygulanan impuls A·∫p dt = plakanın
yük süresi sonundaki momentumu (kısa darbe, kenar tepkisi küçükken) ve
dış iş = IE + KE. Kalıcı çökme (ör. Nurick ampirik bağıntıları) mühendisin.
Bölgeler: plaka_kenar (4 kenar), plaka (yüzey).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.templates.base import GeometryTemplate, Region

REGION_EDGE = "plaka_kenar"
REGION_PLATE = "plaka"

_TOL = 1e-6


class BlastPlateShellParams(BaseModel):
    """Tüm boyutlar mm."""

    plate_size: float = Field(400.0, gt=0, description="Kare plaka kenarı a", json_schema_extra={"unit": "mm", "symbol": "a"})
    plate_thickness: float = Field(3.0, gt=0, description="Plaka kalınlığı t (kabuk kalınlığı)", json_schema_extra={"unit": "mm", "symbol": "t"})


def _build(p: BlastPlateShellParams) -> None:
    import gmsh

    h = p.plate_size / 2.0
    gmsh.model.occ.addRectangle(-h, -h, 0.0, p.plate_size, p.plate_size)


def _edge(bbox, p: BaseModel) -> bool:
    x0, y0, z0, x1, y1, z1 = bbox
    h = p.plate_size / 2.0  # type: ignore[attr-defined]
    on_x = abs(x0 - x1) < _TOL and abs(abs(x0) - h) < _TOL
    on_y = abs(y0 - y1) < _TOL and abs(abs(y0) - h) < _TOL
    return on_x or on_y


BLAST_PLATE_SHELL = GeometryTemplate(
    id="blast_plate_shell",
    name="Patlama yüklü plaka — ankastre kare kabuk",
    description=(
        "Dört kenarı ankastre kare plaka (orta yüzey z = 0); crash'te Friedlander basınç darbesi "
        "(/PLOAD). Referans: uygulanan impuls = plaka momentumu, dış iş = IE + KE."
    ),
    params_model=BlastPlateShellParams,
    build=_build,
    regions=(
        Region(name=REGION_EDGE, description="Dört dış kenar", select=_edge, dim=1, expected_faces=4),
        Region(name=REGION_PLATE, description="Plaka yüzeyi", select=lambda bb, p: True, dim=2, expected_faces=1),
    ),
    analytic=None,
    characteristic_length=lambda p: p.plate_size / 10.0,
    default_element_ratio=(0.1, 0.25),
    default_bcs=(
        {"type": "fixed", "region": REGION_EDGE},
        {"type": "pressure", "region": REGION_PLATE, "magnitude": 0.1},
    ),
    tags=("crash", "kabuk", "patlama"),
    surface_only=True,
)
