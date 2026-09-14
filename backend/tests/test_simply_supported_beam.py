"""Basit mesnetli kiriş şablonu (0.4.6, Grup 1)."""

from __future__ import annotations

from pydantic import ValidationError
import pytest

from app.templates import AnalyticInput, build_template, get_template, list_templates
from app.templates.simply_supported_beam import (
    REGION_LEFT,
    REGION_MID_LOAD,
    REGION_RIGHT,
    REGION_UDL,
    _top_mid_line,
)

REF = {"length": 500.0, "thickness": 10.0, "width": 50.0}
FORCE_N = 500.0
E_PA = 210e9


def test_registry_includes_simply_supported():
    ids = [t.id for t in list_templates()]
    assert "simply_supported_beam" in ids
    assert "cantilever_beam" in ids


def test_invalid_short_beam_rejected():
    with pytest.raises(ValidationError):
        get_template("simply_supported_beam").parse_params({"length": 40, "thickness": 10})


def test_analytic_midspan_point_load():
    t = get_template("simply_supported_beam")
    p = t.parse_params(REF)
    out = t.analytic(p, AnalyticInput(force_n=FORCE_N, youngs_modulus_pa=E_PA))
    assert out["max_displacement"] == pytest.approx(1.4881, abs=0.001)
    assert out["max_von_mises"] == pytest.approx(75.0, abs=0.01)


def test_analytic_udl_total_force():
    t = get_template("simply_supported_beam")
    p = t.parse_params(REF)
    out = t.analytic(
        p, AnalyticInput(force_n=FORCE_N, youngs_modulus_pa=E_PA, distributed=True)
    )
    assert out["max_displacement"] == pytest.approx(0.9301, abs=0.001)
    assert out["max_von_mises"] == pytest.approx(37.5, abs=0.01)


def test_build_finds_supports_and_mid_edge(tmp_path):
    t = get_template("simply_supported_beam")
    p = t.parse_params({"length": 300, "thickness": 20, "width": 40})
    r = build_template(t, p, tmp_path / "ss.step")

    assert r.step_path.exists() and r.step_path.stat().st_size > 0
    assert set(r.regions) == {REGION_LEFT, REGION_RIGHT, REGION_MID_LOAD, REGION_UDL}
    assert len(r.regions[REGION_LEFT]) == 1
    assert len(r.regions[REGION_RIGHT]) == 1
    assert len(r.regions[REGION_MID_LOAD]) == 1
    assert len(r.regions[REGION_UDL]) == 2
    assert r.regions[REGION_LEFT] != r.regions[REGION_RIGHT]

    xmin, ymin, zmin, xmax, ymax, zmax = r.bounding_box
    assert (xmax - xmin, ymax - ymin, zmax - zmin) == pytest.approx((300, 20, 40), abs=1e-4)


def test_mid_load_is_top_edge_at_half_span(tmp_path):
    """Point load kenarı STEP'te geometrik olarak x=L/2, y=T, z=W."""
    import gmsh

    t = get_template("simply_supported_beam")
    p = t.parse_params(REF)
    r = build_template(t, p, tmp_path / "ss.step")

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.open(str(r.step_path))
        hits = []
        for _dim, tag in gmsh.model.getEntities(1):
            bb = tuple(gmsh.model.getBoundingBox(1, tag))
            if _top_mid_line(bb, p):
                hits.append(bb)
        assert len(hits) == 1
        xmin, ymin, zmin, xmax, ymax, zmax = hits[0]
        assert xmin == pytest.approx(p.length / 2.0, abs=1e-4)
        assert xmax == pytest.approx(p.length / 2.0, abs=1e-4)
        assert ymin == pytest.approx(p.thickness, abs=1e-4)
        assert (zmax - zmin) == pytest.approx(p.width, abs=1e-3)
    finally:
        gmsh.finalize()
