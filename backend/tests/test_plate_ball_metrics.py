"""1.18d — plaka–küre son hız / kütle fonksiyonları (koşu #63 ve #64 verisiyle)."""

from __future__ import annotations

import pytest

from app.postprocess.plate_ball import ball_mass_kg, residual_speed_energy, residual_velocity_impulse


def test_mass_from_initial_kinetic_energy():
    # #63: KE₀ 53.06324 J, 10 m/s → 1.0613 kg (kabuk 0.0617 + 1 kg)
    assert ball_mass_kg(53.06324, 10.0) == pytest.approx(1.0613, abs=1e-4)
    with pytest.raises(ValueError):
        ball_mass_kg(1.0, 0.0)


def test_rebound_matches_energy_check():
    # #63: impuls 15.0145 N·s → +4.15 m/s (geri sekme); enerji: (10.448 − 1.263) J → 4.16 m/s
    m = ball_mass_kg(53.06324, 10.0)
    v_imp = residual_velocity_impulse(10.0, 15.01448, m)
    v_en = residual_speed_energy(10.44769, 1.263335, m)
    assert v_imp == pytest.approx(4.147, abs=1e-2)
    assert v_en == pytest.approx(abs(v_imp), rel=0.01)


def test_pass_through_is_negative_and_energy_clipped():
    # temas impulsu momentumdan küçük → küre hâlâ −z (plakayı geçti / temas sürüyor)
    assert residual_velocity_impulse(100.0, 30.0, 1.0) == pytest.approx(-70.0)
    assert residual_speed_energy(1.0, 2.0, 1.0) == 0.0
