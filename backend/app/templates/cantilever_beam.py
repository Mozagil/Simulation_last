"""Şablon: ankastre kiriş, dikdörtgen kesit (Grup 1).

Faz 0'ın doğrulama vakası (50x10x500 mm, uçtan 500 N, S235):
    kiriş teorisi 23.81 mm / 300.0 MPa — bu proje (C3D10) 23.92 mm / 330.7 MPa
İlk şablonun cevabı bilinen vaka olması bilinçli: altyapının doğruluğu ilk
günden kilitlenir (bkz. tests/test_templates.py, uçtan uca test).

Eksen yerleşimi `tests/test_reference_validation.py` ile BİREBİR aynı:
    x: uzunluk (L)     y: kalınlık (T) — yük ve eğilme bu eksende
    z: genişlik (W)
Ankastre uç x=0, yük yüzeyi x=L, yük -y yönünde.

KÖK FİLLETİ (TODO 6): `root_fillet > 0` iken kiriş x<0 tarafındaki bir
duvar bloğuna (kalınlık `wall_thickness`, kesitten her yönde `wall_margin`
taşma) kaynaklanır ve birleşim kenarlarına r yarıçaplı fillet konur;
ankastre BC duvarın ARKA yüzüne (x = −wall_thickness) taşınır. Sebep:
düz kutuda kökte geometrik köşe yok — tekillik sınır koşulunun kenarından
geliyor, fillet konacak yer ancak destek modellenince oluşuyor.
`root_fillet = 0` → duvar YOK, geometri eskisiyle birebir aynı.
Analitik referans duvar esnekliğini içermez (ideal ankastre).
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from app.templates.base import AnalyticInput, GeometryTemplate, Region, plane_at

REGION_FIXED = "ankastre_uc"
REGION_LOAD = "yuk_yuzeyi"


class CantileverBeamParams(BaseModel):
    """Tüm boyutlar mm."""

    length: float = Field(500.0, gt=0, description="Kiriş uzunluğu L (x)", json_schema_extra={"unit": "mm", "symbol": "L"})
    thickness: float = Field(10.0, gt=0, description="Kesit kalınlığı T (y, yük yönü)", json_schema_extra={"unit": "mm", "symbol": "T"})
    width: float = Field(50.0, gt=0, description="Kesit genişliği W (z)", json_schema_extra={"unit": "mm", "symbol": "W"})
    root_fillet: float = Field(
        0.0,
        ge=0,
        description="Kök fillet yarıçapı r (0 → duvar yok, düz ankastre)",
        # optional: tahmin isteğinde eksikse varsayılan alınır (çekirdek
        # L/T/W için böyle değil — eksikleri açık hata).
        json_schema_extra={"unit": "mm", "symbol": "r", "optional": True},
    )
    wall_thickness: float = Field(
        20.0,
        gt=0,
        description="Duvar kalınlığı (x) — yalnız r > 0 iken",
        json_schema_extra={"unit": "mm", "symbol": "tw", "optional": True},
    )
    wall_margin: float = Field(
        20.0,
        gt=0,
        description="Duvarın kesitten her yönde taşması — yalnız r > 0 iken",
        json_schema_extra={"unit": "mm", "symbol": "m", "optional": True},
    )

    @model_validator(mode="after")
    def _beam_like(self) -> "CantileverBeamParams":
        # Kiriş teorisi (analitik referans) L >> T varsayar. L/T < 5'te
        # kesme deformasyonu ihmal edilemez ve referans anlamsızlaşır; bunu
        # "geçerli ama yanlış" yerine açık hata yapıyoruz. Kesme etkisini
        # incelemek istenirse gevşetilebilir, ama o zaman analitik referans
        # kapatılmalı.
        if self.length < 5 * self.thickness:
            raise ValueError(
                f"length ({self.length}) en az 5 x thickness ({self.thickness}) olmalı; "
                "daha kısa kirişte kiriş teorisi (analitik referans) geçersiz."
            )
        if self.root_fillet > 0:
            # Fillet duvar yüzünde r kadar yer kaplar; taşma yetmezse duvarın
            # kenarını keser ve OCC ya patlar ya da bozuk katı üretir.
            if self.root_fillet >= self.wall_margin:
                raise ValueError(
                    f"root_fillet ({self.root_fillet}) wall_margin ({self.wall_margin}) "
                    "değerinden küçük olmalı."
                )
            if self.root_fillet >= self.length:
                raise ValueError("root_fillet kiriş uzunluğundan küçük olmalı.")
        return self


def _build(p: CantileverBeamParams) -> None:
    import gmsh

    beam = gmsh.model.occ.addBox(0.0, 0.0, 0.0, p.length, p.thickness, p.width)
    if p.root_fillet <= 0:
        return
    m = p.wall_margin
    wall = gmsh.model.occ.addBox(
        -p.wall_thickness, -m, -m, p.wall_thickness, p.thickness + 2 * m, p.width + 2 * m
    )
    fused, _ = gmsh.model.occ.fuse([(3, beam)], [(3, wall)])
    gmsh.model.occ.synchronize()
    # Birleşim kenarları: x=0 düzleminde, kiriş kesitinin çevresinde yatan 4 kenar.
    eps = 1e-6
    root_edges = []
    for _d, tag in gmsh.model.getEntities(dim=1):
        x0, y0, z0, x1, y1, z1 = gmsh.model.getBoundingBox(1, tag)
        if (
            abs(x0) < eps and abs(x1) < eps
            and y0 > -eps and y1 < p.thickness + eps
            and z0 > -eps and z1 < p.width + eps
        ):
            root_edges.append(tag)
    if len(root_edges) != 4:
        raise RuntimeError(f"Kök kenarı 4 bekleniyordu, {len(root_edges)} bulundu.")
    gmsh.model.occ.fillet([t for _d, t in fused], root_edges, [p.root_fillet], removeVolume=True)


def _analytic(p: CantileverBeamParams, a: AnalyticInput) -> dict[str, float]:
    """Euler-Bernoulli: uç deplasmanı ve ankastre uçtaki maks. eğilme gerilmesi.

    Birimler: mm, N, MPa. E Pa olarak gelir, MPa'ya çevrilir.
    `max_von_mises`, tek eksenli eğilmede von Mises = |sigma_x| olduğu için
    eğilme gerilmesine eşittir (FEA'da köşe tekilliği nedeniyle biraz üstüne
    çıkar — referans testte %10, tolerans bunu kapsıyor).
    """
    e_mpa = a.youngs_modulus_pa / 1e6
    inertia = p.width * p.thickness**3 / 12.0
    tip_deflection = a.force_n * p.length**3 / (3.0 * e_mpa * inertia)
    bending_stress = a.force_n * p.length * (p.thickness / 2.0) / inertia
    return {"max_displacement": tip_deflection, "max_von_mises": bending_stress}


CANTILEVER_BEAM = GeometryTemplate(
    id="cantilever_beam",
    name="Ankastre kiriş (dikdörtgen kesit)",
    description=(
        "Bir ucu ankastre, diğer ucundan tekil yükle eğilen dikdörtgen kesitli "
        "kiriş. Faz 0 doğrulama vakası; kiriş teorisi ile kapalı form çözümü var."
    ),
    params_model=CantileverBeamParams,
    build=_build,
    regions=(
        Region(
            name=REGION_FIXED,
            description="Ankastre uç (x=0; kök fillet varsa duvar arka yüzü) — tüm serbestlikler sıfır",
            select=plane_at("x", lambda p: -p.wall_thickness if p.root_fillet > 0 else 0.0),
            expected_faces=1,
        ),
        Region(
            name=REGION_LOAD,
            description="Serbest uç (x=L) — tekil yük -y yönünde",
            select=plane_at("x", lambda p: p.length),
            expected_faces=1,
        ),
    ),
    analytic=_analytic,
    # Karakteristik uzunluk: kesit kalınlığı — eğilme gradyanı bu eksende.
    characteristic_length=lambda p: p.thickness,
    default_element_ratio=(0.5, 1.2),
    default_bcs=(
        {"type": "fixed", "region": REGION_FIXED},
        {"type": "cload", "region": REGION_LOAD, "fx": 0.0, "fy": -500.0, "fz": 0.0},
    ),
    tags=("grup1", "analitik", "egilme"),
)
