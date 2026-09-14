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
    #: Şablon parametresi -> [lo, hi]
    geometry: dict[str, tuple[float, float]] = Field(default_factory=dict)
    element_size: tuple[float, float] = (6.0, 12.0)
    #: Verilirse CLOAD Fy bu aralıkta taranır (N, işaret korunur). Analitik
    #: uç yüküyle aynı yön: ankastre kirişte −y.
    load_fy: tuple[float, float] | None = None
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
        if self.dimension not in (2, 3):
            raise ValueError("dimension 2 veya 3 olmalı.")
        return self


class DoeSample(BaseModel):
    index: int
    geometry_params: dict[str, float]
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


def sample_spec(spec: DoeSpec) -> list[DoeSample]:
    """Tohumla yinelenebilir LHS + kesikli malzeme/BC senaryosu."""
    geo_keys = sorted(spec.geometry)
    extra = 3 + (1 if spec.load_fy is not None else 0)
    n_dim = len(geo_keys) + extra  # + element_size, material, scenario [, load_fy]
    rng = np.random.default_rng(spec.seed)
    u = latin_hypercube(spec.n_samples, n_dim, rng)
    out: list[DoeSample] = []
    for i, row in enumerate(u):
        params = {
            key: _lerp(spec.geometry[key][0], spec.geometry[key][1], float(row[j]))
            for j, key in enumerate(geo_keys)
        }
        k = len(geo_keys)
        scenario = _pick(spec.bc_scenarios, float(row[k + 2])).model_copy(deep=True)
        if spec.load_fy is not None:
            fy = _lerp(spec.load_fy[0], spec.load_fy[1], float(row[k + 3]))
            for bc in scenario.bcs:
                if str(bc.get("type") or "").lower() == "cload":
                    bc["fx"] = 0.0
                    bc["fy"] = fy
                    bc["fz"] = 0.0
        out.append(
            DoeSample(
                index=i,
                geometry_params=params,
                element_size=_lerp(spec.element_size[0], spec.element_size[1], float(row[k])),
                material_id=int(_pick(spec.material_ids, float(row[k + 1]))),
                scenario=scenario,
            )
        )
    return out
