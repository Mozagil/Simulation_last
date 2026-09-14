"""Dogbone çekme numunesi (0.4.6, Grup 1)."""

from __future__ import annotations

from pydantic import ValidationError
import pytest

from app.templates import AnalyticInput, build_template, get_template, list_templates
from app.templates.dogbone import (
    REGION_FIXED,
    REGION_GAUGE,
    REGION_LOAD,
    _gauge_faces,
    fillet_dx,
    total_length,
)

FORCE_N = 500.0


def test_registry_includes_dogbone():
    assert "dogbone" in [t.id for t in list_templates()]


def test_invalid_proportions_rejected():
    t = get_template("dogbone")
    with pytest.raises(ValidationError):
        t.parse_params({"grip_width": 10.0, "gauge_width": 12.5})
    with pytest.raises(ValidationError):
        t.parse_params({"fillet_radius": 0.5, "grip_width": 20.0, "gauge_width": 12.5})


def test_defaults_are_astm_e8_sheet():
    p = get_template("dogbone").parse_params({})
    assert p.gauge_length == 50.0
    assert p.gauge_width == 12.5
    assert p.grip_width == 20.0
    assert p.fillet_radius == 12.5
    assert fillet_dx(p) == pytest.approx(8.927, abs=0.01)


def test_analytic_nominal_gauge_stress():
    t = get_template("dogbone")
    p = t.parse_params({})
    out = t.analytic(p, AnalyticInput(force_n=FORCE_N))
    # 500 / (12.5 * 3) = 13.333 MPa
    assert "max_displacement" not in out
    assert out["max_von_mises"] == pytest.approx(13.333, abs=0.01)


def test_build_finds_ends_and_gauge(tmp_path):
    t = get_template("dogbone")
    p = t.parse_params({})
    r = build_template(t, p, tmp_path / "dog.step")
    assert r.step_path.exists()
    assert set(r.regions) == {REGION_FIXED, REGION_LOAD, REGION_GAUGE}
    assert len(r.regions[REGION_FIXED]) == 1
    assert len(r.regions[REGION_LOAD]) == 1
    assert len(r.regions[REGION_GAUGE]) == 2
    xmin, ymin, zmin, xmax, ymax, zmax = r.bounding_box
    assert xmax - xmin == pytest.approx(total_length(p), abs=1e-3)
    assert ymax - ymin == pytest.approx(p.grip_width, abs=1e-3)
    assert zmax - zmin == pytest.approx(p.thickness, abs=1e-3)


def test_gauge_faces_are_parallel_section(tmp_path):
    import gmsh

    t = get_template("dogbone")
    p = t.parse_params({})
    r = build_template(t, p, tmp_path / "dog.step")

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.open(str(r.step_path))
        hits = [
            tuple(gmsh.model.getBoundingBox(2, tag))
            for _d, tag in gmsh.model.getEntities(2)
            if _gauge_faces(tuple(gmsh.model.getBoundingBox(2, tag)), p)
        ]
        assert len(hits) == 2
        for xmin, ymin, _z0, xmax, ymax, _z1 in hits:
            assert abs(ymin) == pytest.approx(p.gauge_width / 2.0, abs=1e-3)
            assert (xmax - xmin) == pytest.approx(p.gauge_length, abs=0.05)
    finally:
        gmsh.finalize()
