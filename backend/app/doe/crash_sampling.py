"""Crash DOE örnekleme — 1.19c-1.

Taban istek bir `CrashScenarioRequest` (her crash şablonu: kutu, düşme, direk,
plaka–küre, kuş, mayın …); `vary` noktalı yol → [alt, üst] aralığı. Yol taban
isteğin bir alanıdır: `speed_m_s`, `thickness_mm`, `t_end_ms`,
`model.sigma_y_pa`, `geometry.wall` (şablon parametresi) … Hangi alanın hangi
aralıkta taranacağı mühendisin; burada yalnız LHS (durability `latin_hypercube`,
tohumla birebir) ve şablonun / isteğin kendi doğrulaması var. Doğrulamaya
takılan örnek yeniden çekilir.

Saf: DB yok, çözücü yok. Koşturma ve kayıt sonraki adım.
"""

from __future__ import annotations

import copy
from typing import Any

import numpy as np
from pydantic import BaseModel, Field, ValidationError, model_validator

from app.doe.sampling import latin_hypercube


class CrashDoeSpec(BaseModel):
    name: str | None = None
    #: Sabit kısım: CrashScenarioRequest gövdesi (template_id dahil).
    base: dict[str, Any]
    #: Taranan alanlar: noktalı yol → (alt, üst).
    vary: dict[str, tuple[float, float]] = Field(min_length=1)
    n_samples: int = Field(8, ge=1, le=500)
    seed: int = 0
    max_resample_passes: int = Field(12, ge=1, le=100)

    @model_validator(mode="after")
    def _bounds(self) -> "CrashDoeSpec":
        for path, (lo, hi) in self.vary.items():
            if not hi > lo:
                raise ValueError(f"'{path}': üst sınır alt sınırdan büyük olmalı.")
        return self


class CrashDoeError(ValueError):
    pass


def _child(node: Any, key: str) -> Any:
    """Sözlük anahtarı ya da liste indisi (ör. `rigid_bodies.0.mass_kg`)."""
    if isinstance(node, dict):
        return node.get(key)
    if isinstance(node, list) and key.isdigit() and int(key) < len(node):
        return node[int(key)]
    return None


def _set_path(body: dict[str, Any], path: str, value: float) -> None:
    keys = path.split(".")
    node: Any = body
    for k in keys[:-1]:
        nxt = _child(node, k)
        if nxt is None and isinstance(node, dict):
            nxt = node.setdefault(k, {})
        node = nxt
        if not isinstance(node, (dict, list)):
            raise CrashDoeError(f"'{path}': sözlük/liste olmayan alanın altı taranamaz.")
    last = keys[-1]
    if isinstance(node, list):
        if not (last.isdigit() and int(last) < len(node)):
            raise CrashDoeError(f"'{path}': liste indisi yok.")
        node[int(last)] = value
    else:
        node[last] = value


def _validate(body: dict[str, Any]) -> dict[str, Any]:
    """Senaryo isteği + şablon parametresi doğrulaması; geçersizse ValidationError."""
    from app.api.crash_scenario import CrashScenarioRequest, _resolved_geometry

    req = CrashScenarioRequest.model_validate(body)
    _resolved_geometry(req)
    return req.model_dump(mode="json")


def check_paths(spec: CrashDoeSpec) -> None:
    """Her yol taban istekte (ya da şablon parametrelerinde) var olan sayısal alan mı?"""
    from app.templates import get_template

    try:
        base = _validate(copy.deepcopy(spec.base))
    except ValidationError as exc:
        raise CrashDoeError(f"Taban istek geçersiz: {exc}") from exc
    geo_fields = get_template(base["template_id"]).params_model.model_fields
    for path in spec.vary:
        keys = path.split(".")
        if keys[0] == "geometry":
            if len(keys) != 2 or keys[1] not in geo_fields:
                raise CrashDoeError(f"'{path}': {base['template_id']} şablonunda böyle parametre yok.")
            continue
        node: Any = base
        for k in keys[:-1]:
            node = _child(node, k)
        v = _child(node, keys[-1])
        if v is None and not (isinstance(node, dict) and keys[-1] in node):
            raise CrashDoeError(f"'{path}': senaryo isteğinde böyle alan yok.")
        if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float))):
            raise CrashDoeError(f"'{path}': sayısal alan değil.")


def sample_crash_cases(spec: CrashDoeSpec) -> list[dict[str, Any]]:
    """→ [{index, values: {yol: değer}, request: doğrulanmış istek}] (en çok n_samples)."""
    check_paths(spec)
    paths = list(spec.vary)
    rng = np.random.default_rng(spec.seed)
    cases: list[dict[str, Any]] = []
    for _ in range(spec.max_resample_passes):
        need = spec.n_samples - len(cases)
        if need <= 0:
            break
        u = latin_hypercube(need, len(paths), rng)
        for row in u:
            values = {
                p: float(lo + t * (hi - lo)) for p, (lo, hi), t in zip(paths, spec.vary.values(), row)
            }
            body = copy.deepcopy(spec.base)
            for p, v in values.items():
                _set_path(body, p, v)
            try:
                request = _validate(body)
            except ValidationError:
                continue
            cases.append({"index": len(cases), "values": values, "request": request})
    return cases
