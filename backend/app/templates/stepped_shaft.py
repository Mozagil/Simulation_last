"""Şablon: kademeli mil — çap geçişinde omuz filleti, uç yüküyle eğilme (Grup 3).

Eksen x. Büyük çap x∈[0, L1] (yarıçap R1), küçük çap x∈[L1, L1+L2] (R2 < R1),
omuz kenarında fillet r. Büyük uç (x=0) ankastre, küçük uç yüzeyine −y CLOAD.

Analitik referans:
- σ_max = Kt · M c / I, M = F·L2 (omuzda moment), küçük kesitte (I = πR2⁴/4).
  Kt eğilmede kademeli mil için Peterson/Norton üstel uydurması
  Kt = A (r/d)^b, A ve b D/d'ye göre tablo (bkz. `stepped_shaft_kt_bending`).
- δ_uç = F/E · [ (L³ − L2³)/(3 I1) + L2³/(3 I2) ], L = L1 + L2
  (Castigliano; ∫ (L−x)²/I(x) dx).

Fillet burada GEOMETRİDE var (kama kanalındakinin aksine): kök filleti
ölçümü (TODO 6) tepe gerilmenin fillet yarıçapını çözecek yerel mesh
istediğini gösterdi — `characteristic_length = r`, eleman oranı 0.5–1.0.
"""

from __future__ import annotations

import math

from pydantic import BaseModel, Field, model_validator

from app.templates.base import AnalyticInput, GeometryTemplate, Region, plane_at

REGION_FIXED = "ankastre_uc"
REGION_LOAD = "yuk_yuzeyi"

#: D/d → (A, b) — Norton, "Machine Design", kademeli mil eğilme (Peterson
#: eğrilerine üstel uydurma). 0.01 ≤ r/d ≤ 0.3 aralığında geçerli.
_KT_TABLE: tuple[tuple[float, float, float], ...] = (
    (1.01, 0.91938, -0.17032),
    (1.02, 0.96048, -0.17711),
    (1.03, 0.98061, -0.18381),
    (1.05, 0.98137, -0.19653),
    (1.07, 0.97527, -0.20958),
    (1.10, 0.95120, -0.23757),
    (1.20, 0.97098, -0.21796),
    (1.50, 0.93836, -0.25759),
    (2.00, 0.90879, -0.28598),
    (3.00, 0.89334, -0.30860),
    (6.00, 0.87868, -0.33243),
)


def stepped_shaft_kt_bending(big_d: float, small_d: float, fillet: float) -> float:
    """Eğilme Kt; D/d tabloda doğrusal ara değer, uçlarda sabit."""
    ratio = big_d / small_d
    rd = min(max(fillet / small_d, 0.01), 0.3)
    if ratio <= _KT_TABLE[0][0]:
        a, b = _KT_TABLE[0][1:]
    elif ratio >= _KT_TABLE[-1][0]:
        a, b = _KT_TABLE[-1][1:]
    else:
        for (r0, a0, b0), (r1, a1, b1) in zip(_KT_TABLE, _KT_TABLE[1:]):
            if r0 <= ratio <= r1:
                w = (ratio - r0) / (r1 - r0)
                a, b = a0 + w * (a1 - a0), b0 + w * (b1 - b0)
                break
    return max(1.0, a * rd**b)


class SteppedShaftParams(BaseModel):
    """Tüm boyutlar mm."""

    big_radius: float = Field(15.0, gt=0, description="Büyük yarıçap R1 (x∈[0,L1])", json_schema_extra={"unit": "mm", "symbol": "R1"})
    small_radius: float = Field(10.0, gt=0, description="Küçük yarıçap R2", json_schema_extra={"unit": "mm", "symbol": "R2"})
    big_length: float = Field(60.0, gt=0, description="Büyük çap boyu L1", json_schema_extra={"unit": "mm", "symbol": "L1"})
    small_length: float = Field(60.0, gt=0, description="Küçük çap boyu L2", json_schema_extra={"unit": "mm", "symbol": "L2"})
    fillet_radius: float = Field(2.0, gt=0, description="Omuz fillet yarıçapı r", json_schema_extra={"unit": "mm", "symbol": "r"})

    @model_validator(mode="after")
    def _step(self) -> "SteppedShaftParams":
        if self.small_radius >= self.big_radius:
            raise ValueError("small_radius, big_radius'tan küçük olmalı (kademe yoksa düz mil kullanın).")
        step = self.big_radius - self.small_radius
        if self.fillet_radius >= step:
            raise ValueError(f"fillet_radius ({self.fillet_radius}) kademe yüksekliğinden ({step}) küçük olmalı.")
        if self.fillet_radius >= min(self.big_length, self.small_length) / 2.0:
            raise ValueError("fillet_radius kademe boylarına göre çok büyük.")
        if self.small_length < 3.0 * self.small_radius:
            raise ValueError("small_length en az 3 × small_radius olmalı (kiriş kabulü).")
        return self


def _build(p: SteppedShaftParams) -> None:
    import gmsh

    big = gmsh.model.occ.addCylinder(0.0, 0.0, 0.0, p.big_length, 0.0, 0.0, p.big_radius)
    small = gmsh.model.occ.addCylinder(p.big_length, 0.0, 0.0, p.small_length, 0.0, 0.0, p.small_radius)
    fused, _ = gmsh.model.occ.fuse([(3, big)], [(3, small)])
    gmsh.model.occ.synchronize()
    # Omuz kenarı: x = L1 düzleminde, çapı 2·R2 olan çember.
    eps = 1e-6
    d2 = 2.0 * p.small_radius
    edges = []
    for _d, tag in gmsh.model.getEntities(dim=1):
        x0, y0, z0, x1, y1, z1 = gmsh.model.getBoundingBox(1, tag)
        if (abs(x0 - p.big_length) < eps and abs(x1 - p.big_length) < eps
                and abs((y1 - y0) - d2) < 1e-3 and abs((z1 - z0) - d2) < 1e-3):
            edges.append(tag)
    if not edges:
        raise RuntimeError("Omuz kenarı bulunamadı.")
    gmsh.model.occ.fillet([t for _d, t in fused], edges, [p.fillet_radius], removeVolume=True)


def _analytic(p: SteppedShaftParams, a: AnalyticInput) -> dict[str, float]:
    e_mpa = a.youngs_modulus_pa / 1e6
    i1 = math.pi * p.big_radius**4 / 4.0
    i2 = math.pi * p.small_radius**4 / 4.0
    total = p.big_length + p.small_length
    tip = a.force_n / e_mpa * ((total**3 - p.small_length**3) / (3.0 * i1) + p.small_length**3 / (3.0 * i2))
    kt = stepped_shaft_kt_bending(2.0 * p.big_radius, 2.0 * p.small_radius, p.fillet_radius)
    sigma = kt * a.force_n * p.small_length * p.small_radius / i2
    return {"max_displacement": tip, "max_von_mises": sigma}


STEPPED_SHAFT = GeometryTemplate(
    id="stepped_shaft",
    name="Kademeli mil (omuz filleti)",
    description=(
        "İki çaplı mil, omuzda fillet; büyük uç ankastre, küçük uçtan −y yük. "
        "Kt (Peterson/Norton) ile omuz gerilmesi, Castigliano ile uç sehimi."
    ),
    params_model=SteppedShaftParams,
    build=_build,
    regions=(
        Region(name=REGION_FIXED, description="Büyük uç (x=0) — ankastre", select=plane_at("x", 0.0), expected_faces=1),
        Region(
            name=REGION_LOAD,
            description="Küçük uç (x=L1+L2) — CLOAD −y",
            select=plane_at("x", lambda p: p.big_length + p.small_length),
            expected_faces=1,
        ),
    ),
    analytic=_analytic,
    # Yığılma fillet yarıçapıyla ölçeklenir; mesh onu çözmeli.
    characteristic_length=lambda p: p.fillet_radius,
    default_element_ratio=(0.5, 1.0),
    default_bcs=(
        {"type": "fixed", "region": REGION_FIXED},
        {"type": "cload", "region": REGION_LOAD, "fx": 0.0, "fy": -500.0, "fz": 0.0},
    ),
    tags=("grup3", "analitik", "egilme", "fillet", "mil"),
)
