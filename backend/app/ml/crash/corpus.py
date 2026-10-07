"""Crash korpusu — 1.19b: crash_runs + geometri template_params → girdi × hedef.

Girdi sütunları kaydın kendisinden düzleştirilir: `geom.<ad>` şablon
parametreleri, `req.<yol>` istek anlık görüntüsünün sayısal yaprakları
(liste elemanı indeksle: `req.parts.0.thickness_mm`). Hangi sütunun modele
gireceği DOE'nin (1.19c) ve mühendisin işi; burada yalnız tüm koşularda aynı
olan sütunlar `constant_features` olarak ayrılır — veri, öneri değil.

Hedefler `app.postprocess.crash_targets` (1.19a); eğriler DB'de değil,
`uploads/crash/<job_id>/job.json` içinde. Hesaplanamayan hedef NaN.

Karışık şablon / senaryo tek tabloya girmez: `template_id` ve `scenario`
zorunlu süzgeç.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.crash_doe import CrashDoeCase
from app.models.crash_run import CrashRun
from app.models.geometry import Geometry
from app.postprocess.crash_targets import TARGET_KEYS, crash_targets

CRASH_DIR = Path("uploads") / "crash"

CurvesLoader = Callable[[str], dict[str, Any]]


@dataclass(frozen=True)
class CrashRecord:
    """Korpusun ihtiyaç duyduğu kayıt alanları (DB'den bağımsız)."""

    run_id: int
    job_id: str
    template_id: str | None
    template_params: dict[str, Any]
    request: dict[str, Any]
    scalars: dict[str, Any]


@dataclass
class CrashCorpus:
    template_id: str
    scenario: str
    run_ids: list[int]
    feature_names: list[str]
    X: np.ndarray
    target_names: list[str]
    Y: np.ndarray
    #: Tüm koşularda aynı değer — X'ten çıkarıldı; {ad: değer}.
    constant_features: dict[str, float] = field(default_factory=dict)
    #: Süzgeçte düşen koşu sayıları (neden → adet).
    dropped: dict[str, int] = field(default_factory=dict)
    #: Korpus tek bir crash DOE çalışmasından süzüldüyse onun kimliği.
    study_id: int | None = None

    def summary(self) -> dict[str, Any]:
        return {
            "template_id": self.template_id,
            "scenario": self.scenario,
            "study_id": self.study_id,
            "n_runs": len(self.run_ids),
            "features": self.feature_names,
            "constant_features": self.constant_features,
            "targets": {
                k: int(np.isfinite(self.Y[:, j]).sum()) if len(self.run_ids) else 0
                for j, k in enumerate(self.target_names)
            },
            "dropped": self.dropped,
        }


def flatten_numeric(obj: Any, prefix: str) -> dict[str, float]:
    """İç içe sözlük / listenin sonlu sayısal yaprakları (bool → 0/1)."""
    out: dict[str, float] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(flatten_numeric(v, f"{prefix}.{k}"))
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            out.update(flatten_numeric(v, f"{prefix}.{i}"))
    elif isinstance(obj, bool):
        out[prefix] = 1.0 if obj else 0.0
    elif isinstance(obj, (int, float)) and math.isfinite(float(obj)):
        out[prefix] = float(obj)
    return out


def job_json_curves(job_id: str, root: Path = CRASH_DIR) -> dict[str, Any]:
    path = root / job_id / "job.json"
    if not path.is_file():
        return {}
    try:
        return dict(json.loads(path.read_text(encoding="utf-8")).get("curves") or {})
    except (OSError, ValueError):
        return {}


def build_corpus(
    records: Iterable[CrashRecord],
    template_id: str,
    scenario: str,
    curves_loader: CurvesLoader = job_json_curves,
) -> CrashCorpus:
    """Kayıtlar → girdi × hedef tablosu (saf; DB yok)."""
    dropped: dict[str, int] = {}
    rows: list[tuple[int, dict[str, float], list[float]]] = []
    for r in records:
        if r.template_id != template_id:
            dropped["other_template"] = dropped.get("other_template", 0) + 1
            continue
        if (r.request.get("scenario") or "") != scenario:
            dropped["other_scenario"] = dropped.get("other_scenario", 0) + 1
            continue
        job = {**r.request, "scalars": r.scalars, "curves": curves_loader(r.job_id)}
        t = crash_targets(job)
        if all(v is None for v in t.values()):
            dropped["no_target"] = dropped.get("no_target", 0) + 1
            continue
        feats = {
            **flatten_numeric(r.template_params or {}, "geom"),
            **flatten_numeric(r.request, "req"),
        }
        y = [math.nan if t[k] is None else float(t[k]) for k in TARGET_KEYS]
        rows.append((r.run_id, feats, y))

    names = sorted({k for _, f, _ in rows for k in f})
    X_all = np.array([[f.get(k, math.nan) for k in names] for _, f, _ in rows], dtype=float).reshape(
        len(rows), len(names)
    )
    keep: list[int] = []
    constant: dict[str, float] = {}
    for j, k in enumerate(names):
        col = X_all[:, j]
        if np.all(np.isfinite(col)) and np.all(col == col[0]):
            constant[k] = float(col[0])
        else:
            keep.append(j)

    return CrashCorpus(
        template_id=template_id,
        scenario=scenario,
        run_ids=[rid for rid, _, _ in rows],
        feature_names=[names[j] for j in keep],
        X=X_all[:, keep],
        target_names=list(TARGET_KEYS),
        Y=np.array([y for _, _, y in rows], dtype=float).reshape(len(rows), len(TARGET_KEYS)),
        constant_features=constant,
        dropped=dropped,
    )


def load_records(db: Session, study_id: int | None = None) -> list[CrashRecord]:
    """Çözülmüş, dışlanmamış crash_runs + geometri şablonu.

    `study_id` verilirse yalnız o crash DOE çalışmasının koşuları (1.19c-3):
    elle yapılmış dağınık denemeler eğitime karışmaz.
    """
    q = (
        select(CrashRun, Geometry.template_id, Geometry.template_params)
        .join(Geometry, Geometry.id == CrashRun.geometry_id)
        .where(CrashRun.status == "solved", CrashRun.excluded.is_(False))
        .order_by(CrashRun.id)
    )
    if study_id is not None:
        q = q.join(CrashDoeCase, CrashDoeCase.run_id == CrashRun.id).where(CrashDoeCase.study_id == study_id)
    return [
        CrashRecord(
            run_id=run.id,
            job_id=run.job_id,
            template_id=tid,
            template_params=dict(tparams or {}),
            request=dict(run.request or {}),
            scalars=dict(run.scalars or {}),
        )
        for run, tid, tparams in db.execute(q).all()
    ]


def load_crash_corpus(
    db: Session,
    template_id: str,
    scenario: str,
    curves_loader: CurvesLoader = job_json_curves,
    study_id: int | None = None,
) -> CrashCorpus:
    corpus = build_corpus(load_records(db, study_id), template_id, scenario, curves_loader)
    corpus.study_id = study_id
    return corpus
