"""Şablon: ankastre kiriş, dikdörtgen kesit (Grup 1).

Faz 0'ın doğrulama vakası (50x10x500 mm, uçtan 500 N, S235):
    kiriş teorisi 23.81 mm / 300.0 MPa — bu proje (C3D10) 23.92 mm / 330.7 MPa
İlk şablonun cevabı bilinen vaka olması bilinçli: altyapının doğruluğu ilk
günden kilitlenir (bkz. tests/test_templates.py, uçtan uca test).

Eksen yerleşimi `tests/test_reference_validation.py` ile BİREBİR aynı:
    x: uzunluk (L)     y: kalınlık (T) — yük ve eğilme bu eksende
    z: genişlik (W)
Ankastre uç x=0, yük yüzeyi x=L, yük -y yönünde.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from app.templates.base import AnalyticInput, GeometryTemplate, Region, plane_at

REGION_FIXED = "ankastre_uc"
REGION_LOAD = "yuk_yuzeyi"


class CantileverBeamParams(BaseModel):
    """Tüm boyutlar mm."""

    length: float = Field(500.0, gt=0, description="Kiriş uzunluğu L (x)", json_schema_extra={"unit": "mm"})
    thickness: float = Field(10.0, gt=0, description="Kesit kalınlığı T (y, yük yönü)", json_schema_extra={"unit": "mm"})
    width: float = Field(50.0, gt=0, description="Kesit genişliği W (z)", json_schema_extra={"unit": "mm"})

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
        return self


def _build(p: CantileverBeamParams) -> None:
    import gmsh

    gmsh.model.occ.addBox(0.0, 0.0, 0.0, p.length, p.thickness, p.width)


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
            description="Ankastre uç (x=0) — tüm serbestlikler sıfır",
            select=plane_at("x", 0.0),
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
    tags=("grup1", "analitik", "egilme"),
)
