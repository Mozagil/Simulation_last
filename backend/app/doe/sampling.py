"""Latin Hypercube örnekleme (0.5.4).

scipy.stats.qmc yerine NumPy ile McKay LHS: yeni bağımlılık yok, tohum
verilince birebir yeniden üretilir.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from pydantic import BaseModel, Field, model_validator


class BcScenario(BaseModel):
    name: str
    bcs: list[dict[str, Any]]


class DoeSpec(BaseModel):
    template_id: str
    seed: int = 0
    n_samples: int = Field(8, ge=1, le=500)
    #: Taranacak şablon parametreleri: ad -> [lo, hi]
    geometry: dict[str, tuple[float, float]] = Field(default_factory=dict)
    #: Taranmayan ama varsayılandan farklı olması istenen parametreler
    #: (sayı ya da enum). `geometry` ile aynı adı taşıyamaz.
    fixed_params: dict[str, float | str] = Field(default_factory=dict)
    element_size: tuple[float, float] = (6.0, 12.0)
    #: Verilirse CLOAD Fy bu aralıkta taranır (N, işaret korunur). Analitik
    #: uç yüküyle aynı yön: ankastre kirişte −y.
    load_fy: tuple[float, float] | None = None
    #: Verilirse senaryodaki TÜM yük BC'leri bu katsayı aralığıyla ölçeklenir
    #: (cload bileşenleri, pressure/bearing magnitude). `load_fy`'den farkı:
    #: yönü ve tipi korur, basınç/tork senaryolarında da çalışır.
    load_scale: tuple[float, float] | None = None
    #: Geçersiz örnek (şablonun geometrik kısıtlarına takılan) elenip yerine
    #: yenisi çekilir. Kaç tur deneneceği; aşılırsa elde kalanla devam edilir.
    max_resample_passes: int = Field(12, ge=1, le=100)
    material_ids: list[int] = Field(min_length=1)
    bc_scenarios: list[BcScenario] = Field(min_length=1)
    dimension: int = 3
    element_scheme: str = "tet"
    analysis_type: str = "static"
    run_solver: bool = False
    name: str | None = None

    @model_validator(mode="after")
    def _bounds(self) -> "DoeSpec":
        lo, hi = self.element_size
        if hi <= lo:
            raise ValueError("element_size üst sınır alt sınırdan büyük olmalı.")
        if self.load_fy is not None:
            a, b = self.load_fy
            if a == b:
                raise ValueError("load_fy alt ve üst sınır farklı olmalı.")
        for key, pair in self.geometry.items():
            a, b = pair
            if b <= a:
                raise ValueError(f"geometry.{key} üst sınır alt sınırdan büyük olmalı.")
        overlap = set(self.geometry) & set(self.fixed_params)
        if overlap:
            raise ValueError(
                f"Aynı parametre hem taranıyor hem sabit: {sorted(overlap)}"
            )
        if self.load_scale is not None:
            a, b = self.load_scale
            if b <= a:
                raise ValueError("load_scale üst sınır alt sınırdan büyük olmalı.")
            if a <= 0:
                raise ValueError("load_scale alt sınır pozitif olmalı.")
        if self.dimension not in (2, 3):
            raise ValueError("dimension 2 veya 3 olmalı.")
        return self


class DoeSample(BaseModel):
    index: int
    #: Sabit + taranan parametreler birlikte (enum alanları metin olabilir).
    geometry_params: dict[str, Any]
    element_size: float
    material_id: int
    scenario: BcScenario


def latin_hypercube(n_samples: int, n_dim: int, rng: np.random.Generator) -> np.ndarray:
    """Birim küpte LHS: her boyutta her dilim tam bir kez."""
    u = np.empty((n_samples, n_dim), dtype=np.float64)
    for j in range(n_dim):
        perm = rng.permutation(n_samples)
        u[:, j] = (perm + rng.random(n_samples)) / n_samples
    return u


def _lerp(lo: float, hi: float, t: float) -> float:
    return float(lo + t * (hi - lo))


def _pick(items: list[Any], t: float) -> Any:
    if not items:
        raise ValueError("boş küme")
    i = min(len(items) - 1, int(t * len(items)))
    return items[i]


#: Ölçeklenecek yük alanları, BC tipine göre.
_LOAD_FIELDS = {
    "cload": ("fx", "fy", "fz"),
    "pressure": ("magnitude",),
    "bearing": ("magnitude",),
}


def _scale_loads(scenario: BcScenario, factor: float) -> None:
    for bc in scenario.bcs:
        for field in _LOAD_FIELDS.get(str(bc.get("type") or "").lower(), ()):
            value = bc.get(field)
            if isinstance(value, (int, float)):
                bc[field] = float(value) * factor


def _sample_row(spec: DoeSpec, row: np.ndarray, geo_keys: list[str], index: int) -> DoeSample:
    params: dict[str, Any] = dict(spec.fixed_params)
    params.update(
        {
            key: _lerp(spec.geometry[key][0], spec.geometry[key][1], float(row[j]))
            for j, key in enumerate(geo_keys)
        }
    )
    k = len(geo_keys)
    scenario = _pick(spec.bc_scenarios, float(row[k + 2])).model_copy(deep=True)
    if spec.load_fy is not None:
        fy = _lerp(spec.load_fy[0], spec.load_fy[1], float(row[k + 3]))
        for bc in scenario.bcs:
            if str(bc.get("type") or "").lower() == "cload":
                bc["fx"] = 0.0
                bc["fy"] = fy
                bc["fz"] = 0.0
    if spec.load_scale is not None:
        offset = 4 if spec.load_fy is not None else 3
        _scale_loads(scenario, _lerp(spec.load_scale[0], spec.load_scale[1], float(row[k + offset])))
    return DoeSample(
        index=index,
        geometry_params=params,
        element_size=_lerp(spec.element_size[0], spec.element_size[1], float(row[k])),
        material_id=int(_pick(spec.material_ids, float(row[k + 1]))),
        scenario=scenario,
    )


def _params_valid(spec: DoeSpec, params: dict[str, Any]) -> bool:
    """Şablonun kendi doğrulaması (L ≥ 5T, d < 0.6W …) geçiyor mu?"""
    from app.templates import UnknownTemplateError, get_template

    try:
        get_template(spec.template_id).parse_params(params)
    except UnknownTemplateError:
        # Bilinmeyen şablonu burada elemeyiz; runner zaten anlamlı hata verir.
        return True
    except Exception:
        return False
    return True


def sample_spec(spec: DoeSpec) -> list[DoeSample]:
    """Tohumla yinelenebilir LHS + kesikli malzeme/BC senaryosu.

    Şablonların geometrik kısıtları (ankastre kirişte `L ≥ 5T` gibi) parametreler
    BAĞIMSIZ örneklendiği için ihlal edilebilir. Böyle bir örnek çalıştırıldığında
    geometri kurulurken patlar: hem o run kaybedilir hem LHS'in dilim dengesi
    bozulur. Bu yüzden geçersiz satırlar elenir ve yerlerine yeni tur örnek
    çekilir (rejection sampling). Katmanlama tur başına korunur; ilk tur çoğu
    örneği verdiğinde pratikte tam LHS'e çok yakındır. `max_resample_passes`
    tükenirse elde kalanla dönülür — çağıran (runner) eksik sayıyı görür.
    """
    geo_keys = sorted(spec.geometry)
    extra = 3 + (1 if spec.load_fy is not None else 0) + (1 if spec.load_scale is not None else 0)
    n_dim = len(geo_keys) + extra  # + element_size, material, scenario [, load_fy][, load_scale]
    rng = np.random.default_rng(spec.seed)

    out: list[DoeSample] = []
    for _ in range(spec.max_resample_passes):
        need = spec.n_samples - len(out)
        if need <= 0:
            break
        u = latin_hypercube(need, n_dim, rng)
        for row in u:
            sample = _sample_row(spec, row, geo_keys, len(out))
            if _params_valid(spec, sample.geometry_params):
                out.append(sample)
    return out
