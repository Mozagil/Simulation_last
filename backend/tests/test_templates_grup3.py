"""Grup 3 şablonları (TODO 7): T-braket, delikli L-braket, flanş, kademeli mil.

Her şablon: kayıt + şema, parametre kısıtı, STEP + isimli bölgeler, analitik
(varsa) ve geometrinin GERÇEKTEN kurulduğunun hacimle doğrulanması.
"""

from __future__ import annotations

import math

import gmsh
import pytest
from pydantic import ValidationError

from app.templates import AnalyticInput, build_template, get_template
from app.templates.stepped_shaft import stepped_shaft_kt_bending

E_PA = 210e9
F = 500.0


def _volume(step_path) -> tuple[float, int]:
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.open(str(step_path))
        vols = gmsh.model.getEntities(3)
        return sum(gmsh.model.occ.getMass(3, t) for _d, t in vols), len(vols)
    finally:
        gmsh.finalize()


@pytest.mark.parametrize("tid", ["t_bracket", "l_bracket_bolted", "flange", "stepped_shaft"])
def test_grup3_registered_with_symbols(tid):
    t = get_template(tid)
    props = t.params_schema()["properties"]
    assert props and t.region_names()
    for name, prop in props.items():
        if prop.get("type") in ("number", "integer"):
            assert prop.get("symbol"), f"{tid}.{name} sembolsüz"
    assert "grup3" in t.tags


# --- T-braket -------------------------------------------------------------------


def test_t_bracket_rib_adds_exact_prism_volume(tmp_path):
    t = get_template("t_bracket")
    plain = t.parse_params({})
    r0 = build_template(t, plain, tmp_path / "plain.step")
    v0, n0 = _volume(r0.step_path)
    base = plain.thickness * plain.back_height * plain.width + plain.arm_length * plain.thickness * plain.width
    assert n0 == 1 and v0 == pytest.approx(base, rel=1e-6)
    assert set(r0.regions) == {"duvar_yuzu", "raf_ucu"}

    rib = t.parse_params({"rib_kind": "gusset"})
    r1 = build_template(t, rib, tmp_path / "rib.step")
    v1, n1 = _volume(r1.step_path)
    s = rib.rib_fraction * rib.arm_length
    assert n1 == 1  # kaburga gövdeye KAYNAMIŞ, ayrı katı değil
    assert v1 - base == pytest.approx(0.5 * s * s * rib.rib_thickness, rel=1e-6)


def test_t_bracket_constraints():
    t = get_template("t_bracket")
    with pytest.raises(ValidationError, match="back_height"):
        t.parse_params({"back_height": 20.0, "thickness": 8.0})
    with pytest.raises(ValidationError, match="rib_fraction"):
        t.parse_params({"rib_kind": "gusset", "rib_fraction": 1.0})


def test_t_bracket_analytic_is_plain_arm():
    t = get_template("t_bracket")
    p = t.parse_params({})
    out = t.analytic(p, AnalyticInput(force_n=F, youngs_modulus_pa=E_PA))
    inertia = p.width * p.thickness**3 / 12.0
    assert out["max_displacement"] == pytest.approx(F * p.arm_length**3 / (3 * 210e3 * inertia))
    assert out["max_von_mises"] == pytest.approx(F * p.arm_length * (p.thickness / 2) / inertia)


# --- delikli L-braket ------------------------------------------------------------


def test_l_bracket_holes_are_two_faces_and_remove_volume(tmp_path):
    t = get_template("l_bracket_bolted")
    p = t.parse_params({})
    r = build_template(t, p, tmp_path / "l.step")
    assert len(r.regions["civata_delikleri"]) == 2
    assert len(r.regions["bacak_ucu"]) == 1
    v, n = _volume(r.step_path)
    solid = (p.thickness * p.vertical_height * p.width
             + p.horizontal_length * p.thickness * p.width
             - p.thickness * p.thickness * p.width)  # köşe örtüşmesi
    holes = 2 * math.pi * (p.hole_diameter / 2) ** 2 * p.thickness
    assert n == 1 and v == pytest.approx(solid - holes, rel=1e-6)


def test_l_bracket_analytic_includes_vertical_leg_rotation():
    """Salt konsol formülü FEA'nın 2.7 katı altındaydı (ölçüldü); dik bacak dönmesi eklendi."""
    t = get_template("l_bracket_bolted")
    p = t.parse_params({})
    out = t.analytic(p, AnalyticInput(force_n=F, youngs_modulus_pa=E_PA))
    inertia = p.width * p.thickness**3 / 12
    lv = p.vertical_height - p.edge_distance - p.thickness
    expect = F * p.horizontal_length**2 / (210e3 * inertia) * (p.horizontal_length / 3 + lv)
    assert out["max_displacement"] == pytest.approx(expect)
    assert out["max_displacement"] > F * p.horizontal_length**3 / (3 * 210e3 * inertia) * 2.5
    assert out["max_von_mises"] == pytest.approx(F * p.horizontal_length * p.thickness / 2 / inertia)


def test_l_bracket_hole_constraints():
    t = get_template("l_bracket_bolted")
    with pytest.raises(ValidationError, match="edge_distance"):
        t.parse_params({"edge_distance": 4.0, "hole_diameter": 9.0})
    with pytest.raises(ValidationError, match="sığmıyor"):
        t.parse_params({"width": 30.0, "hole_diameter": 16.0})


# --- flanş ---------------------------------------------------------------------


def test_flange_bolt_faces_match_count_and_volume(tmp_path):
    t = get_template("flange")
    p = t.parse_params({"bolt_count": 8})
    r = build_template(t, p, tmp_path / "f.step")
    assert len(r.regions["civata_delikleri"]) == 8
    assert len(r.regions["boru_delik_yuzeyi"]) == 1
    v, n = _volume(r.step_path)
    ring = math.pi * (p.outer_radius**2 - p.bore_radius**2) * p.thickness
    bolts = 8 * math.pi * (p.bolt_diameter / 2) ** 2 * p.thickness
    assert n == 1 and v == pytest.approx(ring - bolts, rel=1e-6)
    assert t.analytic is None


def test_flange_constraints():
    t = get_template("flange")
    with pytest.raises(ValidationError, match="çemberi"):
        t.parse_params({"bolt_circle_radius": 78.0})
    with pytest.raises(ValidationError, match="değiyor"):
        t.parse_params({"bolt_count": 24, "bolt_diameter": 16.0})


# --- kademeli mil ----------------------------------------------------------------


def test_stepped_shaft_fillet_adds_material_and_regions(tmp_path):
    t = get_template("stepped_shaft")
    for rf in (2.0, 4.0):
        p = t.parse_params({"fillet_radius": rf})
        r = build_template(t, p, tmp_path / f"s{rf}.step")
        assert len(r.regions["ankastre_uc"]) == 1 and len(r.regions["yuk_yuzeyi"]) == 1
        v, n = _volume(r.step_path)
        sharp = math.pi * p.big_radius**2 * p.big_length + math.pi * p.small_radius**2 * p.small_length
        # İçbükey fillet malzeme EKLER (Pappus): kesit A = r²(1−π/4), köşe
        # bölgesinin ağırlık merkezi her iki kenardan 0.2232·r uzakta →
        # V = 2π (R2 + 0.2232 r) · A. Ölçüldü: r=2 → 56.34, r=4 → 235.02 mm³.
        expect = 2 * math.pi * (p.small_radius + 0.2232 * rf) * rf**2 * (1 - math.pi / 4)
        assert n == 1
        assert v - sharp == pytest.approx(expect, rel=2e-3)


def test_stepped_shaft_kt_table_and_analytic():
    # Norton tablosu: D/d = 1.5, r/d = 0.1 → Kt ≈ 0.93836 · 0.1^−0.25759 ≈ 1.70
    assert stepped_shaft_kt_bending(30.0, 20.0, 2.0) == pytest.approx(0.93836 * 0.1**-0.25759, rel=1e-6)
    assert stepped_shaft_kt_bending(30.0, 20.0, 0.05) == stepped_shaft_kt_bending(30.0, 20.0, 0.2)  # r/d alt kırpma
    assert stepped_shaft_kt_bending(21.0, 20.0, 2.0) < stepped_shaft_kt_bending(60.0, 20.0, 2.0)

    t = get_template("stepped_shaft")
    p = t.parse_params({})
    out = t.analytic(p, AnalyticInput(force_n=F, youngs_modulus_pa=E_PA))
    i1, i2 = math.pi * 15.0**4 / 4, math.pi * 10.0**4 / 4
    tip = F / 210e3 * ((120.0**3 - 60.0**3) / (3 * i1) + 60.0**3 / (3 * i2))
    assert out["max_displacement"] == pytest.approx(tip)
    kt = stepped_shaft_kt_bending(30.0, 20.0, 2.0)
    assert out["max_von_mises"] == pytest.approx(kt * F * 60.0 * 10.0 / i2)


def test_stepped_shaft_constraints():
    t = get_template("stepped_shaft")
    with pytest.raises(ValidationError, match="small_radius"):
        t.parse_params({"small_radius": 15.0})
    with pytest.raises(ValidationError, match="fillet_radius"):
        t.parse_params({"fillet_radius": 5.0})
