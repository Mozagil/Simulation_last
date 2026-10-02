"""Şablon: crash box + çarpma plakası (Faz 1, 1.11a).

İki AYRI katı: açık uçlu kutu profil (crash box) ve önünde kalın bir plaka.
Kutu −x yönünde hareket edip plakaya çarpar; plaka arka yüzünden tutulur.
Katılar birleştirilmez (`fuse` yok): mesh katmanı her hacme ayrı `part_id`
verir (bkz. `mesh/gmsh_adapter._compute_face_to_part`), deck parça başına
`/PART` + `/MAT` + `/PROP` yazabilir (1.11b) ve temas (1.12) iki parça
arasında tanımlanır. Aralık `gap` > 0: başlangıçta temas yok.

Koordinatlar: kutu x ∈ [0, L], kesit y ∈ [0, h], z ∈ [0, b]. Plaka
x ∈ [−gap−tp, −gap], kesiti kutuyu her yanda `margin` kadar aşar.

Analitik çözüm yok (dinamik problem); durability akışı için varsayılan
BC'ler yine verilir (plaka arkası sabit, kutu arkasına −x basma yükü) ki
şablon kütüphanesinin statik testleri ve DOE kısıtları bozulmasın.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from app.templates.base import GeometryTemplate, Region, plane_at

REGION_PLATE_BACK = "plaka_arka"
REGION_PLATE_FRONT = "plaka_on"
REGION_BOX_FRONT = "kutu_on"
REGION_BOX_BACK = "kutu_arka"


class CrashBoxPlateParams(BaseModel):
    """Tüm boyutlar mm."""

    box_length: float = Field(200.0, gt=0, description="Kutu uzunluğu L (x)", json_schema_extra={"unit": "mm", "symbol": "L"})
    box_height: float = Field(50.0, gt=0, description="Kutu dış yüksekliği h (y)", json_schema_extra={"unit": "mm", "symbol": "h"})
    box_width: float = Field(40.0, gt=0, description="Kutu dış genişliği b (z)", json_schema_extra={"unit": "mm", "symbol": "b"})
    wall: float = Field(2.0, gt=0, description="Kutu cidar kalınlığı t", json_schema_extra={"unit": "mm", "symbol": "t"})
    plate_thickness: float = Field(10.0, gt=0, description="Plaka kalınlığı tp (x)", json_schema_extra={"unit": "mm", "symbol": "tp"})
    plate_margin: float = Field(20.0, ge=0, description="Plakanın kutu kesitini her yanda aşma payı m", json_schema_extra={"unit": "mm", "symbol": "m"})
    gap: float = Field(1.0, gt=0, description="Kutu önü ile plaka arası başlangıç aralığı g", json_schema_extra={"unit": "mm", "symbol": "g"})

    @model_validator(mode="after")
    def _geometry_ok(self) -> "CrashBoxPlateParams":
        if self.box_height <= 2.0 * self.wall or self.box_width <= 2.0 * self.wall:
            raise ValueError("box_height ve box_width, 2 × wall değerinden büyük olmalı.")
        if self.box_length < self.box_height:
            raise ValueError(
                f"box_length ({self.box_length}) en az box_height ({self.box_height}) olmalı."
            )
        return self

    # Türetilmiş düzlemler (bölge seçimi ve testler için tek kaynak).
    @property
    def plate_front_x(self) -> float:
        return -self.gap

    @property
    def plate_back_x(self) -> float:
        return -(self.gap + self.plate_thickness)


def _build(p: CrashBoxPlateParams) -> None:
    import gmsh

    outer = gmsh.model.occ.addBox(0.0, 0.0, 0.0, p.box_length, p.box_height, p.box_width)
    inner = gmsh.model.occ.addBox(
        -1.0,
        p.wall,
        p.wall,
        p.box_length + 2.0,
        p.box_height - 2.0 * p.wall,
        p.box_width - 2.0 * p.wall,
    )
    gmsh.model.occ.cut([(3, outer)], [(3, inner)])
    # Plaka ayrı katı; kutuyla birleştirilmez.
    gmsh.model.occ.addBox(
        p.plate_back_x,
        -p.plate_margin,
        -p.plate_margin,
        p.plate_thickness,
        p.box_height + 2.0 * p.plate_margin,
        p.box_width + 2.0 * p.plate_margin,
    )


def box_volume_mm3(p: CrashBoxPlateParams) -> float:
    return p.box_length * (
        p.box_height * p.box_width
        - (p.box_height - 2.0 * p.wall) * (p.box_width - 2.0 * p.wall)
    )


def plate_volume_mm3(p: CrashBoxPlateParams) -> float:
    return (
        p.plate_thickness
        * (p.box_height + 2.0 * p.plate_margin)
        * (p.box_width + 2.0 * p.plate_margin)
    )


CRASH_BOX_PLATE = GeometryTemplate(
    id="crash_box_plate",
    name="Crash box + çarpma plakası (iki parça)",
    description=(
        "Açık uçlu kutu profil −x yönünde hareket edip sabit plakaya çarpar. "
        "İki ayrı katı: kutu (part 0) ve plaka (part 1); temas 1.12'de. Analitik yok."
    ),
    params_model=CrashBoxPlateParams,
    build=_build,
    regions=(
        Region(
            name=REGION_PLATE_BACK,
            description="Plaka arka yüzü (x = −g−tp) — sabit",
            select=plane_at("x", lambda p: p.plate_back_x),
            expected_faces=1,
        ),
        Region(
            name=REGION_PLATE_FRONT,
            description="Plaka ön yüzü (x = −g) — temas ana (master) yüzeyi",
            select=plane_at("x", lambda p: p.plate_front_x),
            expected_faces=1,
        ),
        Region(
            name=REGION_BOX_FRONT,
            description="Kutu ön ucu (x = 0) — temas ikincil (slave) yüzeyi",
            select=plane_at("x", 0.0),
            expected_faces=1,
        ),
        Region(
            name=REGION_BOX_BACK,
            description="Kutu arka ucu (x = L) — ilk hız / basma yükü",
            select=plane_at("x", lambda p: p.box_length),
            expected_faces=1,
        ),
    ),
    analytic=None,
    characteristic_length=lambda p: p.wall,
    default_element_ratio=(0.8, 1.5),
    default_bcs=(
        {"type": "fixed", "region": REGION_PLATE_BACK},
        {"type": "cload", "region": REGION_BOX_BACK, "fx": -1000.0, "fy": 0.0, "fz": 0.0},
    ),
    tags=("crash", "coklu_parca", "profil"),
)
