"""0.6.3 log-log lineer skaler model.

Sentetik veri BİLE BİLE kiriş teorisinden üretilir: model üsleri geri
bulabiliyor mu, sabit sütunu işaretliyor mu, RF ile aynı sözleşmeyi
koruyor mu.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.ml.scalar_features import FEATURE_KEYS, TARGET_KEYS
from app.ml.scalar_loglinear import (
    DESIGN_KEYS,
    constant_columns,
    load_scalar_loglinear,
    predict_scalar_loglinear,
    public_metrics_loglinear,
    save_scalar_loglinear,
    to_log_features,
    train_scalar_loglinear,
)

IDX = {k: i for i, k in enumerate(FEATURE_KEYS)}
E_PA = 210e9
E_MPA = E_PA / 1e6


def _beam_dataset(
    n: int = 120, *, seed: int = 3, vary_e: bool = False, fixed_ratio: bool = False
):
    """Ankastre kirişin kapalı formundan tam veri (gürültüsüz).

    `fixed_ratio`: eleman boyutu T ile birebir bağlı olur — DOE sabit bir
    oranla koşulursa oluşan durum. Gerçek korpus 0.5–0.8 taradığı için
    varsayılan değişken orandır.
    """
    rng = np.random.default_rng(seed)
    L = rng.uniform(400.0, 700.0, n)
    T = rng.uniform(10.0, 16.0, n)
    W = rng.uniform(40.0, 70.0, n)
    F = rng.uniform(40.0, 220.0, n)
    e_pa = rng.uniform(69e9, 210e9, n) if vary_e else np.full(n, E_PA)

    X = np.zeros((n, len(FEATURE_KEYS)))
    X[:, IDX["length"]] = L
    X[:, IDX["thickness"]] = T
    X[:, IDX["width"]] = W
    ratio = np.full(n, 0.65) if fixed_ratio else rng.uniform(0.5, 0.8, n)
    X[:, IDX["element_size"]] = ratio * T
    X[:, IDX["youngs_modulus"]] = e_pa
    X[:, IDX["poisson_ratio"]] = 0.3
    X[:, IDX["load_fy"]] = -F
    X[:, IDX["dimension"]] = 3.0

    inertia = W * T**3 / 12.0
    u = F * L**3 / (3.0 * (e_pa / 1e6) * inertia)
    vm = F * L * (T / 2.0) / inertia
    return X, np.column_stack([u, vm])


def test_recovers_beam_theory_exponents():
    X, y = _beam_dataset(vary_e=True)
    bundle = train_scalar_loglinear(X, y)

    exps = {
        e["feature"]: e["exponent"] for e in bundle["exponents"]["max_displacement"]
    }
    assert exps["length"] == pytest.approx(3.0, abs=0.02)
    assert exps["thickness"] == pytest.approx(-3.0, abs=0.02)
    assert exps["width"] == pytest.approx(-1.0, abs=0.02)
    assert exps["youngs_modulus"] == pytest.approx(-1.0, abs=0.02)
    assert exps["|load_fy|"] == pytest.approx(1.0, abs=0.02)

    exps = {e["feature"]: e["exponent"] for e in bundle["exponents"]["max_von_mises"]}
    assert exps["length"] == pytest.approx(1.0, abs=0.02)
    assert exps["thickness"] == pytest.approx(-2.0, abs=0.02)
    assert exps["width"] == pytest.approx(-1.0, abs=0.02)
    assert exps["youngs_modulus"] == pytest.approx(0.0, abs=0.02)


def test_fits_power_law_almost_exactly():
    X, y = _beam_dataset(vary_e=True)
    bundle = train_scalar_loglinear(X, y)
    # Veri seti 2 sütunlu; `max_von_mises_away` hedefi yoksa metriği
    # None döner (uydurma sayı yerine). Dolu hedeflerin hepsi tam
    # oturmalı — fizik saf kuvvet yasası.
    scored = {
        k: m for k, m in bundle["metrics"]["test"].items() if m is not None
    }
    assert scored, "hiçbir hedef puanlanmamış"
    for key, m in scored.items():
        assert m["r2"] == pytest.approx(1.0, abs=1e-6), key
        assert m["mape"] < 1e-6, key


def test_constant_feature_is_flagged_as_unidentifiable():
    """Tek malzemede E sabittir; o üs veriden ÇIKARILAMAZ."""
    X, y = _beam_dataset(vary_e=False)
    bundle = train_scalar_loglinear(X, y)

    assert "youngs_modulus" in bundle["constant_features"]
    assert "poisson_ratio" in bundle["constant_features"]
    assert "length" not in bundle["constant_features"]

    by_name = {e["feature"]: e for e in bundle["exponents"]["max_displacement"]}
    assert by_name["youngs_modulus"]["identifiable"] is False
    assert by_name["length"]["identifiable"] is True


def test_fixed_mesh_ratio_makes_thickness_exponent_unidentifiable():
    """es = 0.65 × T ise log uzayında T ile birebir bağımlıdır.

    Gerçek −3 üssü iki sütun arasında KEYFİ bölünür; toplamları doğru kalır.
    Tahmin bundan zarar görmez — eşdoğrusallık kestirimi bozar, uyumu değil.
    """
    X, y = _beam_dataset(fixed_ratio=True)
    bundle = train_scalar_loglinear(X, y)

    assert ["thickness", "element_size"] in bundle["collinear_features"]
    by_name = {e["feature"]: e for e in bundle["exponents"]["max_displacement"]}
    assert by_name["thickness"]["identifiable"] is False
    assert by_name["element_size"]["identifiable"] is False
    assert "eşdoğrusal" in by_name["thickness"]["reason"]
    # Ayrı ayrı okunamaz ama TOPLAMLARI doğru −3.
    assert by_name["thickness"]["exponent"] + by_name["element_size"]["exponent"] == (
        pytest.approx(-3.0, abs=0.02)
    )
    assert bundle["metrics"]["test"]["max_displacement"]["r2"] == pytest.approx(
        1.0, abs=1e-6
    )
    assert by_name["length"]["identifiable"] is True


def test_varying_mesh_ratio_keeps_exponents_identifiable():
    """Gerçek korpus oran 0.5–0.8 taradı; eşdoğrusallık kırıldı."""
    X, y = _beam_dataset(fixed_ratio=False)
    bundle = train_scalar_loglinear(X, y)

    assert bundle["collinear_features"] == []
    by_name = {e["feature"]: e for e in bundle["exponents"]["max_displacement"]}
    assert by_name["thickness"]["identifiable"] is True
    assert by_name["thickness"]["reason"] is None


def test_constant_columns_matches_design_keys():
    X, _ = _beam_dataset(vary_e=False)
    assert to_log_features(X).shape == (X.shape[0], len(DESIGN_KEYS))
    assert set(constant_columns(X)) <= set(DESIGN_KEYS)


def test_prediction_contract_matches_rf():
    X, y = _beam_dataset()
    bundle = train_scalar_loglinear(X, y)
    out = predict_scalar_loglinear(bundle, X[0])

    assert set(out) == {"kind", "predictions", "out_of_domain"}
    assert out["kind"] == "scalar"
    assert set(out["predictions"]) == set(TARGET_KEYS)
    assert out["out_of_domain"] is False
    assert out["predictions"]["max_displacement"] == pytest.approx(y[0, 0], rel=1e-6)


def test_out_of_domain_flag_fires_outside_training_box():
    X, y = _beam_dataset()
    bundle = train_scalar_loglinear(X, y)
    far = X[0].copy()
    far[IDX["length"]] = 5000.0
    assert predict_scalar_loglinear(bundle, far)["out_of_domain"] is True


def test_non_positive_target_is_rejected():
    X, y = _beam_dataset(n=20)
    y[3, 0] = 0.0
    with pytest.raises(ValueError, match="pozitif hedef"):
        train_scalar_loglinear(X, y)


def test_no_holdout_reports_no_test_metrics():
    X, y = _beam_dataset(n=9)
    bundle = train_scalar_loglinear(X, y)
    assert bundle["has_holdout"] is False
    assert bundle["n_test"] == 0
    assert bundle["metrics"]["test"] is None


def test_save_load_round_trip(tmp_path):
    X, y = _beam_dataset()
    bundle = train_scalar_loglinear(X, y)
    path = save_scalar_loglinear(bundle, tmp_path / "m.joblib")
    again = load_scalar_loglinear(path)

    assert again is not None
    assert again["kind"] == "scalar_loglinear"
    before = predict_scalar_loglinear(bundle, X[5])["predictions"]
    after = predict_scalar_loglinear(again, X[5])["predictions"]
    assert after == pytest.approx(before)
    assert load_scalar_loglinear(tmp_path / "yok.joblib") is None


def test_public_metrics_exposes_exponents():
    X, y = _beam_dataset()
    pub = public_metrics_loglinear(train_scalar_loglinear(X, y))
    assert pub["kind"] == "scalar_loglinear"
    assert pub["has_holdout"] is True
    assert set(pub["exponents"]) == set(TARGET_KEYS)
    assert pub["constant_features"]
