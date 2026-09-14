"""Burulma mili şablonu (0.4.6, Grup 1, τ = TR/J)."""

from __future__ import annotations

import math

from pydantic import ValidationError
import pytest

from app.templates import AnalyticInput, build_template, get_template, list_templates
from app.templates.torsion_shaft import (
    REGION_FIXED,
    REGION_TORQUE,
    _free_end_circle,
    polar_inertia,
)

REF = {"length": 100.0, "radius": 10.0}
FORCE_N = 500.0
E_PA = 210e9
NU = 0.3


def test_registry_includes_torsion_shaft():
    assert "torsion_shaft" in [t.id for t in list_templates()]


def test_invalid_stubby_shaft_rejected():
    t = get_template("torsion_shaft")
    with pytest.raises(ValidationError):
        t.parse_params({"length": 30.0, "radius": 10.0})


def test_analytic_pure_shear():
    t = get_template("torsion_shaft")
    p = t.parse_params(REF)
    out = t.analytic(p, AnalyticInput(force_n=FORCE_N, youngs_modulus_pa=E_PA, poisson_ratio=NU))
    torque = FORCE_N * p.radius
    polar = polar_inertia(p.radius)
    tau = torque * p.radius / polar
    g_mpa = E_PA / 1e6 / (2.0 * (1.0 + NU))
    tip = torque * p.length * p.radius / (g_mpa * polar)
    assert out["max_von_mises"] == pytest.approx(math.sqrt(3.0) * tau, abs=1e-6)
    assert out["max_displacement"] == pytest.approx(tip, abs=1e-6)
    assert out["max_von_mises"] == pytest.approx(5.513, abs=0.01)


def test_analytic_scales_inverse_radius_squared():
    """T=F·R, J∝R⁴ → τ ∝ F/R²."""
    t = get_template("torsion_shaft")
    a = t.analytic(
        t.parse_params({"length": 100.0, "radius": 10.0}),
        AnalyticInput(force_n=FORCE_N, youngs_modulus_pa=E_PA),
    )["max_von_mises"]
    b = t.analytic(
        t.parse_params({"length": 100.0, "radius": 20.0}),
        AnalyticInput(force_n=FORCE_N, youngs_modulus_pa=E_PA),
    )["max_von_mises"]
    assert b == pytest.approx(a / 4.0, rel=1e-6)


def test_build_finds_fixed_face_and_torque_edge(tmp_path):
    t = get_template("torsion_shaft")
    p = t.parse_params(REF)
    r = build_template(t, p, tmp_path / "shaft.step")
    assert r.step_path.exists() and r.step_path.stat().st_size > 0
    assert set(r.regions) == {REGION_FIXED, REGION_TORQUE}
    assert len(r.regions[REGION_FIXED]) == 1
    assert len(r.regions[REGION_TORQUE]) == 1
    xmin, ymin, zmin, xmax, ymax, zmax = r.bounding_box
    assert (xmax - xmin, ymax - ymin, zmax - zmin) == pytest.approx((100, 20, 20), abs=1e-3)


def test_torque_edge_is_circle_at_free_end(tmp_path):
    import gmsh

    t = get_template("torsion_shaft")
    p = t.parse_params(REF)
    r = build_template(t, p, tmp_path / "shaft.step")

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.open(str(r.step_path))
        hits = [
            tuple(gmsh.model.getBoundingBox(1, tag))
            for _d, tag in gmsh.model.getEntities(1)
            if _free_end_circle(tuple(gmsh.model.getBoundingBox(1, tag)), p)
        ]
        assert len(hits) == 1
        xmin, ymin, zmin, xmax, ymax, zmax = hits[0]
        assert xmin == pytest.approx(p.length, abs=1e-3)
        assert xmax == pytest.approx(p.length, abs=1e-3)
        assert (ymax - ymin) == pytest.approx(2.0 * p.radius, abs=0.2)
        assert (zmax - zmin) == pytest.approx(2.0 * p.radius, abs=0.2)
    finally:
        gmsh.finalize()
