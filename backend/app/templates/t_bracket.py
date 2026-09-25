"""Şablon: T-braket — duvara bağlı sırt plakası + konsol raf, isteğe bağlı kaburga (Grup 3).

Yerleşim: sırt plakası x∈[−t, 0] (duvar yüzü x=−t ankastre), raf plakası
x∈[0, a] · y∈[h/2 − t/2, h/2 + t/2] (sırtın orta yüksekliğinde), genişlik z∈[0, w].
Kaburga (`rib_kind="gusset"`): rafın ALTINDA, z ortasında, üçgen prizma
(x: 0→a·r_frac, y: raf altından aşağı a·r_frac), kalınlık `rib_thickness`.

Analitik referans YALNIZ kaburgasız raf içindir (dikdörtgen kesitli konsol,
I = w t³/12). Kaburgalı halde FEA daha rijit çıkar — sapma beklenen sonuç,
hata değil (korpus lineer analitik kapısı bunu `analytic_warn` sayar; kaburgalı
DOE için `require_analytic_ok=False` kullanılmalı).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.templates.base import AnalyticInput, GeometryTemplate, Region, plane_at
from app.templates.beam_section import cantilever_fl_over_ei

REGION_FIXED = "duvar_yuzu"
REGION_LOAD = "raf_ucu"


class TBracketParams(BaseModel):
    """Tüm boyutlar mm."""

    back_height: float = Field(120.0, gt=0, description="Sırt plakası yüksekliği h (y)", json_schema_extra={"unit": "mm", "symbol": "h"})
    width: float = Field(80.0, gt=0, description="Genişlik w (z)", json_schema_extra={"unit": "mm", "symbol": "w"})
    thickness: float = Field(8.0, gt=0, description="Plaka kalınlığı t (sırt ve raf)", json_schema_extra={"unit": "mm", "symbol": "t"})
    arm_length: float = Field(100.0, gt=0, description="Raf uzunluğu a (x)", json_schema_extra={"unit": "mm", "symbol": "a"})
    rib_kind: Literal["none", "gusset"] = Field("none", description="Kaburga: yok / üçgen destek")
    rib_thickness: float = Field(6.0, gt=0, description="Kaburga kalınlığı tr (z) — yalnız gusset", json_schema_extra={"unit": "mm", "symbol": "tr"})
    rib_fraction: float = Field(0.5, gt=0, le=1.0, description="Kaburga boyu / raf boyu (0–1)", json_schema_extra={"unit": "-", "symbol": "rf"})

    @model_validator(mode="after")
    def _shape(self) -> "TBracketParams":
        if self.back_height <= 3.0 * self.thickness:
            raise ValueError("back_height en az 3 × thickness olmalı (raf sırtın içinde kalmalı).")
        if self.arm_length < 3.0 * self.thickness:
            raise ValueError("arm_length en az 3 × thickness olmalı (plaka kabulü).")
        if self.rib_kind == "gusset":
            if self.rib_thickness >= self.width:
                raise ValueError("rib_thickness genişlikten küçük olmalı.")
            if self.rib_fraction * self.arm_length >= (self.back_height - self.thickness) / 2.0:
                raise ValueError("Kaburga sırt plakasının altından taşıyor: rib_fraction küçültün.")
        return self


def _build(p: TBracketParams) -> None:
    import gmsh

    t = p.thickness
    y0 = p.back_height / 2.0 - t / 2.0  # raf alt yüzü
    back = gmsh.model.occ.addBox(-t, 0.0, 0.0, t, p.back_height, p.width)
    arm = gmsh.model.occ.addBox(0.0, y0, 0.0, p.arm_length, t, p.width)
    parts = [(3, arm)]
    if p.rib_kind == "gusset":
        s = p.rib_fraction * p.arm_length
        zc = p.width / 2.0
        tr = p.rib_thickness
        pts = [
            gmsh.model.occ.addPoint(0.0, y0, zc - tr / 2.0),
            gmsh.model.occ.addPoint(s, y0, zc - tr / 2.0),
            gmsh.model.occ.addPoint(0.0, y0 - s, zc - tr / 2.0),
        ]
        lines = [
            gmsh.model.occ.addLine(pts[0], pts[1]),
            gmsh.model.occ.addLine(pts[1], pts[2]),
            gmsh.model.occ.addLine(pts[2], pts[0]),
        ]
        loop = gmsh.model.occ.addCurveLoop(lines)
        face = gmsh.model.occ.addPlaneSurface([loop])
        ext = gmsh.model.occ.extrude([(2, face)], 0.0, 0.0, tr)
        parts += [e for e in ext if e[0] == 3]
    gmsh.model.occ.fuse([(3, back)], parts)


def _analytic(p: TBracketParams, a: AnalyticInput) -> dict[str, float]:
    inertia = p.width * p.thickness**3 / 12.0
    return cantilever_fl_over_ei(p.arm_length, inertia, p.thickness / 2.0, a.force_n, a.youngs_modulus_pa)


T_BRACKET = GeometryTemplate(
    id="t_bracket",
    name="T-braket (kaburgalı / kaburgasız)",
    description=(
        "Duvara bağlı sırt plakası ve ortasından çıkan konsol raf; isteğe bağlı üçgen "
        "kaburga. Analitik referans kaburgasız raf için."
    ),
    params_model=TBracketParams,
    build=_build,
    regions=(
        Region(
            name=REGION_FIXED,
            description="Sırt plakasının duvar yüzü (x=−t) — ankastre",
            select=plane_at("x", lambda p: -p.thickness),
            expected_faces=1,
        ),
        Region(
            name=REGION_LOAD,
            description="Raf ucu (x=a) — CLOAD −y",
            select=plane_at("x", lambda p: p.arm_length),
            expected_faces=1,
        ),
    ),
    analytic=_analytic,
    characteristic_length=lambda p: p.thickness,
    default_element_ratio=(0.5, 1.0),
    default_bcs=(
        {"type": "fixed", "region": REGION_FIXED},
        {"type": "cload", "region": REGION_LOAD, "fx": 0.0, "fy": -500.0, "fz": 0.0},
    ),
    tags=("grup3", "analitik", "egilme", "braket"),
)
