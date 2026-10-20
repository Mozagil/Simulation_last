"""Faz 3.10 — V-P1 klasik laminat kabuk plaka: CLT vs CalculiX.

Referanslar (`app/composite/reference.py`) her zaman koşar; ccx koşuları
ccx yoksa atlanır (CCX_PATH → PATH → vendor, uygulamayla aynı arama).
Tablo ve yorum: `docs/COMPOSITE_VALIDATION.md`.

Kilitlenen değerler 2026-10-20 ölçümünden; bant ölçüm gürültüsü + ccx sürüm
farkı içindir, mühendislik kabul ölçütü değildir.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.composite.layup import Ply, abd_matrix
from app.composite.reference import midplane_response, navier_deflection
from app.solvers.calculix import _ccx_executable
from scripts.composite_validation_vp1 import (
    CASES,
    build_deck,
    ccx_measure,
    clt_reference,
    parse_dat_displacements,
)

requires_ccx = pytest.mark.skipif(_ccx_executable() is None, reason="ccx yok")

_CASE = {c.key: c for c in CASES}


def _iso_plate(t: float) -> list[Ply]:
    # İzotrop: G = E / 2(1+ν) → D = E t³ / 12(1−ν²)
    e, nu = 70e9, 0.3
    return [Ply(e, e, e / (2 * (1 + nu)), nu, t, 0.0)]


def test_navier_isotropic_matches_timoshenko():
    # Timoshenko & Woinowsky-Krieger Tablo 8: kare SS plaka w = 0.00406 q a⁴ / D
    a, t, q = 100.0, 1.0, 0.01
    abd = abd_matrix(_iso_plate(t))
    d = 70e3 * t**3 / (12 * (1 - 0.3**2))
    w = navier_deflection(abd, a, a, q)
    assert w == pytest.approx(0.00406 * q * a**4 / d, rel=2e-3)


def test_navier_rejects_bad_input():
    abd = abd_matrix(_iso_plate(1.0))
    with pytest.raises(ValueError):
        navier_deflection(abd, 0.0, 1.0, 1.0)
    with pytest.raises(ValueError):
        navier_deflection(abd, 1.0, 1.0, 1.0, terms=0)


def test_midplane_response_isotropic_hooke():
    abd = abd_matrix(_iso_plate(2.0))
    eps = midplane_response(abd, n=(10.0, 0.0, 0.0))["eps0"]
    assert eps[0] == pytest.approx(10.0 / (70e3 * 2.0))
    assert eps[1] == pytest.approx(-0.3 * eps[0])
    assert abs(eps[2]) < 1e-15


def test_clt_reference_off_axis_shear_sign():
    # [30]₄, +Nx: γxy < 0 (Ā16⁻¹ işareti) — ccx karşılaştırmasının dayanağı.
    ref = clt_reference(_CASE["b"])
    assert ref["gamma_xy"] < 0
    assert abs(ref["gamma_xy"]) > abs(ref["eps_y"])


def test_deck_uses_named_orientations_and_balanced_load():
    deck, probes = build_deck(_CASE["b"])
    assert "*SHELL SECTION, ELSET=PLATE, COMPOSITE" in deck
    assert "3, 30\n" in deck
    assert ", T300_epoxy, OR_0_0" in deck
    # Kenar düğüm yüklerinin toplamı Nx · b
    cl = deck.split("*CLOAD\n")[1].split("*NODE PRINT")[0]
    total = sum(float(line.split(",")[2]) for line in cl.strip().splitlines())
    assert total == pytest.approx(10.0 * 50.0)
    assert set(probes) == {"o", "ax", "ay"}


def test_parse_dat_displacements():
    text = (
        "\n displacements (vx,vy,vz) for set PROBE and time  0.1000000E+01\n\n"
        "         1  1.000000E-03 -2.000000E-04  0.000000E+00\n"
        "        42  3.000000E-03  4.000000E-04 -1.500000E-01\n"
    )
    u = parse_dat_displacements(text)
    assert u[42] == (3e-3, 4e-4, -0.15)
    assert len(u) == 2


@requires_ccx
@pytest.mark.parametrize(
    "key, quantity, rel",
    [
        ("a", "eps_x", 0.01),
        ("a", "eps_y", 0.06),  # ölçülen −%3.8: kalınlık yönü Poisson (doküman)
        ("b", "eps_x", 0.01),
        ("b", "eps_y", 0.01),
        ("b", "gamma_xy", 0.01),
        ("c", "w_center_mm", 0.01),
    ],
)
def test_vp1_ccx_vs_clt(key, quantity, rel, tmp_path):
    case = _CASE[key]
    got = ccx_measure(case, _ccx_executable(), tmp_path)[quantity]
    ref = clt_reference(case)[quantity]
    assert math.copysign(1.0, got) == math.copysign(1.0, ref)
    assert got == pytest.approx(ref, rel=rel)


@requires_ccx
def test_vp1_cross_ply_no_shear_coupling(tmp_path):
    # [0/90]s: A16 = 0 → γxy ≈ 0 (εx'e göre)
    got = ccx_measure(_CASE["a"], _ccx_executable(), tmp_path)
    assert abs(got["gamma_xy"]) < 1e-3 * abs(got["eps_x"])
    assert np.isfinite(got["eps_x"])
