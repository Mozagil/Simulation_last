"""1.19a — crash ML hedefleri (sentetik koşu, elle hesaplanmış değerler)."""

from __future__ import annotations

import pytest

from app.postprocess.crash_targets import TARGET_KEYS, crash_targets


def _sled_job(t_end_ms: float = 0.2) -> dict:
    # m = 1 kg, v0 = 10 m/s, sabit F = 100 kN → a = 100 mm/ms², durma 0.1 ms,
    # δ = v0² / 2a = 0.5 mm; E = ½ m v0² = 50 J. I (N·s = kN·ms) = F t ≤ m v0.
    n = int(round(t_end_ms / 0.001))
    time = [k * 0.001 for k in range(n + 1)]
    force = [100.0 if t <= 0.1 + 1e-12 else 0.0 for t in time]
    impulse = [min(100.0 * t, 10.0) for t in time]
    return {
        "use_rigid_wall": True,
        "barrier": {"speed_m_s": 10.0},
        "scalars": {"rwall_force_max": 100.0, "internal_energy_final": 50.0, "mass_model": 1.0},
        "curves": {"time": time, "rwall_force": force, "rwall_impulse": impulse},
    }


def test_sled_targets():
    t = crash_targets(_sled_job())
    assert set(t) == set(TARGET_KEYS)
    assert t["peak_force_kn"] == pytest.approx(100.0)
    assert t["mean_force_kn"] == pytest.approx(100.0, rel=1e-6)
    assert t["energy_absorbed_j"] == pytest.approx(50.0)
    assert t["crush_mm"] == pytest.approx(0.5, rel=1e-3)
    # E = F_ort · δ tutarlılığı (sabit kuvvet)
    assert t["mean_force_kn"] * t["crush_mm"] == pytest.approx(t["energy_absorbed_j"], rel=1e-3)


def test_crush_empty_when_run_ends_before_stop():
    t = crash_targets(_sled_job(t_end_ms=0.05))
    assert t["crush_mm"] is None
    assert t["peak_force_kn"] == pytest.approx(100.0)


def test_no_rigid_wall_or_curves_gives_none():
    job = _sled_job()
    job["use_rigid_wall"] = False
    assert crash_targets(job)["crush_mm"] is None
    t = crash_targets({"scalars": {}, "curves": {}})
    assert all(v is None for v in t.values())
