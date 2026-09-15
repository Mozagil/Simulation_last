"""Şablon: çekme deneyi numunesi (dogbone), ISO 6892 / ASTM E8 oranları.

Eksen: x = çekme, y = genişlik (simetri y=0), z = kalınlık.
Varsayılan: ASTM E8 sac tipi (b=12.5, L0=50, B=20, R=12.5, tutamak 40 mm).

Fillet: ölçü kenarına (y=±b/2) teğet, tutamak genişliğine (y=±B/2) kesişen yay.
    Δ = (B − b) / 2
    dx = √(2 R Δ − Δ²)     (R > Δ/2)

Analitik: nominal ölçü gerilmesi σ = F / (b t). Fillet yığılması FEA'da
biraz üstüne çıkar. Deplasman kapalı formu (tüm boy) yok; 0.4.5 yalnız
max_von_mises.
"""

from __future__ import annotations

import math

from pydantic import BaseModel, Field, model_validator

from app.templates.base import AnalyticInput, BBox, GeometryTemplate, Region, plane_at

REGION_FIXED = "tutulan_uc"
REGION_LOAD = "yuk_cekme"
REGION_GAUGE = "olcu_alani"


class DogboneParams(BaseModel):
    """Tüm boyutlar mm. ASTM E8 sac tipi varsayılanları."""

    gauge_length: float = Field(
        50.0, gt=0, description="Ölçü boyu L0 (x, paralel kesit)", json_schema_extra={"unit": "mm", "symbol": "L0"}
    )
    gauge_width: float = Field(
        12.5, gt=0, description="Ölçü genişliği b", json_schema_extra={"unit": "mm", "symbol": "b"}
    )
    thickness: float = Field(
        3.0, gt=0, description="Kalınlık a (z)", json_schema_extra={"unit": "mm", "symbol": "a"}
    )
    grip_width: float = Field(
        20.0, gt=0, description="Tutamak genişliği B", json_schema_extra={"unit": "mm", "symbol": "B"}
    )
    grip_length: float = Field(
        40.0, gt=0, description="Tutamak boyu (her uç)", json_schema_extra={"unit": "mm", "symbol": "Lg"}
    )
    fillet_radius: float = Field(
        12.5, gt=0, description="Geçiş yarıçapı R", json_schema_extra={"unit": "mm", "symbol": "R"}
    )

    @model_validator(mode="after")
    def _proportions(self) -> "DogboneParams":
        if self.grip_width <= self.gauge_width:
            raise ValueError(
                f"grip_width ({self.grip_width}) gauge_width ({self.gauge_width}) değerinden büyük olmalı."
            )
        delta = (self.grip_width - self.gauge_width) / 2.0
        if self.fillet_radius <= delta / 2.0:
            raise ValueError(
                f"fillet_radius ({self.fillet_radius}) en az (B-b)/4 = {delta / 2.0:.3g} olmalı "
                "(yay tutamak genişliğine ulaşamaz)."
            )
        return self


def fillet_dx(p: DogboneParams) -> float:
    delta = (p.grip_width - p.gauge_width) / 2.0
    return math.sqrt(2.0 * p.fillet_radius * delta - delta * delta)


def total_length(p: DogboneParams) -> float:
    return 2.0 * p.grip_length + 2.0 * fillet_dx(p) + p.gauge_length


def _gauge_faces(bbox: BBox, params: BaseModel, tol: float = 1e-3) -> bool:
    """Paralel ölçü kenarları y=±b/2, uzunluk L0, kalınlık T."""
    xmin, ymin, zmin, xmax, ymax, zmax = bbox
    b = float(getattr(params, "gauge_width"))
    t = float(getattr(params, "thickness"))
    lc = float(getattr(params, "gauge_length"))
    if abs(ymax - ymin) > tol:
        return False
    if abs(abs(ymin) - b / 2.0) > tol:
        return False
    if abs((zmax - zmin) - t) > max(tol, t * 0.05):
        return False
    return abs((xmax - xmin) - lc) < max(0.05, lc * 0.02)


def _build(p: DogboneParams) -> None:
    import gmsh

    dx = fillet_dx(p)
    lg = p.grip_length
    lc = p.gauge_length
    b = p.gauge_width
    big = p.grip_width
    r = p.fillet_radius
    length = total_length(p)
    hb, hg = big / 2.0, b / 2.0

    def pt(x: float, y: float) -> int:
        return gmsh.model.occ.addPoint(x, y, 0.0)

    p1 = pt(0.0, hb)
    p2 = pt(lg, hb)
    p3 = pt(lg + dx, hg)
    p4 = pt(lg + dx + lc, hg)
    p5 = pt(lg + dx + lc + dx, hb)
    p6 = pt(length, hb)
    p7 = pt(length, -hb)
    p8 = pt(lg + dx + lc + dx, -hb)
    p9 = pt(lg + dx + lc, -hg)
    p10 = pt(lg + dx, -hg)
    p11 = pt(lg, -hb)
    p12 = pt(0.0, -hb)
    cu1 = pt(lg + dx, hg + r)
    cu2 = pt(lg + dx + lc, hg + r)
    cb1 = pt(lg + dx, -(hg + r))
    cb2 = pt(lg + dx + lc, -(hg + r))

    l1 = gmsh.model.occ.addLine(p1, p2)
    a1 = gmsh.model.occ.addCircleArc(p2, cu1, p3)
    l2 = gmsh.model.occ.addLine(p3, p4)
    a2 = gmsh.model.occ.addCircleArc(p4, cu2, p5)
    l3 = gmsh.model.occ.addLine(p5, p6)
    l4 = gmsh.model.occ.addLine(p6, p7)
    l5 = gmsh.model.occ.addLine(p7, p8)
    a3 = gmsh.model.occ.addCircleArc(p8, cb2, p9)
    l6 = gmsh.model.occ.addLine(p9, p10)
    a4 = gmsh.model.occ.addCircleArc(p10, cb1, p11)
    l7 = gmsh.model.occ.addLine(p11, p12)
    l8 = gmsh.model.occ.addLine(p12, p1)
    loop = gmsh.model.occ.addCurveLoop([l1, a1, l2, a2, l3, l4, l5, a3, l6, a4, l7, l8])
    surf = gmsh.model.occ.addPlaneSurface([loop])
    gmsh.model.occ.extrude([(2, surf)], 0.0, 0.0, p.thickness)
    # Yay merkez noktaları katıya ait değil; sınır kutusunu şişirmesinler.
    gmsh.model.occ.remove([(0, cu1), (0, cu2), (0, cb1), (0, cb2)], recursive=False)


def _analytic(p: DogboneParams, a: AnalyticInput) -> dict[str, float]:
    """Nominal ölçü gerilmesi [MPa]."""
    area = p.gauge_width * p.thickness
    return {"max_von_mises": a.force_n / area}


DOGBONE = GeometryTemplate(
    id="dogbone",
    name="Çekme numunesi (dogbone)",
    description=(
        "ISO 6892 / ASTM E8 oranlı sac tipi çekme numunesi. Yük tutamak "
        "uçlarına uygulanır; analitik referans nominal ölçü gerilmesi F/(b·t)."
    ),
    params_model=DogboneParams,
    build=_build,
    regions=(
        Region(
            name=REGION_FIXED,
            description="Sol tutamak ucu (x=0)",
            select=plane_at("x", 0.0),
            expected_faces=1,
        ),
        Region(
            name=REGION_LOAD,
            description="Sağ tutamak ucu (x=L) — CLOAD +x",
            select=plane_at("x", total_length),
            expected_faces=1,
        ),
        Region(
            name=REGION_GAUGE,
            description="Ölçü kesiti kenarları (y=±b/2, boy L0)",
            select=_gauge_faces,
            expected_faces=2,
        ),
    ),
    analytic=_analytic,
    default_bcs=(
        {"type": "fixed", "region": REGION_FIXED},
        # σ_nom ≈ 200 MPa ölçü kesitinde (b=12.5, a=3): F = 7.5 kN
        {"type": "cload", "region": REGION_LOAD, "fx": 7500.0, "fy": 0.0, "fz": 0.0},
    ),
    tags=("grup1", "analitik", "cekme"),
)
