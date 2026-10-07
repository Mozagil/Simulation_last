"""1.19d — crash vekil modeli: K-fold CV metrikleri, eksik hedef, kayıt, tahmin."""

from __future__ import annotations

import numpy as np
import pytest

from app.ml.crash.corpus import CrashCorpus
from app.ml.crash.surrogate import (
    MIN_SAMPLES,
    CrashModelError,
    load_crash_model,
    predict,
    save_crash_model,
    train_crash_surrogate,
)
from app.postprocess.crash_targets import TARGET_KEYS


def _corpus(n: int = 40, seed: int = 0) -> CrashCorpus:
    rng = np.random.default_rng(seed)
    speed = rng.uniform(5.0, 15.0, n)
    wall = rng.uniform(1.0, 3.0, n)
    sparse = np.where(np.arange(n) % 2 == 0, 1.0, np.nan)  # bazı koşularda yok
    X = np.column_stack([speed, wall, sparse])
    Y = np.full((n, len(TARGET_KEYS)), np.nan)
    Y[:, TARGET_KEYS.index("peak_force_kn")] = 40.0 * wall + 2.0 * speed
    Y[:, TARGET_KEYS.index("energy_absorbed_j")] = 0.5 * speed**2
    Y[: MIN_SAMPLES - 1, TARGET_KEYS.index("crush_mm")] = 1.0  # çok az dolu satır
    return CrashCorpus(
        template_id="crash_box_shell", scenario="rigid_wall", run_ids=list(range(n)),
        feature_names=["req.barrier.speed_m_s", "geom.wall", "req.sparse"],
        X=X, target_names=list(TARGET_KEYS), Y=Y, study_id=7,
    )


def test_train_cv_metrics_and_skips():
    b = train_crash_surrogate(_corpus())
    assert b["feature_keys"] == ["req.barrier.speed_m_s", "geom.wall"]
    assert b["dropped_features"] == ["req.sparse"]
    assert b["study_id"] == 7
    m = b["metrics_cv"]
    assert m["peak_force_kn"]["n"] == 40 and m["peak_force_kn"]["folds"] == 5
    assert m["peak_force_kn"]["r2"] > 0.9 and m["energy_absorbed_j"]["r2"] > 0.9
    assert b["models"]["crush_mm"] is None and "skipped" in m["crush_mm"]
    assert b["models"]["mean_force_kn"] is None and m["mean_force_kn"]["n"] == 0


def test_predict_and_out_of_domain():
    b = train_crash_surrogate(_corpus())
    r = predict(b, {"req.barrier.speed_m_s": 10.0, "geom.wall": 2.0})
    assert r["out_of_domain"] == []
    assert r["prediction"]["peak_force_kn"] == pytest.approx(100.0, rel=0.1)
    assert r["prediction"]["crush_mm"] is None
    r2 = predict(b, {"req.barrier.speed_m_s": 30.0, "geom.wall": 2.0})
    assert r2["out_of_domain"] == ["req.barrier.speed_m_s"]
    with pytest.raises(CrashModelError):
        predict(b, {"geom.wall": 2.0})


def test_save_load_roundtrip(tmp_path):
    b = train_crash_surrogate(_corpus())
    path = save_crash_model(b, root=tmp_path)
    assert path == tmp_path / "crash_box_shell" / "rigid_wall.joblib"
    loaded = load_crash_model("crash_box_shell", "rigid_wall", root=tmp_path)
    x = {"req.barrier.speed_m_s": 7.0, "geom.wall": 1.5}
    assert predict(loaded, x) == predict(b, x)
    assert load_crash_model("crash_box_shell", "plate_ball", root=tmp_path) is None
    with pytest.raises(CrashModelError):
        load_crash_model("../x", "rigid_wall", root=tmp_path)


def test_empty_corpus_rejected():
    c = _corpus()
    c.run_ids = []
    with pytest.raises(CrashModelError):
        train_crash_surrogate(c)
