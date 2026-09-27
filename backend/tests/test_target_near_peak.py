"""Tepe merkezli gerilme skaler modellerin hedefi (TODO 6 — kalan)."""

from __future__ import annotations

import math

import numpy as np

from app.ml.scalar_features import TARGET_KEYS, targets_from_run
from app.ml.scalar_rf import predict_scalar, train_scalar_rf
from app.models.run import AnalysisRun


def test_hedef_listesinde_ve_run_dan_okunur():
    assert TARGET_KEYS[-1] == "max_von_mises_near_peak"
    run = AnalysisRun(scalars={
        "max_displacement": 2.0, "max_von_mises": 300.0,
        "max_von_mises_away": 250.0, "max_von_mises_near_peak": 240.0,
    })
    y = targets_from_run(run)
    assert y.shape == (len(TARGET_KEYS),)
    assert y[TARGET_KEYS.index("max_von_mises_near_peak")] == 240.0


def test_eksikse_nan_run_dusmez():
    """Geriye doldurma öncesi / şablonsuz run: yalnız o hedef atlanır."""
    y = targets_from_run(AnalysisRun(scalars={"max_displacement": 2.0, "max_von_mises": 300.0}))
    assert y is not None
    assert math.isnan(y[TARGET_KEYS.index("max_von_mises_near_peak")])


def test_eski_uc_hedefli_model_hala_okunur():
    """Diskteki modeller 3 hedefle eğitildi; tahmin bundle'ın kendi listesini kullanır."""
    rng = np.random.default_rng(0)
    X = rng.uniform(1.0, 2.0, size=(24, 11))
    y = np.column_stack([X[:, 0], X[:, 1] * 10, X[:, 2] * 5])  # 3 sütun → 4. NaN
    bundle = train_scalar_rf(X, y, n_estimators=10)
    assert bundle["models"]["max_von_mises_near_peak"] is None
    bundle["target_keys"] = list(TARGET_KEYS[:3])  # eski dosya gibi
    out = predict_scalar(bundle, X[0])
    assert "max_von_mises_near_peak" not in out["predictions"]
