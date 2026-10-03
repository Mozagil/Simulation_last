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
