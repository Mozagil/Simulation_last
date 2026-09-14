"""Şablon: kama kanallı mil, burulma (Grup 4).

Dairesel mil, orta boyda dikdörtgen kama yuvası (+y). Uçlar tam daire kalır
(end-milled keyseat). τ_max = Kt · TR/J; Kt Peterson yaklaşığı (fillet/D).
CAD'de fillet yok; r_fillet yalnız Kt içindir (varsayılan 0.02 D).
"""

from __future__ import annotations

import math

from pydantic import BaseModel, Field, model_validator

from app.templates.base import AnalyticInput, BBox, GeometryTemplate, Region, plane_at
from app.templates.torsion_shaft import polar_inertia

REGION_FIXED = "ankastre_uc"
REGION_TORQUE = "yuk_burulma"
REGION_KEYWAY = "kama_yuvasi"


class KeywayShaftParams(BaseModel):
    """Tüm boyutlar mm. Eksen x, daire yz, merkez orijin."""

    length: float = Field(120.0, gt=0, description="Mil boyu L (x)", json_schema_extra={"unit": "mm"})
    radius: float = Field(12.0, gt=0, description="Yarıçap R", json_schema_extra={"unit": "mm"})
    key_width: float = Field(5.0, gt=0, description="Kama genişliği w (z)", json_schema_extra={"unit": "mm"})
    key_depth: float = Field(3.0, gt=0, description="Kama derinliği h (radyal)", json_schema_extra={"unit": "mm"})
    fillet_radius: float = Field(
        0.0,
        ge=0,
        description="Kt için dip radyusu (0 → 0.02 D); geometride yok",
        json_schema_extra={"unit": "mm"},
    )

    @model_validator(mode="after")
    def _key(self) -> "KeywayShaftParams":
        if self.length < 4.0 * self.radius:
            raise ValueError("length en az 4 × radius olmalı (Saint-Venant).")
        if self.key_width >= 2.0 * self.radius:
            raise ValueError("key_width mil çapından küçük olmalı.")
        if self.key_depth >= self.radius:
            raise ValueError("key_depth yarıçaptan küçük olmalı.")
        if self.key_width > self.radius:
            raise ValueError("key_width ≤ radius (standart kama).")
        return self


def keyway_kt_torsion(diameter: float, fillet: float) -> float:
    """Peterson tarzı: kama yuvası burulma Kt, r/D küçüldükçe artar."""
    r = fillet if fillet > 0.0 else 0.02 * diameter
    rr = r / diameter
    kt = 2.0 + 0.18 / math.sqrt(max(rr, 0.004))
    return min(max(kt, 1.8), 5.0)


def _free_end_circle(bbox: BBox, params: BaseModel, tol: float = 0.15) -> bool:
    xmin, ymin, zmin, xmax, ymax, zmax = bbox
    length = float(getattr(params, "length"))
    rad = float(getattr(params, "radius"))
    if abs(xmin - length) > 1e-3 or abs(xmax - length) > 1e-3:
        return False
    dy, dz = ymax - ymin, zmax - zmin
    return abs(dy - 2.0 * rad) < rad * tol + 0.2 and abs(dz - 2.0 * rad) < rad * tol + 0.2


def _keyway_slot(bbox: BBox, params: BaseModel) -> bool:
    xmin, ymin, zmin, xmax, ymax, zmax = bbox
    p = params
    assert isinstance(p, KeywayShaftParams)
    L, R, w, h = p.length, p.radius, p.key_width, p.key_depth
    cx = 0.5 * (xmin + xmax)
    if not (0.25 * L < cx < 0.75 * L):
        return False
    # Yuva +y tarafında, z-span ≈ w
    dz = zmax - zmin
    if abs(dz - w) > w * 0.5 + 0.5:
        return False
    return ymax > R - h * 0.5


def _build(p: KeywayShaftParams) -> None:
    import gmsh

    shaft = gmsh.model.occ.addCylinder(0.0, 0.0, 0.0, p.length, 0.0, 0.0, p.radius)
    x1, x2 = 0.3 * p.length, 0.7 * p.length
    slot = gmsh.model.occ.addBox(
        x1,
        p.radius - p.key_depth,
        -p.key_width / 2.0,
        x2 - x1,
        p.key_depth + 1.0,
        p.key_width,
    )
    gmsh.model.occ.cut([(3, shaft)], [(3, slot)])


def _analytic(p: KeywayShaftParams, a: AnalyticInput) -> dict[str, float]:
    torque = a.force_n * p.radius
    polar = polar_inertia(p.radius)
    tau = torque * p.radius / polar
    kt = keyway_kt_torsion(2.0 * p.radius, p.fillet_radius)
    return {"max_von_mises": math.sqrt(3.0) * kt * tau}


KEYWAY_SHAFT = GeometryTemplate(
    id="keyway_shaft",
    name="Kama kanallı mil (burulma)",
    description=(
        "Dairesel mil, orta boyda dikdörtgen kama yuvası. Serbest uç çemberine "
        "teğetsel CLOAD; τ_max = Kt TR/J, von Mises = √3 τ_max."
    ),
    params_model=KeywayShaftParams,
    build=_build,
    regions=(
        Region(
            name=REGION_FIXED,
            description="Ankastre uç (x=0)",
            select=plane_at("x", 0.0),
        ),
        Region(
            name=REGION_TORQUE,
            description="Serbest uç dış çemberi (x=L) — teğetsel CLOAD",
            select=_free_end_circle,
            dim=1,
        ),
        Region(
            name=REGION_KEYWAY,
            description="Kama yuvası — gerilme yığılması",
            select=_keyway_slot,
        ),
    ),
    analytic=_analytic,
    default_bcs=(
        {"type": "fixed", "region": REGION_FIXED},
        # NOT: bkz. torsion_shaft — gerçek tork BC'si 0.4.7'de.
        {"type": "cload", "region": REGION_TORQUE, "fx": 0.0, "fy": 0.0, "fz": 500.0},
    ),
    tags=("grup4", "analitik", "burulma", "gerilme_yigilmasi"),
)
