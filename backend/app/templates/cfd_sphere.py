"""Şablon: küre — dış akış doğrulaması (Faz 2.6a).

D çaplı dolu küre, merkez orijinde. CFD rüzgâr tünelinde tek yama (``kure``).
Düşük Reynolds sayısında (Re ≲ 200) daimi, eksenel simetrik laminer akış —
sürükleme katsayısı Schiller–Naumann korelasyonuyla karşılaştırılır
(``app.postprocess.sphere_drag``). Yapısal BC'si yok (etiket ``cfd``).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.templates.base import GeometryTemplate, Region

REGION_SPHERE = "kure"


class CfdSphereParams(BaseModel):
    """Boyut mm."""

    diameter: float = Field(100.0, gt=0, description="Küre çapı D", json_schema_extra={"unit": "mm", "symbol": "D"})


def _build(p: CfdSphereParams) -> None:
    import gmsh

    gmsh.model.occ.addSphere(0.0, 0.0, 0.0, p.diameter / 2.0)


CFD_SPHERE = GeometryTemplate(
    id="cfd_sphere",
    name="Küre — dış akış doğrulaması",
    description=(
        "D çaplı küre (merkez orijinde). Düşük Re'de daimi laminer dış akış; sürükleme katsayısı "
        "Schiller–Naumann korelasyonuyla karşılaştırılır (V-C2)."
    ),
    params_model=CfdSphereParams,
    build=_build,
    regions=(Region(name=REGION_SPHERE, description="Küre yüzeyi", select=lambda bb, p: True, dim=2, expected_faces=1),),
    analytic=None,
    characteristic_length=lambda p: p.diameter,
    default_element_ratio=(0.05, 0.1),
    default_bcs=(),
    tags=("cfd", "dogrulama"),
)
