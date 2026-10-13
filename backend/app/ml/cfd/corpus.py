"""CFD korpusu — 2.9: roket koşuları (cfd_runs, R3) → girdi × hedef.

Girdi sütunları: ``flow.mach``, ``flow.alpha_deg``, ``flow.x_ref_m`` (moment
noktası / CG) ve ``geom.<ad>`` roket şablon parametreleri (sayısal olanlar;
burun profili gibi metin alanlar kategori kodu ``geom.<ad>#<değer>`` = 0/1).
Hedefler R3 katsayıları: CA, CN, CD, CL, Cm, x_cp_m. Tüm koşularda aynı olan
sütunlar ``constant_features`` (veri). Karışık çözücü tek tabloya girmez:
``application`` zorunlu süzgeç (simpleFoam | rhoSimpleFoam | rhoCentralFoam).

Crash korpusuyla aynı veri yapısı (``CrashCorpus``) — aynı RF + K-fold eğitimi
(``app.ml.crash.surrogate``) kullanılır.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from sqlalchemy.orm import Session

from app.ml.crash.corpus import CrashCorpus
from app.models.cfd_run import CfdRun
from app.models.geometry import Geometry

TARGETS: list[tuple[str, str, str]] = [
    ("CD", "Sürükleme katsayısı CD", "-"),
    ("CL", "Taşıma katsayısı CL", "-"),
    ("CA", "Eksenel kuvvet katsayısı CA", "-"),
    ("CN", "Normal kuvvet katsayısı CN", "-"),
    ("Cm", "Yunuslama momenti katsayısı Cm (moment noktasına göre)", "-"),
    ("x_cp_m", "Basınç merkezi x_cp (burun ucundan)", "m"),
]
TARGET_KEYS = [t[0] for t in TARGETS]
SOLVERS = ("simpleFoam", "rhoSimpleFoam", "rhoCentralFoam")


def _num(v: Any) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v) if math.isfinite(v) else None


def run_features(rocket: dict[str, Any], template_params: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    for k in ("mach", "alpha_deg", "x_ref_m"):
        v = _num(rocket.get(k))
        if v is not None:
            out[f"flow.{k}"] = v
    for k, v in sorted((template_params or {}).items()):
        n = _num(v)
        if n is not None:
            out[f"geom.{k}"] = n
        elif isinstance(v, str):
            out[f"geom.{k}#{v}"] = 1.0
    return out


def load_cfd_corpus(db: Session, application: str, *, job_ids: list[str] | None = None, doe_id: str | None = None) -> CrashCorpus:
    q = db.query(CfdRun).filter(CfdRun.application == application)
    if job_ids is not None:
        q = q.filter(CfdRun.job_id.in_(job_ids or ["-"]))
    dropped: dict[str, int] = {}
    rows: list[tuple[int, dict[str, float], list[float]]] = []
    for r in q.order_by(CfdRun.id).all():
        ref = r.reference or {}
        rocket = (r.request or {}).get("rocket")
        reason = None
        if r.excluded:
            reason = "dışlanmış"
        elif r.status != "solved":
            reason = f"durum {r.status}"
        elif ref.get("kind") != "rocket_r3" or not rocket:
            reason = "roket koşusu değil"
        if reason:
            dropped[reason] = dropped.get(reason, 0) + 1
            continue
        geo = db.get(Geometry, r.geometry_id) if r.geometry_id is not None else None
        feats = run_features(rocket, (geo.template_params if geo is not None else None) or {})
        aero = ref.get("aero") or {}
        ys = [(_num(aero.get(k)) if _num(aero.get(k)) is not None else math.nan) for k in TARGET_KEYS]
        rows.append((r.id, feats, ys))

    # kategori kodları: bir koşuda yoksa 0; sayısal sütun eksikse NaN
    cat = sorted({k for _, f, _ in rows for k in f if "#" in k})
    num_keys = sorted({k for _, f, _ in rows for k in f if "#" not in k})
    names = num_keys + cat
    X = np.array(
        [[f.get(k, 0.0 if "#" in k else math.nan) for k in names] for _, f, _ in rows], dtype=float
    ).reshape(len(rows), len(names))
    Y = np.array([y for _, _, y in rows], dtype=float).reshape(len(rows), len(TARGET_KEYS))
    constant: dict[str, float] = {}
    keep = []
    for j, k in enumerate(names):
        col = X[:, j]
        if len(rows) and np.all(np.isfinite(col)) and np.all(col == col[0]):
            constant[k] = float(col[0])
        else:
            keep.append(j)
    return CrashCorpus(
        template_id="rocket",
        scenario=application.lower(),
        run_ids=[r for r, _, _ in rows],
        feature_names=[names[j] for j in keep],
        X=X[:, keep] if rows else np.zeros((0, len(keep))),
        target_names=list(TARGET_KEYS),
        Y=Y,
        constant_features=constant,
        dropped=dropped,
        study_id=None,
    )
