"""K1 — Taylor çubuğu şablonu: dolu silindir, hacim = π·D²/4·L, bölgeler, tet mesh."""

from __future__ import annotations

import math

import gmsh
import pytest
from pydantic import ValidationError

from app.templates import build_template, get_template
from app.templates.taylor_bar import REGION_BACK, REGION_FRONT, REGION_SIDE, TaylorBarParams


def test_registered_solid_crash_template_with_symbols():
    t = get_template("taylor_bar")
    assert t.surface_only is False and "crash" in t.tags
    for name, prop in t.params_schema()["properties"].items():
        assert prop.get("symbol"), name


def test_volume_and_regions(tmp_path):
    t = get_template("taylor_bar")
    p = t.parse_params({"length": 40.0, "diameter": 8.0})
    r = build_template(t, p, tmp_path / "tb.step")
    assert all(len(r.regions[k]) == 1 for k in (REGION_FRONT, REGION_BACK, REGION_SIDE))
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.open(str(r.step_path))
        (vol,) = gmsh.model.getEntities(3)
        assert gmsh.model.occ.getMass(3, vol[1]) == pytest.approx(math.pi * 16.0 * 40.0, rel=1e-6)
        x0, _, _, x1, _, _ = gmsh.model.getBoundingBox(-1, -1)
        assert (x0, x1) == pytest.approx((0.0, 40.0), abs=1e-6)
    finally:
        gmsh.finalize()


def test_invalid_params():
    with pytest.raises(ValidationError):
        TaylorBarParams(length=5.0, diameter=10.0)
