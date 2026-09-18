"""Convergence saf mantık testleri — DB/ccx gerekmez."""

from __future__ import annotations

import pytest

from app.doe.convergence import (
    ConvergenceSpec,
    assess_convergence,
    element_size_ladder,
    recommended_ratio,
)


def _spec(**kw) -> ConvergenceSpec:
    base = dict(
        template_id="cantilever_beam",
        geometry_params={"length": 500.0, "thickness": 10.0, "width": 50.0},
        material_id=1,
        scenario_name="uc_yuku",
        bcs=[{"type": "fixed", "region": "ankastre_uc"}],
        characteristic_length=10.0,
    )
    base.update(kw)
    return ConvergenceSpec(**base)


class TestLadder:
    def test_kabadan_inceye_siralanir(self):
        sizes = element_size_ladder(_spec(ratios=[0.5, 1.5, 1.0]))
        assert sizes == [15.0, 10.0, 5.0]

    def test_karakteristik_uzunlukla_carpilir(self):
        sizes = element_size_ladder(
            _spec(ratios=[1.0, 0.5], characteristic_length=8.0)
        )
        assert sizes == [8.0, 4.0]

    def test_min_altindakiler_elenir(self):
        # 10mm karakteristik, min 4mm → 0.3 (3mm) elenmeli
        sizes = element_size_ladder(
            _spec(ratios=[1.0, 0.5, 0.3], min_element_size=4.0)
        )
        assert sizes == [10.0, 5.0]

    def test_tek_basamak_kalirsa_hata(self):
        with pytest.raises(ValueError, match="en az 2 basamak"):
            element_size_ladder(_spec(ratios=[1.0, 0.3], min_element_size=9.0))

    def test_tekrarli_oran_reddedilir(self):
        with pytest.raises(ValueError, match="tekrarsız"):
            _spec(ratios=[1.0, 1.0, 0.5])


class TestAssess:
    def test_yakinsayan_seri(self):
        steps = [
            {"element_size": 15.0, "max_displacement": 20.0, "max_von_mises": 250.0},
            {"element_size": 10.0, "max_displacement": 22.0, "max_von_mises": 280.0},
            {"element_size": 5.0, "max_displacement": 23.5, "max_von_mises": 295.0},
            # %0.85 değişim → tol %2 altında
            {"element_size": 4.0, "max_displacement": 23.7, "max_von_mises": 300.0},
        ]
        out = assess_convergence(steps)
        # 15 ve 10mm en inceden >%2 sapıyor; 5mm'den itibaren banda giriyor
        assert out["disp_converged_at"] == 5.0
        assert out["finest"]["element_size"] == 4.0

    def test_gerilme_yakinsamazsa_none_ve_not(self):
        # σ her adımda ~%20 artıyor: tekillik davranışı, hiç oturmuyor
        steps = [
            {"element_size": 10.0, "max_displacement": 23.0, "max_von_mises": 200.0},
            {"element_size": 5.0, "max_displacement": 23.2, "max_von_mises": 240.0},
            {"element_size": 3.0, "max_displacement": 23.3, "max_von_mises": 290.0},
        ]
        out = assess_convergence(steps)
        assert out["disp_converged_at"] == 10.0
        assert out["stress_converged_at"] is None
        assert any("tekil" in n for n in out["notes"])

    def test_cozulemeyen_basamak_atlanir_ama_tabloda_kalir(self):
        steps = [
            {"element_size": 10.0, "max_displacement": 23.0, "max_von_mises": 300.0},
            {"element_size": 5.0, "max_displacement": None, "max_von_mises": None},
            {"element_size": 4.0, "max_displacement": 23.1, "max_von_mises": 305.0},
        ]
        out = assess_convergence(steps)
        assert len(out["table"]) == 3
        # çözülemeyen basamak hesaba girmez, 10 ve 4 karşılaştırılır
        assert out["disp_converged_at"] == 10.0
        assert any("çözülemedi" in n for n in out["notes"])

    def test_bagil_degisim_hesaplanir(self):
        steps = [
            {"element_size": 10.0, "max_displacement": 20.0, "max_von_mises": 100.0},
            {"element_size": 5.0, "max_displacement": 25.0, "max_von_mises": 110.0},
        ]
        out = assess_convergence(steps)
        assert out["table"][0]["rel_change_disp"] is None  # ilk satır
        assert out["table"][1]["rel_change_disp"] == pytest.approx(0.25)
        assert out["table"][1]["rel_change_stress"] == pytest.approx(0.10)

    def test_hicbiri_cozulmezse_patlamaz(self):
        steps = [
            {"element_size": 10.0, "max_displacement": None, "max_von_mises": None},
        ]
        out = assess_convergence(steps)
        assert out["disp_converged_at"] is None
        assert out["finest"] is None


class TestGercekTarama:
    """study_id=8 gerçek ölçümü — S235, L500/T10/W50, uçtan 500 N.

    Kiriş teorisi: u = 23.81 mm, σ = 300 MPa.
    Bu veri kriterin regresyon koruması: ilk sürüm σ için yanlışlıkla
    "10 mm'de yakınsadı" diyordu.
    """

    STEPS = [
        {"element_size": 15.0, "node_count": 2397, "max_displacement": 23.991, "max_von_mises": 345.9},
        {"element_size": 12.0, "node_count": 3584, "max_displacement": 23.970, "max_von_mises": 315.5},
        {"element_size": 10.0, "node_count": 4788, "max_displacement": 24.000, "max_von_mises": 330.0},
        {"element_size": 8.0, "node_count": 7205, "max_displacement": 23.919, "max_von_mises": 330.7},
        {"element_size": 6.0, "node_count": 13224, "max_displacement": 23.957, "max_von_mises": 339.8},
        {"element_size": 5.0, "node_count": 21143, "max_displacement": 23.964, "max_von_mises": 337.0},
        {"element_size": 4.0, "node_count": 34493, "max_displacement": 23.751, "max_von_mises": 321.3},
        {"element_size": 3.0, "node_count": 79934, "max_displacement": 23.717, "max_von_mises": 328.5},
    ]

    def test_deplasman_en_kaba_meshte_bile_yakinsamis(self):
        out = assess_convergence(self.STEPS)
        # En inceye göre sapma her basamakta %1.2 → en kabadan itibaren tamam
        assert out["disp_converged_at"] == 15.0
        assert out["disp_noise_floor"] < 0.02

    def test_gerilme_gurultu_tabani_toleransin_ustunde(self):
        out = assess_convergence(self.STEPS)
        # Kuyruk bandı %5.58 > tol %5 → yakınsama iddiası anlamsız
        assert out["stress_noise_floor"] > out["tol_stress"]
        assert any("gürültü tabanı" in n for n in out["notes"])

    def test_teoriye_yakinlik(self):
        out = assess_convergence(self.STEPS)
        u_fea = out["finest"]["max_displacement"]
        assert abs(u_fea - 23.81) / 23.81 < 0.01  # %1'den iyi

    def test_max_sigma_teoriden_yuksek(self):
        # Ankastre yüzeydeki yerel etki: FEA ~331 vs teori 300 → ~%10
        sigmas = [s["max_von_mises"] for s in self.STEPS]
        mean = sum(sigmas) / len(sigmas)
        assert mean > 300 * 1.05


class TestSurdurulebilirKriter:
    def test_sonradan_bozulursa_iddia_duser(self):
        # 10 ve 8 birbirine yakın ama en ince (6) ikisinden de uzak →
        # onlardan "yakınsadı" denemez
        steps = [
            {"element_size": 10.0, "max_displacement": 20.0, "max_von_mises": 100.0},
            {"element_size": 8.0, "max_displacement": 20.2, "max_von_mises": 101.0},
            {"element_size": 6.0, "max_displacement": 22.0, "max_von_mises": 130.0},
        ]
        out = assess_convergence(steps)
        # Yalnız en ince çözüm banda giriyor → tek nokta, yakınsama sayılmaz
        assert out["disp_converged_at"] is None

    def test_gercekten_oturan_seri(self):
        steps = [
            {"element_size": 10.0, "max_displacement": 20.0, "max_von_mises": 100.0},
            {"element_size": 8.0, "max_displacement": 20.2, "max_von_mises": 101.0},
            {"element_size": 6.0, "max_displacement": 20.3, "max_von_mises": 101.5},
        ]
        out = assess_convergence(steps)
        # 10mm'den itibaren hepsi %2 bandında → en kaba mesh yeterli
        assert out["disp_converged_at"] == 10.0


class TestRecommendedRatio:
    def test_orana_cevirir(self):
        out = {"recommended_element_size": 4.0}
        assert recommended_ratio(out, 10.0) == 0.4

    def test_yakinsamadiysa_none(self):
        assert recommended_ratio({"recommended_element_size": None}, 10.0) is None
