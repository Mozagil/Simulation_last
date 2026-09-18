"""Skaler RF holdout testleri — sahte 'test' metriği regresyonu."""

from __future__ import annotations

import numpy as np
import pytest

from app.ml.scalar_rf import FEATURE_KEYS, MIN_SAMPLES, train_scalar_rf


def _data(n: int, seed: int = 0):
    rng = np.random.default_rng(seed)
    X = rng.uniform(1.0, 10.0, (n, len(FEATURE_KEYS)))
    # Öğrenilebilir ama birebir ezberlenemeyecek bir ilişki
    from app.ml.scalar_features import TARGET_KEYS

    cols = [X[:, 0] * 2.0 + X[:, 1], X[:, 0] * 3.0 - X[:, 2]]
    # Hedef sayısı kadar sütun üret (maskeli gerilme dahil)
    while len(cols) < len(TARGET_KEYS):
        cols.append(X[:, 0] * 2.5 - X[:, 3])
    return X, np.column_stack(cols)


class TestHoldout:
    def test_test_seti_egitimden_ayri(self):
        """Asıl regresyon: eskiden X_te = X_tr atanıyordu."""
        X, y = _data(40)
        b = train_scalar_rf(X, y)
        assert b["n_train"] + b["n_test"] == 40
        assert b["n_test"] > 0
        assert b["n_train"] != 40, "tüm veri eğitime gitmiş — holdout yok"

    def test_kucuk_veride_de_gercek_holdout(self):
        # Eskiden n<12 iken sahte metrik dönüyordu
        X, y = _data(MIN_SAMPLES)
        b = train_scalar_rf(X, y)
        assert b["holdout"]["ok"] is True
        assert b["n_test"] >= 2
        assert b["n_train"] < MIN_SAMPLES

    def test_test_metrigi_egitimden_farkli(self):
        """Aynı sayılar çıkıyorsa test aslında eğitimdir."""
        X, y = _data(60)
        b = train_scalar_rf(X, y)
        tr = b["metrics"]["train"]["max_displacement"]["r2"]
        te = b["metrics"]["test"]["max_displacement"]["r2"]
        assert tr is not None and te is not None
        assert tr != te

    def test_holdout_yoksa_test_metrigi_none(self):
        """Hesaplanamıyorsa sessizce yanlış sayı değil, açıkça None."""
        X, y = _data(40)
        b = train_scalar_rf(X, y, test_size=0.01)  # test tarafı < 2 satır
        if not b["holdout"]["ok"]:
            assert b["metrics"]["test"] is None
            assert "Holdout" in b["holdout"]["reason"]
            assert b["n_test"] == 0

    def test_min_ornek_altinda_hata(self):
        X, y = _data(MIN_SAMPLES - 1)
        with pytest.raises(ValueError, match="En az"):
            train_scalar_rf(X, y)

    def test_tohum_tekrarlanabilir(self):
        X, y = _data(50)
        a = train_scalar_rf(X, y, seed=7)
        b = train_scalar_rf(X, y, seed=7)
        assert (
            a["metrics"]["test"]["max_displacement"]["r2"]
            == b["metrics"]["test"]["max_displacement"]["r2"]
        )


class TestKuvvetYasasi:
    """Model fiziği öğreniyor mu — ezber değil, üsteller doğru mu."""

    @staticmethod
    def _beam(n=225, seed=7):
        from app.ml.scalar_features import FEATURE_KEYS

        rng = np.random.default_rng(seed)
        L = rng.uniform(400, 700, n)
        T = rng.uniform(8, 20, n)
        W = rng.uniform(30, 80, n)
        F = rng.uniform(20, 400, n)
        E = 210000.0
        I = W * T**3 / 12
        # Ölçülen gürültü tabanları: u %1.0, σ %1.2
        u = F * L**3 / (3 * E * I) * (1 + rng.normal(0, 0.010, n))
        s = F * L * (T / 2) / I * (1 + rng.normal(0, 0.012, n))
        X = np.zeros((n, len(FEATURE_KEYS)))
        k = {f: i for i, f in enumerate(FEATURE_KEYS)}
        X[:, k["length"]] = L
        X[:, k["thickness"]] = T
        X[:, k["width"]] = W
        X[:, k["element_size"]] = rng.uniform(0.5, 1.2, n) * T
        X[:, k["youngs_modulus"]] = 210e9
        X[:, k["poisson_ratio"]] = 0.3
        X[:, k["load_fy"]] = -F  # NEGATİF: log maskesi bunu kapsamalı
        X[:, k["dimension"]] = 3
        from app.ml.scalar_features import TARGET_KEYS

        cols = [u, s]
        while len(cols) < len(TARGET_KEYS):
            # Maskeli gerilme: aynı kuvvet yasası, köşe etkisi olmadan
            cols.append(F * L * (T / 2) / I * (1 + rng.normal(0, 0.012, n)))
        return X, np.column_stack(cols)

    def test_ustelleri_kiris_teorisinden_ogreniyor(self):
        X, y = self._beam()
        b = train_scalar_rf(X, y)
        e = b["exponents"]["max_displacement"]
        assert e["length"] == pytest.approx(3.0, abs=0.06)
        assert e["thickness"] == pytest.approx(-3.0, abs=0.06)
        assert e["width"] == pytest.approx(-1.0, abs=0.06)
        assert e["load_fy"] == pytest.approx(1.0, abs=0.06)

    def test_eleman_boyutu_fizige_karismiyor(self):
        """Convergence taraması es'in deplasmanı etkilemediğini gösterdi;
        model de bunu bağımsız olarak bulmalı."""
        X, y = self._beam()
        b = train_scalar_rf(X, y)
        assert abs(b["exponents"]["max_displacement"]["element_size"]) < 0.10

    def test_mape_gurultu_tabaninda(self):
        """Asıl regresyon: ham RF bu veride MAPE %42 veriyordu."""
        X, y = self._beam()
        b = train_scalar_rf(X, y)
        for key in ("max_displacement", "max_von_mises"):
            assert b["metrics"]["test"][key]["mape"] < 0.05

    def test_negatif_yuk_loglaniyor(self):
        """load_fy hep negatif; işaret tutarlıysa log|x| alınmalı."""
        from app.ml.scalar_features import FEATURE_KEYS
        from app.ml.scalar_rf import _logmask

        X, _ = self._beam()
        mask = _logmask(X)
        assert mask[list(FEATURE_KEYS).index("load_fy")]

    def test_sabit_sutunlar_ustel_raporunda_yok(self):
        X, y = self._beam()
        b = train_scalar_rf(X, y)
        e = b["exponents"]["max_displacement"]
        assert "poisson_ratio" not in e
        assert "youngs_modulus" not in e


class TestEksikHedef:
    """Bir skaler bazı run'larda yoksa o run tamamen düşmemeli."""

    def test_nan_hedef_digerlerini_dusurmez(self):
        from app.ml.scalar_features import TARGET_KEYS

        X, y = _data(60)
        idx = list(TARGET_KEYS).index("max_von_mises_away")
        # Run'ların yarısında maskeli gerilme yok
        y[::2, idx] = np.nan
        b = train_scalar_rf(X, y)
        # Diğer iki hedef tam veriyle eğitilmiş olmalı
        assert b["metrics"]["test"]["max_displacement"] is not None
        assert b["metrics"]["test"]["max_von_mises"] is not None
        assert b["n_train"] + b["n_test"] == 60

    def test_tamamen_eksik_hedef_none_doner(self):
        from app.ml.scalar_features import TARGET_KEYS

        X, y = _data(60)
        idx = list(TARGET_KEYS).index("max_von_mises_away")
        y[:, idx] = np.nan
        b = train_scalar_rf(X, y)
        assert b["models"]["max_von_mises_away"] is None
        assert b["exponents"]["max_von_mises_away"] is None
        # Diğerleri etkilenmemeli
        assert b["models"]["max_displacement"] is not None


class TestHedefSutunSayisi:
    """Hedef eklendiğinde eski çağıranlar kırılmamalı.

    REGRESYON: `max_von_mises_away` üçüncü hedef olarak eklenince,
    2 sütunlu y gönderen mevcut çağıranlar `IndexError` ile patladı.
    """

    def test_eksik_sutun_nan_ile_tamamlanir(self):
        X, y = _data(40)
        b = train_scalar_rf(X, y[:, :2], seed=1)
        assert b["metrics"]["test"]["max_displacement"] is not None
        assert b["models"]["max_von_mises_away"] is None

    def test_eksik_hedef_tahmininde_none(self):
        from app.ml.scalar_rf import predict_scalar

        X, y = _data(40)
        b = train_scalar_rf(X, y[:, :2], seed=1)
        preds = predict_scalar(b, X[0])["predictions"]
        assert preds["max_displacement"] is not None
        assert preds["max_von_mises_away"] is None

    def test_fazla_sutun_hata_verir(self):
        """Sessizce kırpmak veri kaybını gizler — açıkça reddedilmeli."""
        X, _ = _data(40)
        with pytest.raises(ValueError, match="hedef tanımlı"):
            train_scalar_rf(X, np.zeros((40, 9)))

    def test_tek_boyutlu_y_reddedilir(self):
        X, _ = _data(40)
        with pytest.raises(ValueError, match="2 boyutlu"):
            train_scalar_rf(X, np.zeros(40))
