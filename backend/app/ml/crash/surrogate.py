"""Crash vekil modeli — 1.19d: hedef başına Random Forest + K-fold CV.

Girdi bir `CrashCorpus` (1.19b, tercihen tek DOE çalışması — 1.19c-3).
Her hedef kendi dolu satırlarıyla ayrı eğitilir (ör. ezilme yalnız duran
koşularda var). Metrikler K-fold çapraz doğrulamadan (`cross_val_predict`):
her satırın tahmini, o satırı görmemiş modelden — eğitim skoru raporlanmaz.

Model dosyası `uploads/models/crash/<şablon>/<senaryo>.joblib`; durability
`model_store` klasörlerinden ayrı. Tahmin, eğitim aralığı dışındaki girdiyi
`out_of_domain` olarak listeler — engellemez, mühendis görür.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import KFold, cross_val_predict

from app.ml.crash.corpus import CrashCorpus

KIND = "crash_rf"
#: Hedef başına en az dolu satır; altında o hedefin modeli yok (None).
MIN_SAMPLES = 8
DEFAULT_FOLDS = 5
MODELS_ROOT = Path("uploads") / "models" / "crash"
_NAME_RE = re.compile(r"^[a-z0-9_]{1,64}$")


class CrashModelError(ValueError):
    pass


def _cv_metrics(y: np.ndarray, pred: np.ndarray) -> dict[str, float]:
    denom = np.maximum(np.abs(y), 1e-12)
    return {
        "n": int(len(y)),
        "r2": float(r2_score(y, pred)),
        "mae": float(mean_absolute_error(y, pred)),
        "mape": float(np.mean(np.abs(y - pred) / denom)),
    }


def train_crash_surrogate(
    corpus: CrashCorpus,
    *,
    seed: int = 2026,
    n_folds: int = DEFAULT_FOLDS,
    n_estimators: int = 200,
) -> dict[str, Any]:
    if not corpus.run_ids:
        raise CrashModelError("Korpus boş.")
    # Eksik değerli girdi sütunu (bazı koşularda alan yok) modele girmez; listelenir.
    full = [j for j in range(corpus.X.shape[1]) if np.all(np.isfinite(corpus.X[:, j]))]
    feature_keys = [corpus.feature_names[j] for j in full]
    dropped_features = [k for j, k in enumerate(corpus.feature_names) if j not in full]
    if not feature_keys:
        raise CrashModelError("Tüm koşularda dolu ve değişen girdi sütunu yok.")
    X = corpus.X[:, full]

    models: dict[str, RandomForestRegressor | None] = {}
    metrics: dict[str, Any] = {}
    for i, key in enumerate(corpus.target_names):
        ok = np.isfinite(corpus.Y[:, i])
        n = int(ok.sum())
        if n < MIN_SAMPLES:
            models[key] = None
            metrics[key] = {"n": n, "skipped": f"en az {MIN_SAMPLES} dolu satır gerekir"}
            continue
        Xk, yk = X[ok], corpus.Y[ok, i]
        rf = RandomForestRegressor(n_estimators=n_estimators, random_state=seed)
        folds = KFold(n_splits=min(n_folds, n), shuffle=True, random_state=seed)
        metrics[key] = {**_cv_metrics(yk, cross_val_predict(rf, Xk, yk, cv=folds)), "folds": folds.n_splits}
        models[key] = rf.fit(Xk, yk)

    return {
        "kind": KIND,
        "template_id": corpus.template_id,
        "scenario": corpus.scenario,
        "study_id": corpus.study_id,
        "run_ids": list(corpus.run_ids),
        "feature_keys": feature_keys,
        "dropped_features": dropped_features,
        "constant_features": dict(corpus.constant_features),
        "target_keys": list(corpus.target_names),
        "models": models,
        "bounds": {k: [float(X[:, j].min()), float(X[:, j].max())] for j, k in enumerate(feature_keys)},
        "seed": seed,
        "metrics_cv": metrics,
    }


def predict(bundle: dict[str, Any], inputs: dict[str, float]) -> dict[str, Any]:
    """Girdi sözlüğü (özellik adı → değer) → hedef tahminleri + aralık dışı girdiler."""
    missing = [k for k in bundle["feature_keys"] if k not in inputs]
    if missing:
        raise CrashModelError(f"Eksik girdi: {', '.join(missing)}")
    x = np.array([[float(inputs[k]) for k in bundle["feature_keys"]]])
    ood = [
        k for k in bundle["feature_keys"]
        if not (bundle["bounds"][k][0] <= float(inputs[k]) <= bundle["bounds"][k][1])
    ]
    pred: dict[str, float | None] = {}
    for key in bundle["target_keys"]:
        m = bundle["models"].get(key)
        v = float(m.predict(x)[0]) if m is not None else None
        pred[key] = v if v is not None and math.isfinite(v) else None
    return {"prediction": pred, "out_of_domain": ood}


def model_path(template_id: str, scenario: str, *, root: Path | None = None) -> Path:
    for name in (template_id, scenario):
        if not _NAME_RE.match(name or ""):
            raise CrashModelError(f"Geçersiz ad: {name!r}")
    return (root or MODELS_ROOT) / template_id / f"{scenario}.joblib"


def save_crash_model(bundle: dict[str, Any], *, root: Path | None = None) -> Path:
    dest = model_path(bundle["template_id"], bundle["scenario"], root=root)
    dest.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, dest)
    return dest


def load_crash_model(template_id: str, scenario: str, *, root: Path | None = None) -> dict[str, Any] | None:
    dest = model_path(template_id, scenario, root=root)
    return joblib.load(dest) if dest.is_file() else None
