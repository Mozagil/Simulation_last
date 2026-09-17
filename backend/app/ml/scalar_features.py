"""Çözülmüş run'lardan skaler eğitim tablosu (0.5.6).

Girdiler şablon parametreleri + eleman boyutu + malzeme + yük; hedefler
`max_displacement` ve `max_von_mises`. Alan modeli değildir.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from sqlalchemy.orm import Session

from app.models.geometry import Geometry
from app.models.run import AnalysisRun

FEATURE_KEYS = (
    "length",
    "thickness",
    "width",
    "element_size",
    "youngs_modulus",
    "poisson_ratio",
    "load_fx",
    "load_fy",
    "load_fz",
    "pressure_mpa",
    "dimension",
)

TARGET_KEYS = ("max_displacement", "max_von_mises")


def _cload_components(bcs: list[dict[str, Any]]) -> tuple[float, float, float]:
    fx = fy = fz = 0.0
    for bc in bcs:
        if str(bc.get("type") or "").lower() != "cload":
            continue
        fx += float(bc.get("fx") or 0.0)
        fy += float(bc.get("fy") or 0.0)
        fz += float(bc.get("fz") or 0.0)
    return fx, fy, fz


def _pressure(bcs: list[dict[str, Any]]) -> float:
    for bc in bcs:
        if str(bc.get("type") or "").lower() != "pressure":
            continue
        raw = bc.get("magnitude")
        if raw is None:
            continue
        mag = abs(float(raw))
        if mag > 0.0:
            return mag
    return 0.0


def features_from_run(run: AnalysisRun, geometry: Geometry | None) -> np.ndarray | None:
    """Tek run için özellik vektörü; eksik hedef/şablon varsa None."""
    params = (geometry.template_params if geometry is not None else None) or {}
    mats = run.materials_snapshot or []
    if not mats:
        return None
    m0 = mats[0]
    e = m0.get("youngs_modulus")
    nu = m0.get("poisson_ratio")
    if e is None:
        return None
    fx, fy, fz = _cload_components(list(run.bcs or []))
    row = [
        float(params.get("length") or 0.0),
        float(params.get("thickness") or 0.0),
        float(params.get("width") or 0.0),
        float(run.element_size or 0.0),
        float(e),
        float(nu if nu is not None else 0.3),
        fx,
        fy,
        fz,
        _pressure(list(run.bcs or [])),
        float(run.dimension),
    ]
    return np.asarray(row, dtype=np.float64)


def targets_from_run(run: AnalysisRun) -> np.ndarray | None:
    scalars = run.scalars or {}
    try:
        disp = float(scalars["max_displacement"])
        vm = float(scalars["max_von_mises"])
    except (KeyError, TypeError, ValueError):
        return None
    return np.asarray([disp, vm], dtype=np.float64)


def collect_scalar_table(
    db: Session,
    run_ids: list[int] | None = None,
) -> tuple[np.ndarray, np.ndarray, list[int]]:
    """Çözülmüş statik run'lar → X, Y, run_id listesi.

    `run_ids` verilirse yalnız o küme (eğitim korpusu) alınır.
    """
    q = (
        db.query(AnalysisRun, Geometry)
        .join(Geometry, Geometry.id == AnalysisRun.geometry_id)
        .filter(AnalysisRun.status == "solved")
    )
    if run_ids is not None:
        if not run_ids:
            return (
                np.zeros((0, len(FEATURE_KEYS)), dtype=np.float64),
                np.zeros((0, len(TARGET_KEYS)), dtype=np.float64),
                [],
            )
        q = q.filter(AnalysisRun.id.in_(run_ids))
    rows = q.order_by(AnalysisRun.id).all()
    xs: list[np.ndarray] = []
    ys: list[np.ndarray] = []
    ids: list[int] = []
    for run, geo in rows:
        if (geo.template_id or "") == "":
            continue
        x = features_from_run(run, geo)
        y = targets_from_run(run)
        if x is None or y is None:
            continue
        xs.append(x)
        ys.append(y)
        ids.append(run.id)
    if not xs:
        return (
            np.zeros((0, len(FEATURE_KEYS)), dtype=np.float64),
            np.zeros((0, len(TARGET_KEYS)), dtype=np.float64),
            [],
        )
    return np.vstack(xs), np.vstack(ys), ids


def features_from_dict(values: dict[str, Any]) -> np.ndarray:
    return np.asarray([float(values.get(k) or 0.0) for k in FEATURE_KEYS], dtype=np.float64)
