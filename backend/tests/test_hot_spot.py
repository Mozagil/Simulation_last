"""Hot-spot gerilmesi: tekilliğe doğrusal ekstrapolasyon (TODO 6).

NEDEN: `max_von_mises` tekil noktadan okunuyor, mesh'ten mesh'e ±%5.6
oynuyor. `max_von_mises_away` tekillikten KAÇIYOR — gürültüyü kesiyor ama
sistematik olarak düşük kalıyor. Hot-spot yöntemi iki sağlıklı mesafeden
okuyup tekilliğe UZATIR.

Ankastre kirişte bu yöntem TEORİDE TAM sonuç verir: uç yüklü kirişte
σ(x) = F(L−x)c/I, yani mesafede DOĞRUSAL. Doğrusal bir alana doğrusal
uzatma hatasızdır — testlerin dayanağı bu.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.dataset.training_data import NODE_INPUT_CHANNELS, NODE_OUTPUT_CHANNELS
from app.postprocess.stress_probe import DEFAULT_HOTSPOT_BINS, hot_spot_stress

IX = {n: i for i, n in enumerate(NODE_INPUT_CHANNELS)}
OX = {n: i for i, n in enumerate(NODE_OUTPUT_CHANNELS)}

T = 10.0      # kalınlık (mm)
L = 500.0     # uzunluk
SIGMA_KOK = 300.0   # ankastre kökteki teorik gerilme
EGIM = SIGMA_KOK / L  # σ(x) = 300 − 0.6x  → uçta sıfır


def _kiris(n: int = 400, gurultu: float = 0.0, seed: int = 0):
    """Uç yüklü ankastre kiriş: gerilme mesafede doğrusal."""
    rng = np.random.default_rng(seed)
    x = np.linspace(0.0, L, n)
    X = np.zeros((n, len(NODE_INPUT_CHANNELS)), dtype=np.float64)
    X[:, IX["x"]] = x
    X[x <= 1e-9, IX["fixed_ux"]] = 1.0   # kök ankastre
    Y = np.zeros((n, len(NODE_OUTPUT_CHANNELS)), dtype=np.float64)
    sigma = SIGMA_KOK - EGIM * x
    if gurultu:
        sigma = sigma + rng.normal(0.0, gurultu, n)
    Y[:, OX["von_mises_mpa"]] = sigma
    return X, Y


# --- doğrusal alanda tam sonuç -------------------------------------------------


def test_dogrusal_alanda_kok_gerilmesini_geri_verir():
    X, Y = _kiris()
    out = hot_spot_stress(X, Y, T)
    assert out["hot_spot_mpa"] == pytest.approx(SIGMA_KOK, rel=1e-9)


def test_kacinma_degeri_sistematik_dusuk_kalir():
    """Asıl gerekçe: 1×T uzakta okumak kökteki değeri %2 küçük veriyor."""
    X, Y = _kiris()
    uzak = float(Y[np.isclose(X[:, IX["x"]], T, atol=0.7), OX["von_mises_mpa"]].max())
    hot = hot_spot_stress(X, Y, T)["hot_spot_mpa"]

    assert uzak < SIGMA_KOK
    assert abs(hot - SIGMA_KOK) < abs(uzak - SIGMA_KOK)


def test_mesh_yogunlugundan_bagimsiz():
    """Farklı düğüm sayıları aynı fiziksel alanı örnekliyor; sonuç
    değişmemeli — `max_von_mises`'ın mesh'e göre oynaması sorunun ta
    kendisiydi."""
    degerler = [hot_spot_stress(*_kiris(n=n), T)["hot_spot_mpa"] for n in (200, 400, 1200)]
    assert max(degerler) - min(degerler) < 1e-6


def test_nominal_degil_gercek_mesafe_kullanilir():
    """Düğümler tam 0.4t/1.0t'ye düşmez. Nominal mesafe varsayılırsa
    sistematik hata girer."""
    X = np.zeros((3, len(NODE_INPUT_CHANNELS)))
    Y = np.zeros((3, len(NODE_OUTPUT_CHANNELS)))
    X[:, IX["x"]] = [0.0, 0.45 * T, 0.95 * T]   # dilim ortalarına düşmeyen düğümler
    X[0, IX["fixed_ux"]] = 1.0
    Y[:, OX["von_mises_mpa"]] = SIGMA_KOK - EGIM * X[:, IX["x"]]

    out = hot_spot_stress(X, Y, T, n_bins=2)

    assert out["hot_spot_mpa"] == pytest.approx(SIGMA_KOK, rel=1e-9)
    assert [p["distance_mm"] for p in out["points"]] == pytest.approx([0.45 * T, 0.95 * T])


def test_cok_nokta_iki_noktadan_az_gurultulu():
    """ÖLÇÜLDÜ: iki noktalı uzatma (σ_hs = 1.67σ₁ − 0.67σ₂) tek nokta
    gürültüsünü ~1.8 katına çıkarır. Pencereyi çok noktadan örneklemek
    aynı fiziği kullanır ama gürültüyü ortalar."""
    iki, cok = [], []
    for seed in range(40):
        X, Y = _kiris(gurultu=5.0, seed=seed)
        iki.append(hot_spot_stress(X, Y, T, n_bins=2)["hot_spot_mpa"] - SIGMA_KOK)
        cok.append(hot_spot_stress(X, Y, T)["hot_spot_mpa"] - SIGMA_KOK)

    rms_iki = float(np.sqrt(np.mean(np.square(iki))))
    rms_cok = float(np.sqrt(np.mean(np.square(cok))))
    assert rms_cok < rms_iki


def test_iki_nokta_klasik_formulu_verir():
    """n_bins=2 klasik IIW formülüdür; doğrusal alanda yine tam sonuç."""
    X, Y = _kiris()
    assert hot_spot_stress(X, Y, T, n_bins=2)["hot_spot_mpa"] == pytest.approx(
        SIGMA_KOK, rel=1e-9
    )


def test_tek_nokta_reddedilir():
    X, Y = _kiris()
    assert hot_spot_stress(X, Y, T, n_bins=1)["hot_spot_mpa"] is None


# --- teşhis ve sınır durumları --------------------------------------------------


def test_okuma_noktalari_raporlanir():
    out = hot_spot_stress(*_kiris(n=2000), T)
    assert out["n_bins_used"] == DEFAULT_HOTSPOT_BINS
    assert out["window_mm"] == pytest.approx((0.4 * T, 1.0 * T))
    assert all(p["n_nodes"] > 0 for p in out["points"])


def test_seyrek_meshte_bos_dilim_atlanir():
    """Düğüm aralığı dilim genişliğinden büyükse bazı dilimler boş kalır;
    uydurma nokta eklemek yerine atlanır."""
    out = hot_spot_stress(*_kiris(n=400), T)   # 1.25 mm aralık, 1 mm dilim
    assert 2 <= out["n_bins_used"] < DEFAULT_HOTSPOT_BINS
    assert out["hot_spot_mpa"] == pytest.approx(SIGMA_KOK, rel=1e-9)


def test_dilimler_ayni_dugumu_iki_kez_saymaz():
    """İlk tasarımda bantlar örtüşüyordu; aynı düğüm birkaç okuma noktası
    olarak sayılıp regresyonu yanlı hâle getiriyordu."""
    out = hot_spot_stress(*_kiris(n=2000), T)
    mesafeler = [p["distance_mm"] for p in out["points"]]
    assert len(set(mesafeler)) == len(mesafeler)
    for p, q in zip(out["points"], out["points"][1:]):
        assert p["distance_mm"] < q["distance_mm"]


def test_dogrusal_alanda_uyum_tam():
    """`fit_r2` yöntemin varsayımını denetler: pencere içinde alan
    doğrusal değilse sayı döner ama güvenilmez."""
    out = hot_spot_stress(*_kiris(), T)
    assert out["fit_r2"] == pytest.approx(1.0, abs=1e-12)
    assert out["slope_mpa_per_mm"] == pytest.approx(-EGIM, rel=1e-9)


def test_kaba_meshte_bant_bos_kalirsa_uyarir():
    """Sessizce yanlış sayı döndürmek yerine neden ölçülemediğini söyle."""
    X = np.zeros((2, len(NODE_INPUT_CHANNELS)))
    Y = np.zeros((2, len(NODE_OUTPUT_CHANNELS)))
    X[:, IX["x"]] = [0.0, 300.0]
    X[0, IX["fixed_ux"]] = 1.0

    out = hot_spot_stress(X, Y, T)

    assert out["hot_spot_mpa"] is None
    assert "dilim doldu" in out["warning"]


def test_kisit_yoksa_kisittan_olculemez():
    X, Y = _kiris()
    X[:, IX["fixed_ux"]] = 0.0
    out = hot_spot_stress(X, Y, T, origin="constraint")
    assert out["hot_spot_mpa"] is None
    assert "Kısıtlı düğüm yok" in out["warning"]


def test_kisit_yoksa_tepe_yine_calisir():
    """Varsayılan mesafe kaynağı tepe düğümdür; kısıt gerekmez."""
    X, Y = _kiris()
    X[:, IX["fixed_ux"]] = 0.0
    assert hot_spot_stress(X, Y, T)["hot_spot_mpa"] == pytest.approx(SIGMA_KOK, rel=1e-9)


def test_bilinmeyen_origin_reddedilir():
    X, Y = _kiris()
    assert hot_spot_stress(X, Y, T, origin="yok")["hot_spot_mpa"] is None


def test_gecersiz_kalinlik():
    X, Y = _kiris()
    for t in (0.0, -5.0, float("nan")):
        assert hot_spot_stress(X, Y, t)["hot_spot_mpa"] is None


def test_kisittan_uzaklastikca_artan_alan_isaretlenir():
    """Yığılma kısıtta değilse kısıttan uzatma tepe değeri VERMEZ."""
    X, Y = _kiris()
    Y[:, OX["von_mises_mpa"]] = 100.0 + EGIM * X[:, IX["x"]]
    out = hot_spot_stress(X, Y, T, origin="constraint")
    assert out["increasing_away"] is True


def test_yigilma_kisitta_degilse_tepeden_olculur():
    """ÖLÇÜLDÜ: delikli plakada yığılma delikte, kısıt uzakta. Mesafeyi
    kısıttan ölçmek anlamsız bir yöne uzatıyor (gerçek koşularda
    fit_r2 0.01–0.05'e düşüyordu)."""
    n = 600
    x = np.linspace(0.0, L, n)
    X = np.zeros((n, len(NODE_INPUT_CHANNELS)))
    X[:, IX["x"]] = x
    X[x <= 1e-9, IX["fixed_ux"]] = 1.0          # kısıt solda
    delik = L / 2                                # yığılma ortada
    Y = np.zeros((n, len(NODE_OUTPUT_CHANNELS)))
    Y[:, OX["von_mises_mpa"]] = SIGMA_KOK - EGIM * np.abs(x - delik)

    tepeden = hot_spot_stress(X, Y, T)
    kisittan = hot_spot_stress(X, Y, T, origin="constraint")

    # Tepe düğüm tekilliğin tam üstüne düşmez (yarım eleman kayık kalır),
    # o yüzden %1 bandı: yöntemin kendi çözünürlük sınırı bu.
    assert tepeden["hot_spot_mpa"] == pytest.approx(SIGMA_KOK, rel=0.01)
    assert tepeden["fit_r2"] > 0.99
    # Kısıttan bakınca gerilme UZAKLAŞTIKÇA artıyor: yanlış yöne uzatma
    assert kisittan["increasing_away"] is True
    assert kisittan["hot_spot_mpa"] < tepeden["hot_spot_mpa"]


def test_ham_tepe_de_raporlanir():
    """`scalars` hem tepe hem hot-spot taşıyacak — ikisi bir arada gelsin."""
    X, Y = _kiris()
    out = hot_spot_stress(X, Y, T)
    assert out["max_von_mises_all"] == pytest.approx(SIGMA_KOK)


# --- tepe merkezli ölçüt (TODO 6, seçenek b) -----------------------------------


def test_tepe_merkezli_olcut_kisit_gerektirmez():
    """Asıl gerekçe: delikli plakada yığılma delikte, kısıt uzakta —
    kısıt maskesi orada hiçbir şey düzeltmiyor (ölçüldü: %11.4/%11.4)."""
    from app.postprocess.stress_probe import stress_near_peak

    n = 600
    x = np.linspace(0.0, L, n)
    X = np.zeros((n, len(NODE_INPUT_CHANNELS)))
    X[:, IX["x"]] = x
    delik = L / 2
    Y = np.zeros((n, len(NODE_OUTPUT_CHANNELS)))
    Y[:, OX["von_mises_mpa"]] = SIGMA_KOK - EGIM * np.abs(x - delik)

    out = stress_near_peak(X, Y, T)

    assert out["max_von_mises_near_peak"] is not None
    assert out["peak_xyz"][0] == pytest.approx(delik, abs=1.0)
    # Kabuk 5 ± 2.5 mm; maksimum İÇ KENARDAN gelir: 300 − 0.6×2.5 = 298.5
    assert out["max_von_mises_near_peak"] == pytest.approx(298.5, abs=1.0)
    assert out["max_von_mises_near_peak"] < out["max_von_mises_all"]


def test_tepe_merkezli_olcut_kaba_meshte_uyarir():
    from app.postprocess.stress_probe import stress_near_peak

    X = np.zeros((2, len(NODE_INPUT_CHANNELS)))
    Y = np.zeros((2, len(NODE_OUTPUT_CHANNELS)))
    X[:, IX["x"]] = [0.0, 400.0]
    Y[:, OX["von_mises_mpa"]] = [300.0, 10.0]

    out = stress_near_peak(X, Y, T)

    assert out["max_von_mises_near_peak"] is None
    assert "çok kaba" in out["warning"]


def test_tepe_merkezli_gecersiz_uzunluk():
    from app.postprocess.stress_probe import stress_near_peak

    X, Y = _kiris()
    assert stress_near_peak(X, Y, 0.0)["max_von_mises_near_peak"] is None
