"""app/postprocess/fatigue.py testleri — saf birim testler, DB gerektirmez."""

import math

from app.postprocess.fatigue import compute_safety_factor, estimate_fatigue_life

# S355 benzeri: Rm=510 MPa varsayımıyla estimate_sn_from_rm(510) noktaları
SN_POINTS = [
    {"N": 1.0e3, "sigma": 0.90 * 510},  # 459 MPa
    {"N": 1.0e6, "sigma": 0.45 * 510},  # 229.5 MPa
    {"N": 1.0e7, "sigma": 0.40 * 510},  # 204 MPa
]


def test_estimate_fatigue_life_at_exact_points_matches_input():
    """Gerilme genliği tam bir S-N noktasına denk gelirse, o noktanın N'i
    dönmeli (interpolasyon hatası olmamalı)."""
    result = estimate_fatigue_life(459.0, SN_POINTS)
    assert result["cycles"] == 1.0e3


def test_estimate_fatigue_life_interpolates_between_points():
    """İki nokta arasındaki bir gerilme, log-log doğrusal interpolasyonla
    makul bir ara değer vermeli (iki komşu N değeri arasında olmalı)."""
    # 459 (N=1e3) ile 229.5 (N=1e6) arası, ortada bir gerilme:
    result = estimate_fatigue_life(300.0, SN_POINTS)
    assert result["cycles"] is not None
    assert 1.0e3 < result["cycles"] < 1.0e6
    assert result["runout"] is False


def test_estimate_fatigue_life_below_fatigue_limit_is_runout():
    """Yorulma sınırının (en düşük S-N noktası) altındaki bir gerilme,
    'runout' (pratikte sonsuz ömür) olarak işaretlenmeli."""
    result = estimate_fatigue_life(50.0, SN_POINTS)
    assert result["runout"] is True
    assert result["cycles"] == 1.0e7


def test_estimate_fatigue_life_above_max_stress_returns_shortest_life():
    """S-N eğrisinin en üstündeki (en yüksek gerilme) noktanın üzerinde bir
    gerilme verilirse, ekstrapole ETMEDEN en kısa ömür noktası dönmeli —
    güvenli tarafta kalınır (hayali bir ekstrapolasyonla yanıltıcı 'daha
    uzun ömür' verilmez)."""
    result = estimate_fatigue_life(600.0, SN_POINTS)
    assert result["cycles"] == 1.0e3


def test_estimate_fatigue_life_monotonic_decreasing_with_stress():
    """KRİTİK fiziksel tutarlılık: gerilme arttıkça ömür (cycles) kesinlikle
    AZALMALI (S-N eğrisinin temel doğası) — regresyon testinde bu
    monotonluğu doğrudan kontrol ediyoruz."""
    stresses = [100.0, 150.0, 200.0, 250.0, 300.0, 350.0, 400.0]
    lives = [estimate_fatigue_life(s, SN_POINTS)["cycles"] for s in stresses]
    for i in range(len(lives) - 1):
        assert lives[i] >= lives[i + 1], f"{stresses[i]} MPa'de ömür, {stresses[i+1]} MPa'dekinden az olmamalı"


def test_estimate_fatigue_life_handles_empty_or_insufficient_points():
    assert estimate_fatigue_life(300.0, [])["cycles"] is None
    assert estimate_fatigue_life(300.0, [{"N": 1e6, "sigma": 200}])["cycles"] is None


def test_estimate_fatigue_life_rejects_zero_or_negative_stress():
    assert estimate_fatigue_life(0.0, SN_POINTS)["cycles"] is None
    assert estimate_fatigue_life(-10.0, SN_POINTS)["cycles"] is None


def test_compute_safety_factor_basic():
    # Akma 355 MPa, gerçek gerilme 598 MPa -> SF = 355/598 ≈ 0.59 (senin
    # ekran görüntündeki gerçek örnekle birebir eşleşir).
    sf = compute_safety_factor(598.0, 355.0)
    assert math.isclose(sf, 355.0 / 598.0)


def test_compute_safety_factor_handles_missing_or_invalid_input():
    assert compute_safety_factor(100.0, None) is None
    assert compute_safety_factor(100.0, 0) is None
    assert compute_safety_factor(0, 355.0) is None
