"""Delikli plaka şablonu (0.4.6, Grup 1)."""

from __future__ import annotations

from pydantic import ValidationError
import pytest

from app.templates import AnalyticInput, build_template, get_template, list_templates
from app.templates.plate_with_hole import (
    REGION_FIXED,
    REGION_HOLE,
    REGION_LOAD,
    _hole_wall,
    heywood_kt_net,
)

REF = {"height": 200.0, "width": 100.0, "thickness": 5.0, "diameter": 20.0}
FORCE_N = 500.0


def test_registry_includes_plate_with_hole():
    ids = [t.id for t in list_templates()]
    assert "plate_with_hole" in ids


def test_invalid_hole_rejected():
    t = get_template("plate_with_hole")
    with pytest.raises(ValidationError):
        t.parse_params({**REF, "diameter": 100.0})
    with pytest.raises(ValidationError):
        t.parse_params({**REF, "width": 30.0, "diameter": 20.0})
    with pytest.raises(ValidationError):
        t.parse_params({**REF, "height": 50.0, "diameter": 20.0})


def test_heywood_approaches_kirsch_when_hole_is_small():
    assert heywood_kt_net(1.0, 100.0) == pytest.approx(3.0, abs=0.03)


def test_analytic_default_case():
    t = get_template("plate_with_hole")
    p = t.parse_params(REF)
    out = t.analytic(p, AnalyticInput(force_n=FORCE_N))
    # λ=0.2 → K_tn=2.512; σ_net=500/(80*5)=1.25 MPa; σ_max=3.14 MPa
    assert "max_displacement" not in out
    assert out["max_von_mises"] == pytest.approx(3.14, abs=0.01)


def test_build_finds_ends_and_hole(tmp_path):
    t = get_template("plate_with_hole")
    p = t.parse_params(REF)
    r = build_template(t, p, tmp_path / "plate.step")
    assert r.step_path.exists() and r.step_path.stat().st_size > 0
    assert set(r.regions) == {REGION_FIXED, REGION_LOAD, REGION_HOLE}
    assert len(r.regions[REGION_FIXED]) == 1
    assert len(r.regions[REGION_LOAD]) == 1
    assert len(r.regions[REGION_HOLE]) == 1
    xmin, ymin, zmin, xmax, ymax, zmax = r.bounding_box
    assert (xmax - xmin, ymax - ymin, zmax - zmin) == pytest.approx((200, 100, 5), abs=1e-3)


def test_hole_face_is_centered_in_step(tmp_path):
    import gmsh

    t = get_template("plate_with_hole")
    p = t.parse_params(REF)
    r = build_template(t, p, tmp_path / "plate.step")

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.open(str(r.step_path))
        hits = [
            tuple(gmsh.model.getBoundingBox(2, tag))
            for _d, tag in gmsh.model.getEntities(2)
            if _hole_wall(tuple(gmsh.model.getBoundingBox(2, tag)), p)
        ]
        assert len(hits) == 1
        xmin, ymin, zmin, xmax, ymax, zmax = hits[0]
        assert 0.5 * (xmin + xmax) == pytest.approx(p.height / 2.0, abs=0.2)
        assert 0.5 * (ymin + ymax) == pytest.approx(p.width / 2.0, abs=0.2)
        assert (xmax - xmin) == pytest.approx(p.diameter, abs=0.2)
        assert (zmax - zmin) == pytest.approx(p.thickness, abs=0.2)
    finally:
        gmsh.finalize()
