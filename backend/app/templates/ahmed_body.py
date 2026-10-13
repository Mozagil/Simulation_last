"""Şablon: Ahmed gövdesi — otomotiv dış akış doğrulaması (Faz 2.6c, V-C4).

Ahmed, Ramm & Faltin (1984, SAE 840300) basitleştirilmiş araç gövdesi: L × W × H
kutu, ön dört kenarda R yarıçap, arkada üst kenarda φ açılı, S uzunluklu eğik
yüzey. Gövde zeminden G yukarıda (zemin CFD tünelinde duvar). Eksen +x (burun
x = 0), y genişlik (simetrik), z düşey (zemin z = 0).

Sadeleştirme: deneydeki dört taşıyıcı bacak (Ø30 mm) modellenmez — veri notu.
Deney Cd (A_ref = W·H = 0.112 m²): φ 0° 0.250, 12.5° 0.230, 25° 0.285,
30° 0.378, 35° 0.260 (``app.postprocess.ahmed_drag``).
"""

from __future__ import annotations

import math

from pydantic import BaseModel, Field, model_validator

from app.templates.base import GeometryTemplate, Region

REGION_BODY = "ahmed"


class AhmedParams(BaseModel):
    """Boyutlar mm, açı derece. Varsayılanlar özgün Ahmed gövdesi."""

    slant_angle_deg: float = Field(25.0, ge=0, le=40, description="Arka eğim açısı φ", json_schema_extra={"unit": "°", "symbol": "φ"})
    length: float = Field(1044.0, gt=0, description="Boy L", json_schema_extra={"unit": "mm", "symbol": "L"})
    width: float = Field(389.0, gt=0, description="Genişlik W", json_schema_extra={"unit": "mm", "symbol": "W"})
    height: float = Field(288.0, gt=0, description="Yükseklik H", json_schema_extra={"unit": "mm", "symbol": "H"})
    front_radius: float = Field(100.0, gt=0, description="Ön kenar yarıçapı R", json_schema_extra={"unit": "mm", "symbol": "R"})
    slant_length: float = Field(222.0, gt=0, description="Eğik yüzey uzunluğu S", json_schema_extra={"unit": "mm", "symbol": "S"})
    ground_clearance: float = Field(50.0, gt=0, description="Zemin açıklığı G", json_schema_extra={"unit": "mm", "symbol": "G"})

    @model_validator(mode="after")
    def _ok(self) -> "AhmedParams":
        if 2 * self.front_radius >= min(self.width, self.height):
            raise ValueError("Ön yarıçap R, W/2 ve H/2'den küçük olmalı.")
        a = math.radians(self.slant_angle_deg)
        if self.slant_length * math.cos(a) >= self.length - self.front_radius:
            raise ValueError("Eğik yüzey gövde boyuna sığmalı.")
        if self.slant_length * math.sin(a) >= self.height:
            raise ValueError("Eğik yüzeyin düşüşü H'den küçük olmalı.")
        return self


def _build(p: AhmedParams) -> None:
    import gmsh

    occ = gmsh.model.occ
    z0 = p.ground_clearance
    box = occ.addBox(0.0, -p.width / 2.0, z0, p.length, p.width, p.height)
    occ.synchronize()
    # Ön yüzün (x = 0) dört kenarı R yarıçapla yuvarlatılır.
    front_edges = []
    for _, tag in gmsh.model.getEntities(1):
        x0, _y0, _z0, x1, _y1, _z1 = gmsh.model.getBoundingBox(1, tag)
        if abs(x0) < 1e-6 and abs(x1) < 1e-6:
            front_edges.append(tag)
    vol = occ.fillet([box], front_edges, [p.front_radius])
    if p.slant_angle_deg > 0:
        a = math.radians(p.slant_angle_deg)
        hinge_x = p.length - p.slant_length * math.cos(a)
        top = z0 + p.height
        big = 4.0 * max(p.length, p.height)
        cutter = occ.addBox(hinge_x, -p.width, top, big, 2.0 * p.width, big)
        # Menteşe (hinge_x, top) etrafında aşağı doğru φ döndür: kesen kutunun alt
        # yüzü eğik yüzey olur.
        occ.rotate([(3, cutter)], hinge_x, 0.0, top, 0.0, 1.0, 0.0, a)
        occ.cut(vol, [(3, cutter)])
    occ.synchronize()


AHMED_BODY = GeometryTemplate(
    id="ahmed_body",
    name="Ahmed gövdesi — otomotiv doğrulaması",
    description=(
        "Ahmed vd. (1984) basitleştirilmiş araç gövdesi: L × W × H, ön kenarlar R, arkada φ açılı S "
        "eğik yüzey, zeminden G yukarıda (bacaklar yok). Deney Cd ile karşılaştırma (V-C4)."
    ),
    params_model=AhmedParams,
    build=_build,
    regions=(Region(name=REGION_BODY, description="Gövde yüzeyleri (tümü)", select=lambda bb, p: True, dim=2),),
    analytic=None,
    characteristic_length=lambda p: p.height,
    default_element_ratio=(0.02, 0.05),
    default_bcs=(),
    tags=("cfd", "dogrulama", "otomotiv"),
)
