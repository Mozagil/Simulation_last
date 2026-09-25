"""/surrogate/screen — geometri kaydı olmadan u/L ön kontrolü (WeWeb formu)."""

from __future__ import annotations

import pytest

from app.api.surrogate import ScreenBody, screen_params


def test_kiris_buyuk_sehim_ve_akma():
    body = ScreenBody(template_id="cantilever_beam",
                      params={"length": 1000.0, "thickness": 6.4, "width": 40.0},
                      youngs_modulus=68.9e9, yield_strength=276e6, load_fy=-60.2)
    out = screen_params(body, db=None)
    assert out["has_analytic"] and out["large_deformation"] is True
    assert out["u_over_l"] == pytest.approx(0.333, abs=0.002)
    assert out["exceeds_yield"] is False and out["sigma_mpa"] == pytest.approx(220.5, rel=0.01)

    small = screen_params(ScreenBody(params={"length": 500.0, "thickness": 10.0, "width": 50.0},
                                     load_fy=-500.0), db=None)
    assert small["large_deformation"] is False and small["exceeds_yield"] is False


def test_akma_asimi_bayragi():
    body = ScreenBody(params={"length": 500.0, "thickness": 10.0, "width": 50.0},
                      yield_strength=235e6, load_fy=-500.0)  # σ ≈ 300 > 235
    out = screen_params(body, db=None)
    assert out["exceeds_yield"] is True and out["large_deformation"] is False


def test_analitigi_olmayan_sablon():
    out = screen_params(ScreenBody(template_id="flange", params={}), db=None)
    assert out["has_analytic"] is False and out["large_deformation"] is False
