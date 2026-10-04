"""K3 — direk kirişi şablonu: kabuk dikdörtgen tüp (y ekseni), bölgeler, Zp."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.templates import build_template, get_template
from app.templates.pole_beam_shell import (
    REGION_END_1,
    REGION_END_2,
    REGION_FRONT,
    PoleBeamShellParams,
    plastic_modulus_mm3,
)


def test_regions_and_bbox(tmp_path):
    t = get_template("pole_beam_shell")
    p = t.parse_params({})
    r = build_template(t, p, tmp_path / "pb.step")
    assert len(r.regions[REGION_END_1]) == 4 and len(r.regions[REGION_END_2]) == 4
    assert len(r.regions[REGION_FRONT]) == 1
    x0, y0, z0, x1, y1, z1 = r.bounding_box
    assert (x0, x1) == pytest.approx((1.0, 59.0), abs=1e-6)  # orta yüzey t/2 … h − t/2
    assert (y0, y1) == pytest.approx((0.0, 800.0), abs=1e-6)


def test_plastic_modulus_thin_walled_box():
    # h' 58, b' 38, t 2: 2·(58·38 + 58²/2) = 7772 mm³
    assert plastic_modulus_mm3(PoleBeamShellParams()) == pytest.approx(7772.0)


def test_invalid():
    with pytest.raises(ValidationError):
        PoleBeamShellParams(length=100.0)
    with pytest.raises(ValidationError):
        PoleBeamShellParams(depth=3.0)
