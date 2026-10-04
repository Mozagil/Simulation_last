"""K2 — düşme kutusu şablonu: kapalı kabuk, yön açıları, en alt nokta g'de, tek parça."""

from __future__ import annotations

import gmsh
import pytest

from app.templates import build_template, get_template
from app.templates.drop_box_shell import REGION_BOTTOM, REGION_BOX, REGION_TOP, lowest_z


@pytest.mark.parametrize("raw", [{}, {"rot_x": 45.0}, {"rot_x": 35.26, "rot_y": 45.0, "gap": 5.0}])
def test_orientations_regions_and_lowest_point(tmp_path, raw):
    t = get_template("drop_box_shell")
    p = t.parse_params({"size_x": 120.0, "size_y": 80.0, "size_z": 40.0, **raw})
    r = build_template(t, p, tmp_path / "db.step")
    assert len(r.regions[REGION_BOTTOM]) == 1 and len(r.regions[REGION_TOP]) == 1
    assert len(r.regions[REGION_BOX]) == 6
    assert lowest_z(p) == pytest.approx(p.gap, abs=1e-9)
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.option.setNumber("Geometry.OCCSewFaces", 1)
        gmsh.open(str(r.step_path))
        assert gmsh.model.getEntities(3) == []
        area = sum(gmsh.model.occ.getMass(2, f) for _d, f in gmsh.model.getEntities(2))
        assert area == pytest.approx(2 * (120 * 80 + 120 * 40 + 80 * 40), rel=1e-9)
        assert len(gmsh.model.getEntities(1)) == 12  # dikişli: 12 ortak kenar
    finally:
        gmsh.finalize()
