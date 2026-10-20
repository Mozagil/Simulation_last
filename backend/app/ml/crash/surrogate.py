"""Crash vekil modeli — 1.19d RF + K-fold CV; 1.27a tür seçimi.

Girdi bir `CrashCorpus` (1.19b, tercihen tek DOE çalışması — 1.19c-3).
Her hedef kendi dolu satırlarıyla ayrı eğitilir (ör. ezilme yalnız duran
koşularda var). Metrikler K-fold çapraz doğrulamadan (`cross_val_predict`):
her satırın tahmini, o satırı görmemiş modelden — eğitim skoru raporlanmaz.

TÜRLER (durability 0.6.3 ile aynı üçlü, crash hedeflerine uyarlanmış):
- `rf`        Random Forest (ham özellikler).
- `loglinear` log uzayında en küçük kareler: y = Π xᵢ^aᵢ · e^(Σ bⱼ zⱼ).
              Tüm satırlarda pozitif olan özellikler log; diğerleri (açı,
              c=0 gibi) ham. Hedef pozitif olmalı; ≤ 0 satırlar dışarıda kalır.
- `hybrid`    log-lineer iskelet + log artıklarını ham özelliklerde RF.
- `auto`      üçünü de eğitir, HEDEF BAŞINA CV MAPE'si en düşük olanı seçer
              (`chosen`). Hangi türün iyi olduğu veriden; peşin karar yok.

Model dosyası `uploads/models/crash/<şablon>/<senaryo>.joblib`. Tahmin,
eğitim aralığı dışındaki girdiyi `out_of_domain` olarak listeler (ortak
`app.ml.ood`) — engellemez, mühendis görür.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import KFold, cross_val_predict

from app.ml.crash.corpus import CrashCorpus
from app.ml.ood import domain_violations

KIND = "crash_rf"
KINDS = ("rf", "loglinear", "hybrid")
#: Hedef başına en az dolu satır; altında o hedefin modeli yok (None).
MIN_SAMPLES = 8
DEFAULT_FOLDS = 5
MODELS_ROOT = Path("uploads") / "models" / "crash"
_NAME_RE = re.compile(r"^[a-z0-9_]{1,64}$")
_FLOOR = 1e-12


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


def crash_design_spec(feature_keys: list[str], X: np.ndarray) -> dict[str, Any]:
    """Log tasarımı: her satırda > 0 olan sütunlar log, diğerleri ham (çarpan etkisi)."""
    pos = [bool(np.all(X[:, j] > 0)) for j in range(X.shape[1])]
    return {
        "feature_keys": list(feature_keys),
        "log_keys": [k for k, p in zip(feature_keys, pos) if p],
        "raw_keys": [k for k, p in zip(feature_keys, pos) if not p],
    }


def _design(X: np.ndarray, spec: dict[str, Any]) -> np.ndarray:
    idx = {k: i for i, k in enumerate(spec["feature_keys"])}
    cols = [np.log(np.maximum(X[:, idx[k]], _FLOOR)) for k in spec["log_keys"]]
    cols += [X[:, idx[k]] for k in spec["raw_keys"]]
    return np.column_stack(cols)


class _LogLinear:
    """Tek hedef: log y = w·design (+ RF artığı). sklearn tahmincisi gibi fit/predict."""

    def __init__(self, spec: dict[str, Any], *, residual: bool, seed: int) -> None:
        self.spec, self.residual, self.seed = spec, residual, seed
        self.lin = LinearRegression()
        self.rf: RandomForestRegressor | None = None

    def fit(self, X: np.ndarray, y: np.ndarray) -> "_LogLinear":
        ly = np.log(y)
        d = _design(X, self.spec)
        self.lin = LinearRegression().fit(d, ly)
        if self.residual:
            self.rf = RandomForestRegressor(n_estimators=200, min_samples_leaf=2, random_state=self.seed)
            self.rf.fit(X, ly - self.lin.predict(d))
        else:
            self.rf = None
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        lp = self.lin.predict(_design(X, self.spec))
        if self.rf is not None:
            lp = lp + self.rf.predict(X)
        return np.exp(lp)

    # cross_val_predict klonlayabilsin
    def get_params(self, deep: bool = True) -> dict[str, Any]:
        return {"spec": self.spec, "residual": self.residual, "seed": self.seed}

    def set_params(self, **p: Any) -> "_LogLinear":
        for k, v in p.items():
            setattr(self, k, v)
        return self

    def __sklearn_clone__(self) -> "_LogLinear":
        return _LogLinear(self.spec, residual=self.residual, seed=self.seed)


def _estimator(kind: str, spec: dict[str, Any], seed: int, n_estimators: int) -> Any:
    if kind == "rf":
        return RandomForestRegressor(n_estimators=n_estimators, random_state=seed)
    if kind == "loglinear":
        return _LogLinear(spec, residual=False, seed=seed)
    if kind == "hybrid":
        return _LogLinear(spec, residual=True, seed=seed)
    raise CrashModelError(f"Bilinmeyen tür: {kind!r} (rf | loglinear | hybrid | auto)")


def train_crash_surrogate(
    corpus: CrashCorpus,
    *,
    kind: str = "auto",
    seed: int = 2026,
    n_folds: int = DEFAULT_FOLDS,
    n_estimators: int = 200,
) -> dict[str, Any]:
    if not corpus.run_ids:
        raise CrashModelError("Korpus boş.")
    kinds = list(KINDS) if kind == "auto" else [kind]
    for k in kinds:
        _estimator(k, {"feature_keys": [], "log_keys": [], "raw_keys": []}, seed, n_estimators)  # ad doğrulama
    # Eksik değerli girdi sütunu (bazı koşularda alan yok) modele girmez; listelenir.
    full = [j for j in range(corpus.X.shape[1]) if np.all(np.isfinite(corpus.X[:, j]))]
    feature_keys = [corpus.feature_names[j] for j in full]
    dropped_features = [k for j, k in enumerate(corpus.feature_names) if j not in full]
    if not feature_keys:
        raise CrashModelError("Tüm koşullarda dolu ve değişen girdi sütunu yok.")
    X = corpus.X[:, full]
    spec = crash_design_spec(feature_keys, X)

    models: dict[str, Any] = {}
    chosen: dict[str, str | None] = {}
    metrics: dict[str, Any] = {}
    for i, key in enumerate(corpus.target_names):
        ok = np.isfinite(corpus.Y[:, i])
        n = int(ok.sum())
        if n < MIN_SAMPLES:
            models[key], chosen[key] = None, None
            metrics[key] = {"n": n, "skipped": f"en az {MIN_SAMPLES} dolu satır gerekir"}
            continue
        Xk, yk = X[ok], corpus.Y[ok, i]
        per_kind: dict[str, Any] = {}
        fitted: dict[str, Any] = {}
        for k in kinds:
            Xs, ys = Xk, yk
            if k != "rf":
                pos = ys > 0
                if int(pos.sum()) < MIN_SAMPLES:
                    per_kind[k] = {"n": int(pos.sum()), "skipped": "log için pozitif hedef gerekir"}
                    continue
                Xs, ys = Xs[pos], ys[pos]
            est = _estimator(k, spec, seed, n_estimators)
            folds = KFold(n_splits=min(n_folds, len(ys)), shuffle=True, random_state=seed)
            pred = cross_val_predict(est, Xs, ys, cv=folds)
            per_kind[k] = {**_cv_metrics(ys, pred), "folds": folds.n_splits}
            if len(ys) < len(yk):
                per_kind[k]["dropped_nonpositive"] = int(len(yk) - len(ys))
            fitted[k] = _estimator(k, spec, seed, n_estimators).fit(Xs, ys)
        usable = [k for k in kinds if k in fitted and math.isfinite(per_kind[k]["mape"])]
        if not usable:
            models[key], chosen[key] = None, None
            metrics[key] = {"n": n, "skipped": "hiçbir tür eğitilemedi", "kinds": per_kind}
            continue
        best = min(usable, key=lambda k: per_kind[k]["mape"])
        models[key], chosen[key] = fitted[best], best
        metrics[key] = {**per_kind[best], "kind": best, "kinds": per_kind}

    return {
        "kind": KIND,
        "requested_kind": kind,
        "template_id": corpus.template_id,
        "scenario": corpus.scenario,
        "study_id": corpus.study_id,
        "run_ids": list(corpus.run_ids),
        "feature_keys": feature_keys,
        "dropped_features": dropped_features,
        "constant_features": dict(corpus.constant_features),
        "design_spec": spec,
        "target_keys": list(corpus.target_names),
        "models": models,
        "chosen": chosen,
        "bounds": {k: [float(X[:, j].min()), float(X[:, j].max())] for j, k in enumerate(feature_keys)},
        "seed": seed,
        "metrics_cv": metrics,
    }


def predict(bundle: dict[str, Any], inputs: dict[str, float]) -> dict[str, Any]:
    """Girdi sözlüğü (özellik adı → değer) → hedef tahminleri + aralık dışı girdiler.

    `out_of_domain`: aralık dışı özellik adları (ortak `ood.domain_violations`;
    ayrıntı `out_of_domain_detail`: değer, sınır, kaç kat).
    """
    keys = list(bundle["feature_keys"])
    missing = [k for k in keys if k not in inputs]
    if missing:
        raise CrashModelError(f"Eksik girdi: {', '.join(missing)}")
    x = np.array([[float(inputs[k]) for k in keys]])
    b = bundle["bounds"]
    detail = domain_violations(
        x.reshape(-1), {"min": [b[k][0] for k in keys], "max": [b[k][1] for k in keys]}, keys
    )
    pred: dict[str, float | None] = {}
    for key in bundle["target_keys"]:
        m = bundle["models"].get(key)
        v = float(m.predict(x)[0]) if m is not None else None
        pred[key] = v if v is not None and math.isfinite(v) else None
    return {
        "prediction": pred,
        "out_of_domain": [d["feature"] for d in detail],
        "out_of_domain_detail": detail,
        "chosen": dict(bundle.get("chosen") or {}),
    }


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
