"""Tekillikten uzak gerilme ölçümü testleri."""

from __future__ import annotations

import numpy as np
import pytest

from app.dataset.training_data import NODE_INPUT_CHANNELS, NODE_OUTPUT_CHANNELS
from app.postprocess.stress_probe import (
    constrained_mask,
    distance_to_constraint,
    stress_away_from_constraint,
)

IDX = {n: i for i, n in enumerate(NODE_INPUT_CHANNELS)}
OUT = {n: i for i, n in enumerate(NODE_OUTPUT_CHANNELS)}


def _beam(n_along: int, singular_peak: float) -> tuple[np.ndarray, np.ndarray]:
    """Sentetik ankastre kiriş: x=0 kısıtlı, σ kiriş teorisine uyar ama
    x≈0'da tekillik gibi fırlayan bir tepe var.

    `n_along` değiştirilerek "mesh inceliyor" taklit edilir: tepe noktasına
    ne kadar yaklaşıldığı değişir, yani max σ mesh'e göre oynar. Gerçek
    taramada gördüğümüz davranışın ta kendisi.
    """
    L, T, W = 500.0, 10.0, 50.0
    F = 500.0
    I = W * T**3 / 12
    xs = np.linspace(0.0, L, n_along)
    X = np.zeros((n_along, len(NODE_INPUT_CHANNELS)), dtype=np.float64)
    Y = np.zeros((n_along, len(NODE_OUTPUT_CHANNELS)), dtype=np.float64)

    X[:, IDX["x"]] = xs
    X[:, IDX["y"]] = T / 2
    X[:, IDX["youngs_modulus_mpa"]] = 210000.0
    # x=0 düzlemi ankastre
    fixed = xs <= 1e-9
    for c in ("fixed_ux", "fixed_uy", "fixed_uz"):
        X[fixed, IDX[c]] = 1.0

    # Kiriş teorisi: σ(x) = F(L-x)(T/2)/I
    sigma = F * (L - xs) * (T / 2) / I
    # Tekillik: gerçek tekil noktada σ mesh inceldikçe BÜYÜR (σ ~ h^-α).
    # Eleman boyutuna bağlı bir tepe ekliyoruz ki "incelttikçe max artar"
    # davranışı taklit edilsin — maskesiz ölçümün neden yakınsamadığını
    # gösteren şey bu.
    h = L / (n_along - 1)
    amp = singular_peak * (10.0 / h) ** 0.3
    sigma = sigma + amp * np.exp(-xs / 0.8)
    Y[:, OUT["von_mises_mpa"]] = sigma
    return X, Y


class TestMask:
    def test_kisitli_dugumler_bulunur(self):
        X, _ = _beam(50, 0.0)
        m = constrained_mask(X)
        assert m.sum() == 1
        assert X[m, IDX["x"]][0] == 0.0

    def test_uzaklik_hesabi(self):
        X, _ = _beam(11, 0.0)  # x = 0,50,...,500
        d = distance_to_constraint(X)
        assert d[0] == pytest.approx(0.0)
        assert d[1] == pytest.approx(50.0)
        assert d[-1] == pytest.approx(500.0)

    def test_kisit_yoksa_sonsuz(self):
        X, _ = _beam(10, 0.0)
        X[:, IDX["fixed_ux"]] = 0.0
        X[:, IDX["fixed_uy"]] = 0.0
        X[:, IDX["fixed_uz"]] = 0.0
        d = distance_to_constraint(X)
        assert np.isinf(d).all()


class TestMaskeliGerilme:
    def test_maskesiz_max_meshe_gore_oynar(self):
        """Sorunun kendisini gösterir: standoff=0 iken max σ mesh'e bağlı."""
        peaks = []
        for n in (60, 120, 240, 480):
            X, Y = _beam(n, singular_peak=200.0)
            r = stress_away_from_constraint(X, Y, standoff_mm=0.0)
            peaks.append(r["max_von_mises_away"])
        spread = (max(peaks) - min(peaks)) / (sum(peaks) / len(peaks))
        assert spread > 0.10  # %10'dan fazla oynuyor

    def test_maskeli_max_meshten_bagimsiz(self):
        """Çözüm: 1×T uzakta ölçünce mesh etkisi kayboluyor."""
        vals = []
        for n in (60, 120, 240, 480):
            X, Y = _beam(n, singular_peak=200.0)
            r = stress_away_from_constraint(X, Y, standoff_mm=10.0)
            vals.append(r["max_von_mises_away"])
        spread = (max(vals) - min(vals)) / (sum(vals) / len(vals))
        assert spread < 0.02  # %2'nin altında

    def test_teorik_degere_yakin(self):
        # x=10 mm'de kiriş teorisi 294 MPa
        X, Y = _beam(2000, singular_peak=200.0)
        r = stress_away_from_constraint(X, Y, standoff_mm=10.0)
        assert r["max_von_mises_away"] == pytest.approx(294.0, rel=0.02)

    def test_kullanilan_dugum_orani_raporlanir(self):
        X, Y = _beam(100, singular_peak=0.0)
        r = stress_away_from_constraint(X, Y, standoff_mm=10.0)
        assert 0.0 < r["fraction_used"] < 1.0
        assert r["n_nodes_used"] > 0

    def test_cok_buyuk_standoff_uyari_verir(self):
        X, Y = _beam(50, singular_peak=0.0)
        r = stress_away_from_constraint(X, Y, standoff_mm=10_000.0)
        assert r["max_von_mises_away"] is None
        assert "standoff" in r["warning"]

    def test_maskesiz_deger_de_dondurulur(self):
        X, Y = _beam(100, singular_peak=200.0)
        r = stress_away_from_constraint(X, Y, standoff_mm=10.0)
        # Karşılaştırma yapılabilsin diye ikisi de raporlanır
        assert r["max_von_mises_all"] > r["max_von_mises_away"]
