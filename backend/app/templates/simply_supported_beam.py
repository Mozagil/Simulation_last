"""Şablon: basit mesnetli kiriş, dikdörtgen kesit (Grup 1).

Aynı eksen yerleşimi ankastre kirişle: x=L, y=T (yük/eğilme), z=W.
Sol uç x=0 ve sağ uç x=L mesnet.

`yuk_orta` üstte x=L/2 kenarıdır (genişlik boyunca çizgi). 3B solidde
kiriş teorisindeki "point load"ın karşılığı yüzey şeridi değil bu kenardır;
CLOAD kenar düğümlerine toplam F olarak bölünür.
`yuk_yayili` isteğe bağlı yayılı yük için üst yüzler (analitik tablo CLOAD
orta-nokta formülünü kullanır).
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from app.templates.base import AnalyticInput, BBox, GeometryTemplate, Region, plane_at

REGION_LEFT = "mesnet_sol"
REGION_RIGHT = "mesnet_sag"
REGION_MID_LOAD = "yuk_orta"
REGION_UDL = "yuk_yayili"


class SimplySupportedBeamParams(BaseModel):
    """Tüm boyutlar mm."""

    length: float = Field(500.0, gt=0, description="Kiriş uzunluğu L (x)", json_schema_extra={"unit": "mm"})
    thickness: float = Field(10.0, gt=0, description="Kesit kalınlığı T (y, yük yönü)", json_schema_extra={"unit": "mm"})
    width: float = Field(50.0, gt=0, description="Kesit genişliği W (z)", json_schema_extra={"unit": "mm"})

    @model_validator(mode="after")
    def _beam_like(self) -> "SimplySupportedBeamParams":
        if self.length < 5 * self.thickness:
            raise ValueError(
                f"length ({self.length}) en az 5 x thickness ({self.thickness}) olmalı; "
                "daha kısa kirişte kiriş teorisi (analitik referans) geçersiz."
            )
        return self


def _top_mid_line(bbox: BBox, params: BaseModel, tol: float = 1e-4) -> bool:
    """x=L/2, y=T, z boyunca uzanan üst kenar."""
    xmin, ymin, zmin, xmax, ymax, zmax = bbox
    thickness = float(getattr(params, "thickness"))
    length = float(getattr(params, "length"))
    width = float(getattr(params, "width"))
    if abs(ymin - thickness) > tol or abs(ymax - thickness) > tol:
        return False
    mid = length / 2.0
    if abs(xmin - mid) > tol or abs(xmax - mid) > tol:
        return False
    return (zmax - zmin) > width * 0.5


def _build(p: SimplySupportedBeamParams) -> None:
    import gmsh

    box = gmsh.model.occ.addBox(0.0, 0.0, 0.0, p.length, p.thickness, p.width)
    p1 = gmsh.model.occ.addPoint(p.length / 2.0, p.thickness, 0.0)
    p2 = gmsh.model.occ.addPoint(p.length / 2.0, p.thickness, p.width)
    line = gmsh.model.occ.addLine(p1, p2)
    gmsh.model.occ.fragment([(3, box)], [(1, line)])


def _analytic(p: SimplySupportedBeamParams, a: AnalyticInput) -> dict[str, float]:
    """Birimler: mm, N, MPa. E Pa gelir. Varsayılan: orta nokta tekil F."""
    e_mpa = a.youngs_modulus_pa / 1e6
    inertia = p.width * p.thickness**3 / 12.0
    f = a.force_n
    length = p.length
    if a.distributed:
        tip = 5.0 * f * length**3 / (384.0 * e_mpa * inertia)
        moment = f * length / 8.0
    else:
        tip = f * length**3 / (48.0 * e_mpa * inertia)
        moment = f * length / 4.0
    bending_stress = moment * (p.thickness / 2.0) / inertia
    return {"max_displacement": tip, "max_von_mises": bending_stress}


SIMPLY_SUPPORTED_BEAM = GeometryTemplate(
    id="simply_supported_beam",
    name="Basit mesnetli kiriş (dikdörtgen kesit)",
    description=(
        "İki ucu basit mesnetli dikdörtgen kesitli kiriş. Yük, açıklık ortasında "
        "üst kenara uygulanan tekil kuvvettir (point load). Kiriş teorisi: "
        "δ = FL³/48EI."
    ),
    params_model=SimplySupportedBeamParams,
    build=_build,
    regions=(
        Region(
            name=REGION_LEFT,
            description="Sol mesnet (x=0) — düşey destek",
            select=plane_at("x", 0.0),
            expected_faces=1,
        ),
        Region(
            name=REGION_RIGHT,
            description="Sağ mesnet (x=L) — düşey destek",
            select=plane_at("x", lambda p: p.length),
            expected_faces=1,
        ),
        Region(
            name=REGION_MID_LOAD,
            description="Açıklık ortası üst kenar — tekil yük -y (CLOAD, kenar)",
            select=_top_mid_line,
            dim=1,
            expected_faces=1,
        ),
        Region(
            name=REGION_UDL,
            description="Üst yüzeyler (y=T) — isteğe bağlı yayılı yük",
            select=plane_at("y", lambda p: p.thickness),
            expected_faces=2,
        ),
    ),
    analytic=_analytic,
    tags=("grup1", "analitik", "egilme"),
)
