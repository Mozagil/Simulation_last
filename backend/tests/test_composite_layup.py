"""Faz 3.3 — CLT ABD (saf numpy, DB yok)."""

import numpy as np
import pytest

from app.composite.layup import Ply, abd_matrix, reduced_stiffness

# Seed T300/epoxy (Pa); mill test değil — yalnız sayısal tutarlılık.
_T300 = dict(e1=135e9, e2=10e9, g12=5.2e9, nu12=0.30)


def _ply(angle: float, t: float = 0.125) -> Ply:
    return Ply(**_T300, thickness_mm=t, angle_deg=angle)


def test_reduced_stiffness_matches_plane_stress_formula():
    q = reduced_stiffness(135e9, 10e9, 5.2e9, 0.30)
    nu21 = 0.30 * 10e9 / 135e9
    denom = 1.0 - 0.30 * nu21
    assert q[0, 0] == pytest.approx(135e9 / denom)
    assert q[1, 1] == pytest.approx(10e9 / denom)
    assert q[0, 1] == pytest.approx(0.30 * 10e9 / denom)
    assert q[2, 2] == pytest.approx(5.2e9)
    assert q[0, 2] == pytest.approx(0.0)
    assert q[1, 2] == pytest.approx(0.0)


def test_isotropic_ply_a_and_d_plate_formula():
    e, nu = 210e9, 0.30
    g = e / (2.0 * (1.0 + nu))
    t = 2.0
    abd = abd_matrix([Ply(e1=e, e2=e, g12=g, nu12=nu, thickness_mm=t, angle_deg=0.0)])
    q11_mpa = (e / (1.0 - nu * nu)) / 1e6
    assert abd.A[0, 0] == pytest.approx(q11_mpa * t)
    assert abd.D[0, 0] == pytest.approx(q11_mpa * t**3 / 12.0)
    assert abd.B == pytest.approx(np.zeros((3, 3)), abs=1e-9)


def test_symmetric_0_90_0_b_zero_and_a_from_q():
    t = 0.125
    abd = abd_matrix([_ply(0.0, t), _ply(90.0, t), _ply(0.0, t)])
    q = reduced_stiffness(**_T300) / 1e6
    q11, q22, q12, q66 = q[0, 0], q[1, 1], q[0, 1], q[2, 2]
    assert abd.B == pytest.approx(np.zeros((3, 3)), abs=1e-9)
    assert abd.A[0, 2] == pytest.approx(0.0, abs=1e-9)
    assert abd.A[1, 2] == pytest.approx(0.0, abs=1e-9)
    assert abd.A[0, 0] == pytest.approx((2.0 * q11 + q22) * t)
    assert abd.A[1, 1] == pytest.approx((2.0 * q22 + q11) * t)
    assert abd.A[0, 1] == pytest.approx(3.0 * q12 * t)
    assert abd.A[2, 2] == pytest.approx(3.0 * q66 * t)
    assert abd.A[0, 0] > abd.A[1, 1]
    d11 = (1.0 / 3.0) * (6.5 * q11 + 0.25 * q22) * t**3
    assert abd.D[0, 0] == pytest.approx(d11)


def test_pm45_symmetric_balanced():
    """[±45]s = [45/−45/−45/45], alt→üst."""
    t = 0.125
    abd = abd_matrix([_ply(45.0, t), _ply(-45.0, t), _ply(-45.0, t), _ply(45.0, t)])
    assert abd.B == pytest.approx(np.zeros((3, 3)), abs=1e-8)
    assert abd.A[0, 0] == pytest.approx(abd.A[1, 1], rel=1e-9)
    assert abd.A[0, 2] == pytest.approx(0.0, abs=1e-8)
    assert abd.A[1, 2] == pytest.approx(0.0, abs=1e-8)
    # Dengeli simetrik: A16=0 ama eğilme-burulma D16 sıfır değil.
    assert abs(abd.D[0, 2]) > 1e-6


def test_empty_and_bad_thickness_raise():
    with pytest.raises(ValueError, match="En az bir"):
        abd_matrix([])
    with pytest.raises(ValueError, match="pozitif"):
        abd_matrix([_ply(0.0, 0.0)])
