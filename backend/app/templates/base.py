"""Parametrik geometri şablonu altyapısı (Faz 0.4.1).

Şablon = parametre şeması + kurucu fonksiyon + isimlendirilmiş bölgeler +
analitik referans (varsa). Veri olarak tanımlanır (`GeometryTemplate`
örneği), koda gömülmez; yeni şablon eklemek `app/templates/` altına tek bir
dosya eklemekten ibarettir. Frontend formu (0.4.4) `params_schema()` ile
şemadan üretilecek, DOE (0.5.4) parametre uzayını yine bu şemadan alacak.

Geometri gmsh OCC ile üretilir — Faz 0'da STEP okumak için kullanılan aynı
modül, yeni bağımlılık yok.

İSİMLENDİRİLMİŞ BÖLGELER: kurucu, BC uygulanacak yüzeyleri (`ankastre_uc`,
`yuk_yuzeyi` ...) GEOMETRİK olarak bulur (sınır kutusu ile), yüzey
numaralarını sabit varsaymaz. gmsh'in yüzey sıralaması sürüm ya da
parametre değişikliğiyle kayabilir ve BC sessizce yanlış yüzeye uygulanır —
Faz 0'da yaşanan yedi sessiz hatanın sınıfından. Bölgeler `PhysicalGroup`
tablosuna yazılır (bkz. `service.py`), böylece mevcut BC akışı `face_ids`
ile aynen çalışır.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel

#: Yüzey sınır kutusu: (xmin, ymin, zmin, xmax, ymax, zmax)
BBox = tuple[float, float, float, float, float, float]

_AXIS_INDEX = {"x": 0, "y": 1, "z": 2}


class TemplateError(ValueError):
    """Şablon parametreleri geçerli ama geometri kurulamadı / bölge bulunamadı."""


@dataclass(frozen=True)
class Region:
    """Şablonun BC uygulanabilir isimli bölgesi.

    `select`, yüzeyin sınır kutusunu ve doğrulanmış parametreleri alır, o
    yüzeyin bu bölgeye ait olup olmadığını söyler (parametreye bağlı
    düzlemler — `x = length` gibi — bu yüzden mümkün). `expected_faces` verilirse bulunan
    yüzey sayısı buna eşit olmalıdır — eksik/fazla yüzey, geometri kurucusunda
    bir hatanın en erken belirtisidir.
    """

    name: str
    description: str
    select: Callable[[BBox, BaseModel], bool]
    dim: int = 2
    expected_faces: int | None = None


@dataclass(frozen=True)
class AnalyticInput:
    """Analitik referansın ihtiyaç duyduğu yük/malzeme girdileri.

    Her şablon kendi kullandığı alanları belgeler; kullanmadığı alanlar
    yok sayılır. 0.4.5'te FEA sonucuyla karşılaştırma bunu kullanacak.
    """

    force_n: float = 0.0
    youngs_modulus_pa: float = 210e9
    poisson_ratio: float = 0.3


@dataclass(frozen=True)
class BuildResult:
    """Kurucunun çıktısı: STEP dosyası + bölge -> yüzey etiketleri."""

    step_path: Path
    regions: dict[str, list[int]]
    bounding_box: BBox


@dataclass(frozen=True)
class GeometryTemplate:
    id: str
    name: str
    description: str
    params_model: type[BaseModel]
    #: gmsh oturumu AÇIKKEN çağrılır; OCC ile geometriyi kurar ve
    #: `gmsh.model.occ.synchronize()` yapar. Dosya yazma ve bölge bulma
    #: altyapıya aittir (bkz. `build_template`).
    build: Callable[[BaseModel], None]
    regions: tuple[Region, ...]
    #: Kapalı form çözüm; skaler adı -> değer. Adlar `AnalysisRun.scalars`
    #: ile aynı (`max_displacement` [mm], `max_von_mises` [MPa]) ki 0.4.5'te
    #: doğrudan karşılaştırılabilsin. Yoksa None.
    analytic: Callable[[BaseModel, AnalyticInput], dict[str, float]] | None = None
    tags: tuple[str, ...] = field(default_factory=tuple)

    def params_schema(self) -> dict[str, Any]:
        """Frontend formu / DOE için JSON şeması (Pydantic'ten)."""
        return self.params_model.model_json_schema()

    def parse_params(self, raw: dict[str, Any]) -> BaseModel:
        """Ham sözlüğü doğrulanmış parametre nesnesine çevirir.

        Hatalı değerde `pydantic.ValidationError` fırlatır — çağıran (API
        katmanı) bunu 422'ye çevirir.
        """
        return self.params_model.model_validate(raw)

    def region_names(self) -> list[str]:
        return [r.name for r in self.regions]


# --- bölge seçici yardımcıları -------------------------------------------------


def plane_at(
    axis: str,
    value: float | Callable[[Any], float],
    tol: float = 1e-6,
) -> Callable[[BBox, BaseModel], bool]:
    """`axis = value` düzleminde yatan (o eksende sıfır kalınlıklı) yüzeyleri seçer.

    `value` sabit ya da parametrelerden hesaplanan bir fonksiyon olabilir:
        plane_at("x", 0.0)                 # ankastre uç
        plane_at("x", lambda p: p.length)  # serbest uç
    """
    i = _AXIS_INDEX[axis]

    def _select(bbox: BBox, params: BaseModel) -> bool:
        target = value(params) if callable(value) else value
        return abs(bbox[i] - target) < tol and abs(bbox[i + 3] - target) < tol

    return _select


def _bbox_is_finite(bbox: BBox) -> bool:
    return all(math.isfinite(v) for v in bbox)


# --- kurucu -------------------------------------------------------------------


def build_template(template: GeometryTemplate, params: BaseModel, step_path: Path) -> BuildResult:
    """Şablonu gmsh OCC ile kurar, STEP'e yazar ve isimli bölgeleri bulur.

    Gmsh'in global durumu süreç genelinde TEKTİR; bu yüzden
    `gmsh_adapter._gmsh_lock` burada da alınır — aksi halde eş zamanlı bir
    `import_geometry` ile çakışıp segfault'a gidebilir (Faz 0'da yaşandı).
    Oturum bu fonksiyonun içinde açılıp kapanır; çağıran gmsh'e dokunmaz.
    """
    import gmsh

    from app.mesh.gmsh_adapter import _gmsh_lock

    if not _gmsh_lock.acquire(timeout=180):
        raise TemplateError(
            "Gmsh kilidi alınamadı (önceki işlem takılı kalmış olabilir). "
            "Backend sürecini yeniden başlatın."
        )
    gmsh.initialize(interruptible=False)
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add(template.id)

        template.build(params)
        gmsh.model.occ.synchronize()

        volumes = gmsh.model.getEntities(dim=3)
        if not volumes:
            raise TemplateError(f"Şablon '{template.id}' hiç hacim üretmedi.")

        # Bölgeleri geometrik olarak bul.
        faces = [tag for _dim, tag in gmsh.model.getEntities(dim=2)]
        bboxes = {tag: tuple(gmsh.model.getBoundingBox(2, tag)) for tag in faces}
        regions: dict[str, list[int]] = {}
        for region in template.regions:
            hits = sorted(tag for tag, bb in bboxes.items() if region.select(bb, params))
            if not hits:
                raise TemplateError(
                    f"Şablon '{template.id}': '{region.name}' bölgesi için yüzey bulunamadı."
                )
            if region.expected_faces is not None and len(hits) != region.expected_faces:
                raise TemplateError(
                    f"Şablon '{template.id}': '{region.name}' için {region.expected_faces} "
                    f"yüzey bekleniyordu, {len(hits)} bulundu: {hits}"
                )
            regions[region.name] = hits

        bbox = tuple(gmsh.model.getBoundingBox(-1, -1))
        if not _bbox_is_finite(bbox):
            raise TemplateError(f"Şablon '{template.id}': sınır kutusu hesaplanamadı.")

        step_path.parent.mkdir(parents=True, exist_ok=True)
        gmsh.write(str(step_path))
    finally:
        gmsh.finalize()
        _gmsh_lock.release()

    return BuildResult(step_path=step_path, regions=regions, bounding_box=bbox)  # type: ignore[arg-type]
