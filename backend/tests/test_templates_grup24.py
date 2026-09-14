"""Grup 2 (profil) + Grup 4 (çentik/kama) şablon regresyonu.

Her şablon: parametre kısıtı, analitik aralık, STEP + isimli bölgeler.
ccx uçtan uca yok — o Grup 1 kantilever kilidine aittir.
"""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from app.templates import AnalyticInput, build_template, get_template
from app.templates.beam_section import (
    box_tube_inertia,
    cantilever_fl_over_ei,
    circular_tube_inertia,
    equal_l_angle_inertia_and_c,
    i_beam_inertia,
)
from app.templates.keyway_shaft import keyway_kt_torsion
from app.templates.notched_bar import neuber_kt

E_PA = 210e9
F = 500.0


@pytest.mark.parametrize(
    "tid",
    ["i_beam", "box_tube", "circular_tube", "l_angle", "notched_bar", "keyway_shaft"],
)
def test_grup24_registered_with_analytic(tid):
    t = get_template(tid)
    assert t.analytic is not None
    assert t.params_schema()["properties"]
    assert t.region_names()


def test_i_beam_inertia_and_analytic():
    i = i_beam_inertia(80.0, 50.0, 6.0, 8.0)
    inner_h = 80.0 - 16.0
    expect = (50.0 * 80.0**3 - 44.0 * inner_h**3) / 12.0
    assert i == pytest.approx(expect)
    t = get_template("i_beam")
    p = t.parse_params({})
    out = t.analytic(p, AnalyticInput(force_n=F, youngs_modulus_pa=E_PA))
    ref = cantilever_fl_over_ei(p.length, i, 40.0, F, E_PA)
    assert out["max_displacement"] == pytest.approx(ref["max_displacement"])
    assert out["max_von_mises"] == pytest.approx(ref["max_von_mises"])


def test_box_and_tube_and_l_analytics():
    assert box_tube_inertia(60.0, 40.0, 4.0) > 0
    assert circular_tube_inertia(20.0, 16.0) == pytest.approx(
        math.pi / 4.0 * (20.0**4 - 16.0**4)
    )
    i, c = equal_l_angle_inertia_and_c(40.0, 5.0)
    assert i > 0 and 0 < c < 40.0
    for tid in ("box_tube", "circular_tube", "l_angle"):
        t = get_template(tid)
        out = t.analytic(t.parse_params({}), AnalyticInput(force_n=F, youngs_modulus_pa=E_PA))
        assert out["max_displacement"] > 0
        assert out["max_von_mises"] > 0


def test_notched_neuber_semicircle_is_three():
    assert neuber_kt(4.0, 4.0) == pytest.approx(3.0)
    t = get_template("notched_bar")
    p = t.parse_params({"notch_kind": "u", "notch_radius": 4.0, "width": 40.0})
    out = t.analytic(p, AnalyticInput(force_n=1000.0))
    net = (40.0 - 8.0) * 8.0
    assert out["max_von_mises"] == pytest.approx(3.0 * 1000.0 / net)
    sharper = neuber_kt(6.0, 2.0, 60.0)
    blunt = neuber_kt(6.0, 2.0, 120.0)
    assert sharper > blunt


def test_keyway_kt_increases_when_fillet_shrinks():
    assert keyway_kt_torsion(24.0, 0.2) > keyway_kt_torsion(24.0, 1.0)
    t = get_template("keyway_shaft")
    out = t.analytic(t.parse_params({}), AnalyticInput(force_n=100.0, youngs_modulus_pa=E_PA))
    assert "max_von_mises" in out
    assert out["max_von_mises"] > 0


@pytest.mark.parametrize(
    "tid,bad",
    [
        ("i_beam", {"length": 100, "height": 80}),
        ("box_tube", {"wall": 40, "height": 60, "width": 40}),
        ("circular_tube", {"inner_radius": 20, "outer_radius": 20}),
        ("l_angle", {"leg": 5, "thickness": 5}),
        ("notched_bar", {"notch_radius": 30, "width": 40}),
        ("keyway_shaft", {"key_depth": 20, "radius": 12}),
    ],
)
def test_invalid_params_rejected(tid, bad):
    with pytest.raises(ValidationError):
        get_template(tid).parse_params(bad)


@pytest.mark.parametrize(
    "tid,params",
    [
        ("i_beam", {}),
        ("box_tube", {}),
        ("circular_tube", {}),
        ("l_angle", {}),
        ("notched_bar", {"notch_kind": "u"}),
        ("notched_bar", {"notch_kind": "v", "notch_depth": 6.0, "notch_radius": 1.0}),
        ("keyway_shaft", {}),
    ],
)
def test_build_writes_step_and_named_regions(tmp_path, tid, params):
    t = get_template(tid)
    p = t.parse_params(params)
    r = build_template(t, p, tmp_path / f"{tid}.step")
    assert r.step_path.exists() and r.step_path.stat().st_size > 0
    assert set(r.regions) == set(t.region_names())
    for name, tags in r.regions.items():
        assert len(tags) >= 1, name
    xmin, ymin, zmin, xmax, ymax, zmax = r.bounding_box
    assert xmax > xmin
    assert math.isfinite(xmin) and math.isfinite(xmax)
