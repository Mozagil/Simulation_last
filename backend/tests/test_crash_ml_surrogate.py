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


# --- 1.27a — türler: rf / loglinear / hybrid / auto ---------------------------


def _power_corpus(n: int = 60, seed: int = 1) -> CrashCorpus:
    """Güç yasası hedef (F ∝ t^1.0 · v^0.5), açı sütunu 0 içeriyor (log'a girmez)."""
    rng = np.random.default_rng(seed)
    t = rng.uniform(1.0, 4.0, n)
    v = rng.uniform(5.0, 15.0, n)
    ang = rng.choice([0.0, 10.0, 20.0], n)
    X = np.column_stack([t, v, ang])
    Y = np.full((n, len(TARGET_KEYS)), np.nan)
    Y[:, TARGET_KEYS.index("peak_force_kn")] = 30.0 * t * np.sqrt(v) * np.exp(-0.01 * ang)
    y2 = 2.0 * t - 3.0  # bazı satırlar ≤ 0 → log türleri o satırları atar
    Y[:, TARGET_KEYS.index("energy_absorbed_j")] = y2
    return CrashCorpus(
        template_id="crash_box_shell", scenario="rigid_wall", run_ids=list(range(n)),
        feature_names=["geom.wall", "req.barrier.speed_m_s", "req.barrier.angle_deg"],
        X=X, target_names=list(TARGET_KEYS), Y=Y, study_id=9,
    )


def test_design_spec_logs_only_positive_columns():
    b = train_crash_surrogate(_power_corpus(), kind="loglinear")
    assert b["design_spec"]["log_keys"] == ["geom.wall", "req.barrier.speed_m_s"]
    assert b["design_spec"]["raw_keys"] == ["req.barrier.angle_deg"]


@pytest.mark.parametrize("kind", ["rf", "loglinear", "hybrid"])
def test_single_kind_trains_and_predicts(kind):
    b = train_crash_surrogate(_power_corpus(), kind=kind)
    assert b["requested_kind"] == kind and b["chosen"]["peak_force_kn"] == kind
    m = b["metrics_cv"]["peak_force_kn"]
    assert m["kind"] == kind and set(m["kinds"]) == {kind}
    r = predict(b, {"geom.wall": 2.0, "req.barrier.speed_m_s": 9.0, "req.barrier.angle_deg": 10.0})
    assert r["prediction"]["peak_force_kn"] == pytest.approx(30 * 2 * 3 * np.exp(-0.1), rel=0.15)
    assert r["chosen"]["peak_force_kn"] == kind


def test_loglinear_beats_rf_on_power_law_and_auto_picks_it():
    b = train_crash_surrogate(_power_corpus(), kind="auto")
    kinds = b["metrics_cv"]["peak_force_kn"]["kinds"]
    assert kinds["loglinear"]["mape"] < kinds["rf"]["mape"]
    assert b["chosen"]["peak_force_kn"] in ("loglinear", "hybrid")
    # ≤ 0 hedefli satırlar log türlerinde atılır, RF hepsini kullanır
    e = b["metrics_cv"]["energy_absorbed_j"]["kinds"]
    assert e["rf"]["n"] == 60 and e["loglinear"]["n"] < 60 and e["loglinear"]["dropped_nonpositive"] > 0
    # dışarıda kalan değerle tahmin: aralık dışı ayrıntısı
    r = predict(b, {"geom.wall": 9.0, "req.barrier.speed_m_s": 9.0, "req.barrier.angle_deg": 10.0})
    assert r["out_of_domain"] == ["geom.wall"]
    assert r["out_of_domain_detail"][0]["side"] == "above"


def test_unknown_kind_rejected():
    with pytest.raises(CrashModelError, match="Bilinmeyen tür"):
        train_crash_surrogate(_power_corpus(), kind="svm")


def test_auto_roundtrip_keeps_loglinear_model(tmp_path):
    b = train_crash_surrogate(_power_corpus(), kind="auto")
    save_crash_model(b, root=tmp_path)
    b2 = load_crash_model("crash_box_shell", "rigid_wall", root=tmp_path)
    assert b2["chosen"] == b["chosen"]
    x = {"geom.wall": 2.5, "req.barrier.speed_m_s": 12.0, "req.barrier.angle_deg": 0.0}
    assert predict(b2, x)["prediction"] == predict(b, x)["prediction"]
