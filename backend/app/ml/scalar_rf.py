"""Skaler Random Forest baseline (0.5.6).

Amaç: veri boru hattının ucuza doğrulanması. Skaler surrogate ürün hedefi
değildir — kontur buradan çizilmez.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split

from app.ml.ood import bounds_from_matrix, is_out_of_domain
from app.ml.scalar_features import FEATURE_KEYS, TARGET_KEYS

MIN_SAMPLES = 8
DEFAULT_MODEL_PATH = Path("uploads") / "models" / "scalar_rf.joblib"


def _metrics(y_true: np.ndarray, y_pred: np.ndarray, keys: tuple[str, ...]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for i, key in enumerate(keys):
        yt = y_true[:, i]
        yp = y_pred[:, i]
        mae = float(mean_absolute_error(yt, yp))
        denom = np.maximum(np.abs(yt), 1e-12)
        mape = float(np.mean(np.abs(yt - yp) / denom))
        out[key] = {
            "mae": mae,
            "mape": mape,
            "r2": float(r2_score(yt, yp)) if len(yt) >= 2 else None,
        }
    return out


def train_scalar_rf(
    X: np.ndarray,
    y: np.ndarray,
    *,
    seed: int = 2026,
    n_estimators: int = 80,
    test_size: float = 0.25,
) -> dict[str, Any]:
    if X.shape[0] < MIN_SAMPLES:
        raise ValueError(f"En az {MIN_SAMPLES} çözülmüş örnek gerekir (var: {X.shape[0]}).")
    if X.shape[0] >= 12:
        X_tr, X_te, y_tr, y_te = train_test_split(
            X, y, test_size=test_size, random_state=seed
        )
    else:
        X_tr, y_tr = X, y
        X_te, y_te = X, y

    models: dict[str, RandomForestRegressor] = {}
    pred_tr = np.zeros_like(y_tr)
    pred_te = np.zeros_like(y_te)
    for i, key in enumerate(TARGET_KEYS):
        rf = RandomForestRegressor(
            n_estimators=n_estimators,
            random_state=seed,
            min_samples_leaf=1,
        )
        rf.fit(X_tr, y_tr[:, i])
        models[key] = rf
        pred_tr[:, i] = rf.predict(X_tr)
        pred_te[:, i] = rf.predict(X_te)

    bundle = {
        "kind": "scalar_rf",
        "feature_keys": list(FEATURE_KEYS),
        "target_keys": list(TARGET_KEYS),
        "models": models,
        "bounds": bounds_from_matrix(X),
        "n_samples": int(X.shape[0]),
        "n_train": int(X_tr.shape[0]),
        "n_test": int(X_te.shape[0]),
        "seed": seed,
        "metrics": {
            "train": _metrics(y_tr, pred_tr, TARGET_KEYS),
            "test": _metrics(y_te, pred_te, TARGET_KEYS),
        },
    }
    return bundle


def save_scalar_rf(bundle: dict[str, Any], path: Path | None = None) -> Path:
    dest = path or DEFAULT_MODEL_PATH
    dest.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, dest)
    return dest


def load_scalar_rf(path: Path | None = None) -> dict[str, Any] | None:
    dest = path or DEFAULT_MODEL_PATH
    if not dest.is_file():
        return None
    return joblib.load(dest)


def predict_scalar(
    bundle: dict[str, Any],
    x: np.ndarray,
) -> dict[str, Any]:
    vec = np.asarray(x, dtype=np.float64).reshape(1, -1)
    preds: dict[str, float] = {}
    for key in bundle["target_keys"]:
        preds[key] = float(bundle["models"][key].predict(vec)[0])
    ood = is_out_of_domain(vec.reshape(-1), bundle.get("bounds") or {})
    return {
        "kind": "scalar",
        "predictions": preds,
        "out_of_domain": ood,
    }


def public_metrics(bundle: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": bundle.get("kind"),
        "n_samples": bundle.get("n_samples"),
        "n_train": bundle.get("n_train"),
        "n_test": bundle.get("n_test"),
        "metrics": bundle.get("metrics"),
        "feature_keys": bundle.get("feature_keys"),
        "target_keys": bundle.get("target_keys"),
        "bounds": bundle.get("bounds"),
        "corpus": bundle.get("corpus"),
    }
