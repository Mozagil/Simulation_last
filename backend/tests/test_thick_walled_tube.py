"""Kalın cidarlı boru şablonu (0.4.6, Grup 1, Lamé)."""

from __future__ import annotations

from pydantic import ValidationError
import pytest

from app.templates import AnalyticInput, build_template, get_template, list_templates
from app.templates.thick_walled_tube import REGION_FIXED, REGION_INNER, REGION_OUTER, _cyl_wall

REF = {"length": 100.0, "inner_radius": 10.0, "outer_radius": 20.0}
PRESS_MPA = 10.0


def test_registry_includes_thick_walled_tube():
    assert "thick_walled_tube" in [t.id for t in list_templates()]


def test_invalid_radii_rejected():
    t = get_template("thick_walled_tube")
    with pytest.raises(ValidationError):
        t.parse_params({**REF, "outer_radius": 10.0})
    with pytest.raises(ValidationError):
        t.parse_params({**REF, "outer_radius": 8.0})
    with pytest.raises(ValidationError):
        t.parse_params({**REF, "outer_radius": 11.0})


def test_analytic_inner_wall_von_mises():
    t = get_template("thick_walled_tube")
    p = t.parse_params(REF)
    out = t.analytic(p, AnalyticInput(pressure_mpa=PRESS_MPA))
    assert "max_displacement" not in out
    # σ_θ = 10*(100+400)/(400-100)=16.667; σ_r=-10; σ_vm=√(100+277.78+166.67)=23.333
    assert out["max_von_mises"] == pytest.approx(23.333, abs=0.01)


def test_analytic_scales_with_pressure():
    t = get_template("thick_walled_tube")
    p = t.parse_params(REF)
    a = t.analytic(p, AnalyticInput(pressure_mpa=PRESS_MPA))["max_von_mises"]
    b = t.analytic(p, AnalyticInput(pressure_mpa=2 * PRESS_MPA))["max_von_mises"]
    assert b == pytest.approx(2.0 * a)


def test_build_finds_ends_and_walls(tmp_path):
    t = get_template("thick_walled_tube")
    p = t.parse_params(REF)
    r = build_template(t, p, tmp_path / "tube.step")
    assert r.step_path.exists() and r.step_path.stat().st_size > 0
    assert set(r.regions) == {REGION_FIXED, REGION_INNER, REGION_OUTER}
    assert len(r.regions[REGION_FIXED]) == 1
    assert len(r.regions[REGION_INNER]) == 1
    assert len(r.regions[REGION_OUTER]) == 1
    xmin, ymin, zmin, xmax, ymax, zmax = r.bounding_box
    assert (xmax - xmin, ymax - ymin, zmax - zmin) == pytest.approx((100, 40, 40), abs=1e-3)


def test_inner_wall_bbox_matches_inner_radius(tmp_path):
    import gmsh

    t = get_template("thick_walled_tube")
    p = t.parse_params(REF)
    r = build_template(t, p, tmp_path / "tube.step")

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.open(str(r.step_path))
        select = _cyl_wall("inner_radius")
        hits = [
            tuple(gmsh.model.getBoundingBox(2, tag))
            for _d, tag in gmsh.model.getEntities(2)
            if select(tuple(gmsh.model.getBoundingBox(2, tag)), p)
        ]
        assert len(hits) == 1
        xmin, ymin, zmin, xmax, ymax, zmax = hits[0]
        assert (xmax - xmin) == pytest.approx(p.length, abs=0.2)
        assert (ymax - ymin) == pytest.approx(2.0 * p.inner_radius, abs=0.2)
        assert (zmax - zmin) == pytest.approx(2.0 * p.inner_radius, abs=0.2)
    finally:
        gmsh.finalize()
