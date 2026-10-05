"""K7 — S-kiriş şablonu: süpürülmüş tüp, alan = çevre × yol, uyumlu mesh, uç halkaları."""

from __future__ import annotations

import math

import gmsh
import pytest

from app.templates import build_template, get_template
from app.templates.s_rail_shell import REGION_BACK, REGION_FRONT, SRailShellParams, end_point, path_length


def test_geometry_area_and_regions(tmp_path):
    t = get_template("s_rail_shell")
    p = t.parse_params({"bend_angle": 30.0})
    r = build_template(t, p, tmp_path / "s.step")
    assert len(r.regions[REGION_FRONT]) == 4 and len(r.regions[REGION_BACK]) == 4
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.option.setNumber("Geometry.OCCSewFaces", 1)
        gmsh.open(str(r.step_path))
        area = sum(gmsh.model.occ.getMass(2, f) for _d, f in gmsh.model.getEntities(2))
        assert area == pytest.approx(2 * (p.height + p.width) * path_length(p), rel=1e-6)
    finally:
        gmsh.finalize()


def test_end_point_and_offset():
    p = SRailShellParams(front_length=100, rear_length=200, bend_radius=150, bend_angle=45)
    x, y = end_point(p)
    assert x == pytest.approx(300 + 300 * math.sin(math.radians(45)))
    assert y == pytest.approx(300 * (1 - math.cos(math.radians(45))))
