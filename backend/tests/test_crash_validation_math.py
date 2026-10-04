"""1.17f — validasyon hesap fonksiyonları (elle hesaplanmış değerlerle)."""

from __future__ import annotations

import math

import pytest

from app.postprocess.crash_validation import (
    contact_duration_ms,
    contact_window,
    elastic_impact_force_kn,
    plateau_kn,
    sled_crush,
    tube_mean_crush_force_kn,
    wave_speeds,
)


def test_wave_and_elastic_force():
    c = wave_speeds(210e9, 7850.0, 0.3)
    assert c["c0"] == pytest.approx(5172.2, rel=1e-4)
    assert c["cp"] == pytest.approx(c["c0"] / math.sqrt(1 - 0.09), rel=1e-12)
    # kutu: çevre 2(47+37) × t 3 = 504 mm²; 10 m/s
    assert elastic_impact_force_kn(7850.0, c["c0"], 10.0, 504.0) == pytest.approx(204.6, rel=1e-3)
    assert contact_duration_ms(300.0, c["c0"]) == pytest.approx(0.1160, rel=1e-3)


def test_tube_mean_crush_force_hand_values():
    # σ0 235 MPa, t 3, C = (47+37)/2 = 42: 235·3^(5/3)·42^(1/3) = 5097.6 N
    pm = tube_mean_crush_force_kn(235.0, 3.0, 42.0)
    assert pm["wierzbicki_abramowicz_1983"] == pytest.approx(9.56 * 5.0976, rel=1e-3)
    assert pm["abramowicz_jones_1984"] == pytest.approx(13.06 * 5.0976, rel=1e-3)


def test_window_and_plateau():
    t = [0.0, 0.1, 0.2, 0.3, 0.4]
    f = [0.0, 10.0, 10.0, 10.0, 0.0]
    assert contact_window(t, f) == (0.1, 0.3)
    assert plateau_kn(t, f, 0.1, 0.3) == pytest.approx(10.0)


def test_sled_crush_constant_force():
    # M = 10 kg, v0 = 10 m/s, sabit 50 kN → durma 2 ms, δ = v0²·M/(2F) = 10 mm
    t = [i * 0.01 for i in range(301)]
    imp = [min(50.0 * x, 100.0) for x in t]  # kN·ms = N·s; 100 N·s = M·v0
    out = sled_crush(t, imp, 10.0, 10.0)
    assert out["t_stop_ms"] == pytest.approx(2.0, abs=0.011)
    assert out["crush_mm"] == pytest.approx(10.0, rel=1e-3)


def test_validation_endpoint(tmp_path, monkeypatch):
    import json

    from fastapi.testclient import TestClient

    from app.api import crash_scenario
    from app.main import app

    client = TestClient(app)
    monkeypatch.setattr(crash_scenario, "VALIDATION_REPORT", tmp_path / "yok.json")
    assert client.get("/crash/validation").status_code == 404
    rep = tmp_path / "crash_validation.json"
    rep.write_text(json.dumps({"generated_at": "x", "cases": []}), encoding="utf-8")
    monkeypatch.setattr(crash_scenario, "VALIDATION_REPORT", rep)
    assert client.get("/crash/validation").json() == {"generated_at": "x", "cases": []}


def test_clamped_plate_quasi_static_hand_values():
    # 1.18e — S235 a 300 t 5: D = 210000·125/(12·0.91) = 2.4038e6 N·mm; k = D/(0.0056·9e4) = 4769 N/mm
    from app.postprocess.crash_validation import (
        clamped_square_plate_stiffness_n_per_mm,
        plate_rigidity_nmm,
        quasi_static_impact,
    )

    assert plate_rigidity_nmm(210e9, 0.3, 5.0) == pytest.approx(2.4038e6, rel=1e-4)
    k = clamped_square_plate_stiffness_n_per_mm(210e9, 0.3, 5.0, 300.0)
    assert k == pytest.approx(4769.4, rel=1e-4)
    q = quasi_static_impact(k, 50.0, 1.0)
    # F = 1·√(4.769e6·50) = 15443 N; δ = F/k = 3.238 mm; T = π·√(50/4.769e6) = 10.17 ms
    assert q["force_max_kn"] == pytest.approx(15.443, rel=1e-3)
    assert q["deflection_max_mm"] == pytest.approx(q["force_max_kn"] * 1e3 / k, rel=1e-9)
    assert q["contact_ms"] == pytest.approx(10.17, rel=1e-3)


def test_recht_ipson_fit_recovers_exact_curve():
    from app.postprocess.crash_validation import recht_ipson_fit

    v0 = [60.0, 100.0, 150.0, 200.0]
    vr = [0.9 * math.sqrt(v * v - 40.0**2) for v in v0]
    r = recht_ipson_fit(v0, vr)
    assert r["a"] == pytest.approx(0.9) and r["v_bl_m_s"] == pytest.approx(40.0) and r["r2"] == pytest.approx(1.0)
    with pytest.raises(ValueError):
        recht_ipson_fit([1.0], [1.0])


def test_taylor_reference_and_final_shape():
    # K1 — S235, 100 m/s: ρv²/(2σ) = 7850·1e4/(4.7e8) = 0.16702 → exp = 0.84618
    from app.postprocess.crash_validation import taylor_final_shape, wilkins_guinan_ratio

    assert wilkins_guinan_ratio(7850.0, 100.0, 235e6) == pytest.approx(0.846182, rel=1e-5)
    assert wilkins_guinan_ratio(7850.0, 100.0, 235e6, h_over_l0=1.0) == pytest.approx(1.0)
    # iki yüzlü küçük çubuk: x 0…40, uçta yarıçap 6; 9. düğüm yüzsüz (duvar noktası) yok sayılır
    pos = [0, 6, 0, 0, -6, 0, 0, 0, 6, 40, 5, 0, 40, -5, 0, 40, 0, 5, 0, 0, 0, 40, 0, 0, 0, 99, 0]
    shape = taylor_final_shape([[0, 1, 2], [3, 4, 5], [6, 7, 1]], pos)
    assert shape == {"length_mm": 40.0, "front_diameter_mm": 12.0}


def test_drop_free_fall_and_impulse():
    # K2 — 1 m: v0 = 4.42945 m/s; 1 mm boşluk → t ≈ 1/4.42945 ms (g düzeltmesi < 1e-4)
    from app.postprocess.crash_validation import drop_wall_impulse_ns, free_fall_contact_ms

    v0 = math.sqrt(2 * 9.81 * 1.0)
    t = free_fall_contact_ms(1.0, v0, 9.81)
    assert v0 * t + 0.5 * 9.81e-3 * t * t == pytest.approx(1.0, rel=1e-12)
    assert t == pytest.approx(1.0 / v0, rel=1e-3)
    assert free_fall_contact_ms(2.0, 4.0, 0.0) == pytest.approx(0.5)
    # 1.5 kg, −4.43 → +1.0 m/s, 5 ms: 1.5·5.43 + 1.5·9.81·0.005
    assert drop_wall_impulse_ns(1.5, -4.43, 1.0, 9.81, 5.0) == pytest.approx(1.5 * 5.43 + 1.5 * 9.81 * 0.005)


def test_friedlander_impulse_closed_form():
    # K10 — ∫Ps(1−τ)e^(−bτ)dt = Ps·td·[1/b − (1−e^(−b))/b²]; sayısal integralle
    from app.solvers.crash_params import CrashPressureLoadParams

    pl = CrashPressureLoadParams(peak_mpa=2.0, duration_ms=0.2, decay=1.0)
    n = 20000
    num = sum(pl.pressure_mpa(0.2 * (i + 0.5) / n) for i in range(n)) * 0.2 / n
    assert pl.impulse_per_area_mpa_ms() == pytest.approx(num, rel=1e-6)
    assert CrashPressureLoadParams(peak_mpa=2.0, duration_ms=0.2, decay=0.0).impulse_per_area_mpa_ms() == pytest.approx(0.2)
