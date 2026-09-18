"""Skaler Random Forest baseline (0.5.6).

AmaÃ§: veri boru hattÄ±nÄ±n ucuza doÄŸrulanmasÄ±. Skaler surrogate Ã¼rÃ¼n hedefi
deÄŸildir â€” kontur buradan Ã§izilmez.
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
#: AyrÄ± bir holdout ayÄ±rmak iÃ§in gereken en az Ã¶rnek.
#:
#: AltÄ±nda test seti AYRILMAZ ve test metriÄŸi RAPORLANMAZ. Daha Ã¶nce bu
#: durumda `X_te = X_tr` atanÄ±yordu; sonuÃ§, `metrics["test"]` adÄ± altÄ±nda
#: eÄŸitim RÂ²'sinin raporlanmasÄ±ydÄ±. Ã–lÃ§Ã¼ldÃ¼: 8 Ã¶rneklik sette "test RÂ² =
#: 0.739" gÃ¶steriliyordu, o sayÄ± modelin kendi eÄŸitim verisindeki
#: baÅŸarÄ±sÄ±ydÄ± ve genelleme hakkÄ±nda hiÃ§bir ÅŸey sÃ¶ylemiyordu. Sessiz yanlÄ±ÅŸ
#: sayÄ±, eksik sayÄ±dan kÃ¶tÃ¼dÃ¼r.
MIN_HOLDOUT_SAMPLES = 12
DEFAULT_MODEL_PATH = Path("uploads") / "models" / "scalar_rf.joblib"


def split_metrics(y_true: np.ndarray, y_pred: np.ndarray, keys: tuple[str, ...]) -> dict[str, Any]:
    """Hedef basina R2 / MAE / MAPE. `scalar_loglinear` da bunu kullanir â€”
    iki model turunun sayilari ayni tanimla uretilmezse kiyaslanamaz."""
    out: dict[str, Any] = {}
    for i, key in enumerate(keys):
        yt = y_true[:, i]
        yp = y_pred[:, i]
        # Hedef-bazlÄ± maskeleme sonrasÄ± bazÄ± satÄ±rlar NaN olabilir (o run'da
        # o skaler yok). Metrik yalnÄ±z dolu satÄ±rlardan hesaplanÄ±r; hiÃ§
        # dolu satÄ±r yoksa hedef iÃ§in metrik None dÃ¶ner.
        finite = np.isfinite(yt) & np.isfinite(yp)
        if not finite.any():
            out[key] = None
            continue
        yt = yt[finite]
        yp = yp[finite]
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
        raise ValueError(f"En az {MIN_SAMPLES} Ã§Ã¶zÃ¼lmÃ¼ÅŸ Ã¶rnek gerekir (var: {X.shape[0]}).")
    # Hedef sutun sayisi TARGET_KEYS ile uyusmali. Eksikse NaN ile
    # tamamlanir: cagiran yeni bir hedefi (max_von_mises_away) bilmiyorsa
    # ya da o skaler henuz hesaplanmamissa patlamak yerine o hedef
    # atlanir. Fazlaysa sessizce kirpmak veri kaybini gizler -> hata.
    y = np.asarray(y, dtype=np.float64)
    if y.ndim != 2:
        raise ValueError(f"y 2 boyutlu olmali (geldi: {y.shape}).")
    n_targets = len(TARGET_KEYS)
    if y.shape[1] > n_targets:
        raise ValueError(
            f"y {y.shape[1]} sutunlu ama {n_targets} hedef tanimli."
        )
    if y.shape[1] < n_targets:
        pad = np.full((y.shape[0], n_targets - y.shape[1]), np.nan)
        y = np.hstack([y, pad])

    has_holdout = X.shape[0] >= MIN_HOLDOUT_SAMPLES
    if has_holdout:
        X_tr, X_te, y_tr, y_te = train_test_split(
            X, y, test_size=test_size, random_state=seed
        )
    else:
        # Holdout yok: eÄŸitim verisi test verisi olarak GEÃ‡Ä°RÄ°LMEZ.
        X_tr, y_tr = X, y
        X_te = y_te = None

    models: dict[str, RandomForestRegressor] = {}
    pred_tr = np.zeros_like(y_tr)
    pred_te = np.zeros_like(y_te) if y_te is not None else None
    for i, key in enumerate(TARGET_KEYS):
        rf = RandomForestRegressor(
            n_estimators=n_estimators,
            random_state=seed,
            min_samples_leaf=1,
        )
        ok = np.isfinite(y_tr[:, i])
        if int(ok.sum()) < MIN_SAMPLES:
            models[key] = None
            pred_tr[:, i] = np.nan
            if pred_te is not None:
                pred_te[:, i] = np.nan
            continue
        rf.fit(X_tr[ok], y_tr[ok, i])
        models[key] = rf
        pred_tr[:, i] = np.where(ok, rf.predict(X_tr), np.nan)
        if pred_te is not None and X_te is not None and y_te is not None:
            ok_te = np.isfinite(y_te[:, i])
            pred_te[:, i] = np.where(ok_te, rf.predict(X_te), np.nan)

    bundle = {
        "kind": "scalar_rf",
        "feature_keys": list(FEATURE_KEYS),
        "target_keys": list(TARGET_KEYS),
        "models": models,
        "bounds": bounds_from_matrix(X),
        "n_samples": int(X.shape[0]),
        "n_train": int(X_tr.shape[0]),
        "n_test": int(X_te.shape[0]) if X_te is not None else 0,
        "has_holdout": has_holdout,
        "seed": seed,
        "metrics": {
            "train": split_metrics(y_tr, pred_tr, TARGET_KEYS),
            "test": (
                split_metrics(y_te, pred_te, TARGET_KEYS)
                if has_holdout and y_te is not None and pred_te is not None
                else None
            ),
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
        m = (bundle.get("models") or {}).get(key)
        preds[key] = float(m.predict(vec)[0]) if m is not None else None
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
        # Eski bundle'larda alan yok; o dosyalar test=train ile yazÄ±lmÄ±ÅŸtÄ±,
        # bu yÃ¼zden varsayÄ±lan False (holdout yok) doÄŸru yorumdur.
        "has_holdout": bool(bundle.get("has_holdout", False)),
        "metrics": bundle.get("metrics"),
        "feature_keys": bundle.get("feature_keys"),
        "target_keys": bundle.get("target_keys"),
        "bounds": bundle.get("bounds"),
        "corpus": bundle.get("corpus"),
    }
