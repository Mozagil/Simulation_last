"""Şablon: içten basınçlı kalın cidarlı boru (Lamé).

Eksen x = boru boyu. İç yarıçap a, dış yarıçap b, açık uç (düzlem gerilme).
İç cidarda: σ_r = −p, σ_θ = p (a²+b²)/(b²−a²)
von Mises (σ_z=0): √(σ_r² + σ_θ² − σ_r σ_θ)
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from app.templates.base import AnalyticInput, BBox, GeometryTemplate, Region, plane_at

REGION_FIXED = "tutulan_uc"
REGION_INNER = "ic_cidar"
REGION_OUTER = "dis_cidar"


class ThickWalledTubeParams(BaseModel):
    """Tüm boyutlar mm."""

    length: float = Field(100.0, gt=0, description="Boru boyu L (x)", json_schema_extra={"unit": "mm"})
    inner_radius: float = Field(10.0, gt=0, description="İç yarıçap a", json_schema_extra={"unit": "mm"})
    outer_radius: float = Field(20.0, gt=0, description="Dış yarıçap b", json_schema_extra={"unit": "mm"})

    @model_validator(mode="after")
    def _thick_wall(self) -> "ThickWalledTubeParams":
        if self.outer_radius <= self.inner_radius:
            raise ValueError(
                f"outer_radius ({self.outer_radius}) inner_radius ({self.inner_radius}) "
                "değerinden büyük olmalı."
            )
        # İnce cidar (b-a << a) membran teorisine kayar; Lamé hâlâ geçerli ama
        # "kalın cidar" iddiası için minimum oran.
        if self.outer_radius < 1.2 * self.inner_radius:
            raise ValueError(
                f"outer_radius ({self.outer_radius}) en az 1.2 x inner_radius "
                f"({self.inner_radius}) olmalı (kalın cidar)."
            )
        return self


def _cyl_wall(radius_attr: str, tol: float = 0.08):
    def _select(bbox: BBox, params: BaseModel) -> bool:
        xmin, ymin, zmin, xmax, ymax, zmax = bbox
        length = float(getattr(params, "length"))
        rad = float(getattr(params, radius_attr))
        dx, dy, dz = xmax - xmin, ymax - ymin, zmax - zmin
        if abs(dx - length) > max(0.05, length * 0.02):
            return False
        return abs(dy - 2.0 * rad) < rad * tol + 0.2 and abs(dz - 2.0 * rad) < rad * tol + 0.2

    return _select


def _build(p: ThickWalledTubeParams) -> None:
    import gmsh

    outer = gmsh.model.occ.addCylinder(0.0, 0.0, 0.0, p.length, 0.0, 0.0, p.outer_radius)
    inner = gmsh.model.occ.addCylinder(0.0, 0.0, 0.0, p.length, 0.0, 0.0, p.inner_radius)
    gmsh.model.occ.cut([(3, outer)], [(3, inner)])


def _analytic(p: ThickWalledTubeParams, a: AnalyticInput) -> dict[str, float]:
    """İç cidar von Mises [MPa]; p [MPa]."""
    press = a.pressure_mpa
    aa, bb = p.inner_radius**2, p.outer_radius**2
    hoop = press * (aa + bb) / (bb - aa)
    radial = -press
    vm = (radial**2 + hoop**2 - radial * hoop) ** 0.5
    return {"max_von_mises": vm}


THICK_WALLED_TUBE = GeometryTemplate(
    id="thick_walled_tube",
    name="Kalın cidarlı boru (iç basınç)",
    description=(
        "Açık uçlu kalın cidarlı silindir, iç basınç. Lamé çözümü: iç cidarda "
        "maksimum hoop ve von Mises. Pressure BC → ic_cidar."
    ),
    params_model=ThickWalledTubeParams,
    build=_build,
    regions=(
        Region(
            name=REGION_FIXED,
            description="Tutulan uç (x=0, halka)",
            select=plane_at("x", 0.0),
            expected_faces=1,
        ),
        Region(
            name=REGION_INNER,
            description="İç cidar — iç basınç (Pressure)",
            select=_cyl_wall("inner_radius"),
            expected_faces=1,
        ),
        Region(
            name=REGION_OUTER,
            description="Dış cidar",
            select=_cyl_wall("outer_radius"),
            expected_faces=1,
        ),
    ),
    analytic=_analytic,
    tags=("grup1", "analitik", "lame"),
)
