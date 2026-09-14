"""Şablon: merkezi delikli plaka, çekme (Grup 1).

Eksen: x = yük / uzunluk H, y = genişlik W, z = kalınlık T.
Delik merkezde, çap d, kalınlık boyunca.

Analitik: Heywood net Kt (Howland sonlu genişlik; d/W → 0 iken Kirsch Kt=3).
    K_tn = 2 + (1 - d/W)³
    σ_max = K_tn * F / ((W - d) T)
Deplasman kapalı formu yok; 0.4.5 yalnız max_von_mises karşılaştırır.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from app.templates.base import AnalyticInput, BBox, GeometryTemplate, Region, plane_at

REGION_FIXED = "tutulan_uc"
REGION_LOAD = "yuk_cekme"
REGION_HOLE = "delik_cidari"


class PlateWithHoleParams(BaseModel):
    """Tüm boyutlar mm."""

    height: float = Field(
        200.0, gt=0, description="Plaka uzunluğu H (çekme yönü, x)", json_schema_extra={"unit": "mm"}
    )
    width: float = Field(
        100.0, gt=0, description="Plaka genişliği W (y)", json_schema_extra={"unit": "mm"}
    )
    thickness: float = Field(
        5.0, gt=0, description="Kalınlık T (z)", json_schema_extra={"unit": "mm"}
    )
    diameter: float = Field(
        20.0, gt=0, description="Delik çapı d", json_schema_extra={"unit": "mm"}
    )

    @model_validator(mode="after")
    def _hole_fits(self) -> "PlateWithHoleParams":
        if self.diameter >= self.width:
            raise ValueError(
                f"diameter ({self.diameter}) width ({self.width}) değerinden küçük olmalı."
            )
        if self.diameter >= self.height:
            raise ValueError(
                f"diameter ({self.diameter}) height ({self.height}) değerinden küçük olmalı."
            )
        # Kenar mesafesi: delik cidarı plaka kenarına yapışmasın.
        if self.width < 2.0 * self.diameter:
            raise ValueError(
                f"width ({self.width}) en az 2 x diameter ({self.diameter}) olmalı "
                "(delik kenara çok yakın; Kirsch/Heywood far-field varsayımı bozulur)."
            )
        if self.height < 3.0 * self.diameter:
            raise ValueError(
                f"height ({self.height}) en az 3 x diameter ({self.diameter}) olmalı "
                "(çekme uçları deliğe çok yakın)."
            )
        return self


def heywood_kt_net(diameter: float, width: float) -> float:
    """Net kesite göre gerilme yığılması; d/W→0 iken 3 (Kirsch)."""
    lam = diameter / width
    return 2.0 + (1.0 - lam) ** 3


def _hole_wall(bbox: BBox, params: BaseModel, tol: float = 0.08) -> bool:
    xmin, ymin, zmin, xmax, ymax, zmax = bbox
    d = float(getattr(params, "diameter"))
    t = float(getattr(params, "thickness"))
    h = float(getattr(params, "height"))
    w = float(getattr(params, "width"))
    dx, dy, dz = xmax - xmin, ymax - ymin, zmax - zmin
    if abs(dx - d) > d * tol + 1e-3:
        return False
    if abs(dy - d) > d * tol + 1e-3:
        return False
    if abs(dz - t) > max(t * 0.05, 1e-3):
        return False
    cx, cy = 0.5 * (xmin + xmax), 0.5 * (ymin + ymax)
    return abs(cx - h / 2.0) < d * 0.25 and abs(cy - w / 2.0) < d * 0.25


def _build(p: PlateWithHoleParams) -> None:
    import gmsh

    box = gmsh.model.occ.addBox(0.0, 0.0, 0.0, p.height, p.width, p.thickness)
    cyl = gmsh.model.occ.addCylinder(
        p.height / 2.0,
        p.width / 2.0,
        -1.0,
        0.0,
        0.0,
        p.thickness + 2.0,
        p.diameter / 2.0,
    )
    gmsh.model.occ.cut([(3, box)], [(3, cyl)])


def _analytic(p: PlateWithHoleParams, a: AnalyticInput) -> dict[str, float]:
    """σ_max [MPa]; F [N], mm. E kullanılmaz (Kirsch gerilmesi E'den bağımsız)."""
    net_area = (p.width - p.diameter) * p.thickness
    sigma_net = a.force_n / net_area
    sigma_max = heywood_kt_net(p.diameter, p.width) * sigma_net
    return {"max_von_mises": sigma_max}


PLATE_WITH_HOLE = GeometryTemplate(
    id="plate_with_hole",
    name="Delikli plaka (çekme)",
    description=(
        "Merkezi dairesel delikli dikdörtgen plaka, x yönünde çekme. "
        "Sonsuz plaka limiti Kirsch Kt=3; sonlu genişlikte Heywood net Kt kullanılır."
    ),
    params_model=PlateWithHoleParams,
    build=_build,
    regions=(
        Region(
            name=REGION_FIXED,
            description="Tutulan uç (x=0)",
            select=plane_at("x", 0.0),
            expected_faces=1,
        ),
        Region(
            name=REGION_LOAD,
            description="Çekme ucu (x=H) — CLOAD +x",
            select=plane_at("x", lambda p: p.height),
            expected_faces=1,
        ),
        Region(
            name=REGION_HOLE,
            description="Delik cidarı — gerilme yığılması (BC değil)",
            select=_hole_wall,
            expected_faces=1,
        ),
    ),
    analytic=_analytic,
    tags=("grup1", "analitik", "gerilme_yigilmasi"),
)
