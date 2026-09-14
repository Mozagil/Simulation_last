"""Eğitim uzayı dışı işaretleme (0.5.8).

Ağaç modelleri uzay dışında sabit bir değer döndürür ve bunu hata vermeden
yapar. Kutu sınırı: herhangi bir özellik eğitim min–max dışındaysa işaretlenir.
Öneri üretmez — yalnız bayrak.
"""

from __future__ import annotations

from typing import Any

import numpy as np


def bounds_from_matrix(X: np.ndarray) -> dict[str, list[float]]:
    if X.size == 0:
        return {"min": [], "max": []}
    return {
        "min": [float(v) for v in np.min(X, axis=0)],
        "max": [float(v) for v in np.max(X, axis=0)],
    }


def is_out_of_domain(x: np.ndarray, bounds: dict[str, Any], *, rtol: float = 0.0) -> bool:
    lo = np.asarray(bounds.get("min") or [], dtype=np.float64)
    hi = np.asarray(bounds.get("max") or [], dtype=np.float64)
    vec = np.asarray(x, dtype=np.float64).reshape(-1)
    if lo.size == 0 or hi.size == 0 or lo.size != vec.size:
        return True
    span = np.maximum(np.abs(hi - lo), 1e-12)
    pad = span * float(rtol)
    return bool(np.any(vec < lo - pad) or np.any(vec > hi + pad))
