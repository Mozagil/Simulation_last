"""1.24d — kutu (can) ezme kabuk şablonu.

Kilitlenen şey: hacim yok; bölgeler 4 yan / 1 taban / 1 kapak / 3 çarpıcı / 1 taban plakası;
alanlar formülle; çarpıcının en alt noktası kapaktan g yukarıda (θ eğimli); dikişli açılışta
meshlenebiliyor (yan yüzey 4 yama — periyodik yüzey yok); 2D mesh üç parça (0 kutu,
1 çarpıcı, 2 taban), çakışık düğüm yok.
"""

from __future__ import annotations

import math

import gmsh
import numpy as np
import pytest
from pydantic import ValidationError

from app.mesh.openradioss_export import gmsh_msh_to_radioss
from app.templates import build_template, get_template
from app.templates.can_crush_shell import (
    REGION_BASE,
    REGION_BOTTOM,
    REGION_IMPACTOR,
    REGION_SIDE,
    REGION_TOP,
    CanCrushShellParams,
)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    t = get_template("can_crush_shell")
    p = t.parse_params({})
    r = build_template(t, p, tmp_path_factory.mktemp("can") / "can.step")
    return t, p, r


def test_registered_surface_only_with_symbols():
    t = get_template("can_crush_shell")
    assert t.surface_only is True and t.analytic is None
    assert {"crash", "kabuk"} <= set(t.tags)
    for name, prop in t.params_schema()["properties"].items():
        if prop.get("type") in ("number", "integer"):
            assert prop.get("symbol"), f"{name} sembolsüz"


def test_regions(built):
    _t, _p, r = built
    assert [len(r.regions[k]) for k in (REGION_SIDE, REGION_BOTTOM, REGION_TOP, REGION_IMPACTOR, REGION_BASE)] == [4, 1, 1, 3, 1]


def test_areas_position_mesh_parts(built, tmp_path):
    _t, p, r = built
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.option.setNumber("Geometry.OCCSewFaces", 1)
    gmsh.open(str(r.step_path))
    try:
        assert gmsh.model.getEntities(3) == []
        area = lambda faces: sum(gmsh.model.occ.getMass(2, f) for f in faces)  # noqa: E731
        rr = p.can_diameter / 2.0
        assert area(r.regions[REGION_SIDE]) == pytest.approx(2 * math.pi * rr * p.can_height, rel=1e-6)
        assert area(r.regions[REGION_BOTTOM]) == pytest.approx(math.pi * rr**2, rel=1e-6)
        assert area(r.regions[REGION_TOP]) == pytest.approx(math.pi * (rr**2 - (p.hole_diameter / 2) ** 2), rel=1e-6)
        c_area = p.impactor_length * (p.impactor_width + 2 * p.impactor_flange)
        assert area(r.regions[REGION_IMPACTOR]) == pytest.approx(c_area, rel=1e-6)
        gmsh.option.setNumber("Mesh.RecombineAll", 1)
        gmsh.option.setNumber("Mesh.MeshSizeMax", 4.0)
        gmsh.model.mesh.generate(2)
        msh = tmp_path / "can.msh"
        gmsh.write(str(msh))
    finally:
        gmsh.finalize()

    rm = gmsh_msh_to_radioss(msh)
    assert rm.shells and not rm.tets
    assert set(rm.element_parts.values()) == {0, 1, 2}
    z_of = {n["id"]: n["z"] for n in rm.nodes}
    zs: dict[int, list[float]] = {0: [], 1: [], 2: []}
    for e in rm.shells:
        zs[rm.element_parts[e[0]]].extend(z_of[v] for v in e[1:])
    # parça 0 kutu 0…H, parça 1 çarpıcı (en alt = H + g), parça 2 taban (z = −g_b)
    assert min(zs[0]) == pytest.approx(0.0, abs=1e-6) and max(zs[0]) == pytest.approx(p.can_height, abs=1e-6)
    assert min(zs[1]) == pytest.approx(p.can_height + p.gap, abs=1e-3)
    assert set(round(z, 6) for z in zs[2]) == {-p.base_gap}
    coords = [(round(n["x"], 6), round(n["y"], 6), round(n["z"], 6)) for n in rm.nodes]
    assert len(coords) == len(set(coords))


def test_lift_formula_and_validation():
    p = CanCrushShellParams(impactor_angle_deg=30.0, impactor_width=40.0, can_height=100.0, gap=2.0)
    assert p.impactor_lift() == pytest.approx(100.0 + 2.0 + 20.0 * 0.5)
    with pytest.raises(ValidationError):
        CanCrushShellParams(hole_diameter=70.0)
    with pytest.raises(ValidationError):
        CanCrushShellParams(base_size=60.0)
    with pytest.raises(ValidationError):
        CanCrushShellParams(impactor_angle_deg=85.0)


def test_scenario_setup_defaults():
    """1.24d senaryo kurulumu: kutu serbest, çarpıcı hareketli + rijit gövde, taban /BCS, TYPE24 genel + Iedge 1."""
    from app.api.crash_scenario import CrashScenarioRequest, _can_setup, _default_wall

    req = CrashScenarioRequest(template_id="can_crush_shell", ball_mass_kg=5.0, ball_thickness_mm=1.0)
    s = _can_setup(req, 0.5)
    assert s["use_rigid_wall"] is False
    assert [(p["part_id"], p["role"], p["thickness_mm"]) for p in s["parts"]] == [(0, "free", 0.5), (1, "moving", 1.0), (2, "free", 1.0)]
    (rb,) = s["rigid_bodies"]
    assert (rb.name, rb.region, rb.mass_kg) == ("carpici", "carpici", 5.0)
    (bc,) = s["boundary_conditions"]
    assert (bc.part_id, bc.dofs) == (2, "111111")
    (c,) = s["contacts"]
    assert (c.type, c.all_parts, c.iedge) == (24, True, 1)
    # ilk hız −z: duvar normali +z (yazılmaz)
    assert _default_wall("can_crush_shell", {}) ["normal"] == (0.0, 0.0, 1.0)
    # açık liste olduğu gibi kullanılır
    req2 = CrashScenarioRequest(template_id="can_crush_shell", contacts=[{"type": 24, "all_parts": True, "fric": 0.2}])
    assert _can_setup(req2, 0.5)["contacts"][0].fric == 0.2
