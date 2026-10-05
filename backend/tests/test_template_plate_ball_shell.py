"""Plaka–küre kabuk şablonu (1.18a).

Kilitlenen şey: hacim yok; plaka orta yüzeyi z = 0 (a × a), küre 6 yamalı
küp-küre ve dikişli açılışta (mesh katmanı) meshlenebiliyor; küre düğümleri
yarıçaptan < %0.2 sapıyor; 2D mesh iki parça (0 plaka, 1 küre), çakışık
düğüm yok; bölgeler 4 kenar / 1 plaka / 6 küre yüzü.
"""

from __future__ import annotations

import math

import gmsh
import numpy as np
import pytest
from pydantic import ValidationError

from app.mesh.openradioss_export import gmsh_msh_to_radioss
from app.templates import build_template, get_template
from app.templates.plate_ball_shell import (
    REGION_BALL,
    REGION_PLATE,
    REGION_PLATE_EDGE,
    PlateBallShellParams,
    ball_area_mm2,
    plate_area_mm2,
)


def _open(step_path):
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.option.setNumber("Geometry.OCCSewFaces", 1)
    gmsh.open(str(step_path))


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    t = get_template("plate_ball_shell")
    p = t.parse_params({"plate_size": 200.0, "plate_thickness": 4.0, "ball_diameter": 40.0, "gap": 2.0})
    r = build_template(t, p, tmp_path_factory.mktemp("pb") / "pb.step")
    return t, p, r


def test_registered_surface_only_with_symbols():
    t = get_template("plate_ball_shell")
    assert t.surface_only is True and t.analytic is None
    assert {"crash", "kabuk"} <= set(t.tags)
    for name, prop in t.params_schema()["properties"].items():
        if prop.get("type") in ("number", "integer"):
            assert prop.get("symbol"), f"{name} sembolsüz"


def test_regions(built):
    _t, _p, r = built
    assert len(r.regions[REGION_PLATE_EDGE]) == 4
    assert len(r.regions[REGION_PLATE]) == 1
    assert len(r.regions[REGION_BALL]) == 6
    assert not set(r.regions[REGION_PLATE]) & set(r.regions[REGION_BALL])


def test_areas_and_ball_position(built, tmp_path):
    _t, p, r = built
    _open(r.step_path)
    try:
        assert gmsh.model.getEntities(3) == []
        (plate,) = r.regions[REGION_PLATE]
        assert gmsh.model.occ.getMass(2, plate) == pytest.approx(plate_area_mm2(p), rel=1e-9)
        ball = sum(gmsh.model.occ.getMass(2, f) for f in r.regions[REGION_BALL])
        assert ball == pytest.approx(ball_area_mm2(p), rel=2e-3)
        gmsh.option.setNumber("Mesh.RecombineAll", 1)
        gmsh.option.setNumber("Mesh.MeshSizeMax", 4.0)
        gmsh.model.mesh.generate(2)  # dikişli açılışta meshlenebilmeli
        msh = tmp_path / "pb.msh"
        gmsh.write(str(msh))
        _tags, xyz, _ = gmsh.model.mesh.getNodes()
    finally:
        gmsh.finalize()
    x = np.asarray(xyz).reshape(-1, 3)
    on_ball = x[:, 2] > 1e-6
    r_nodes = np.linalg.norm(x[on_ball] - np.array([0.0, 0.0, p.ball_center_z]), axis=1)
    radius = p.ball_diameter / 2.0
    assert np.abs(r_nodes / radius - 1.0).max() < 2e-3
    # en alt küre düğümü ≈ plaka üst yüzeyi + g
    assert x[on_ball, 2].min() == pytest.approx(p.plate_thickness / 2.0 + p.gap, abs=0.1)

    rm = gmsh_msh_to_radioss(msh)
    assert rm.shells and not rm.tets
    assert set(rm.element_parts.values()) == {0, 1}
    parts = np.array([rm.element_parts[e[0]] for e in rm.shells])
    z_of = {n["id"]: n["z"] for n in rm.nodes}
    # parça 0 plaka (z = 0), parça 1 küre
    plate_z = [z_of[e[1]] for e, pid in zip(rm.shells, parts) if pid == 0]
    ball_z = [z_of[e[1]] for e, pid in zip(rm.shells, parts) if pid == 1]
    assert max(abs(z) for z in plate_z) < 1e-9 and min(ball_z) > 1.0
    coords = [(round(n["x"], 6), round(n["y"], 6), round(n["z"], 6)) for n in rm.nodes]
    assert len(coords) == len(set(coords))


def test_ball_centre_formula():
    p = PlateBallShellParams(plate_thickness=6.0, ball_diameter=30.0, gap=0.5)
    assert p.ball_center_z == pytest.approx(3.0 + 0.5 + 15.0)
    assert ball_area_mm2(p) == pytest.approx(math.pi * 900.0)


def test_invalid_params_rejected():
    with pytest.raises(ValidationError):
        PlateBallShellParams(ball_diameter=0.0)
    with pytest.raises(ValidationError):
        PlateBallShellParams(gap=-1.0)
