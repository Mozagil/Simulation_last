"""K4 — ROPS portal şablonu: tek parça bükülmüş tüp, uyumlu mesh, bölgeler, Zp."""

from __future__ import annotations

import gmsh
import pytest
from pydantic import ValidationError

from app.mesh.openradioss_export import gmsh_msh_to_radioss
from app.templates import build_template, get_template
from app.templates.rops_frame_shell import (
    REGION_BASE_1,
    REGION_BASE_2,
    REGION_LOAD,
    RopsFrameShellParams,
    plastic_modulus_mm3,
)


def test_regions_single_part_conforming_mesh(tmp_path):
    t = get_template("rops_frame_shell")
    p = t.parse_params({"span": 600.0, "height": 700.0, "bend_radius": 100.0})
    r = build_template(t, p, tmp_path / "r.step")
    assert len(r.regions[REGION_BASE_1]) == 4 and len(r.regions[REGION_BASE_2]) == 4
    assert len(r.regions[REGION_LOAD]) == 4
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.option.setNumber("Geometry.OCCSewFaces", 1)
        gmsh.open(str(r.step_path))
        assert len(gmsh.model.getEntities(2)) == 20  # 5 segment × 4 yüz
        gmsh.option.setNumber("Mesh.RecombineAll", 1)
        gmsh.option.setNumber("Mesh.MeshSizeMax", 25.0)
        gmsh.model.mesh.generate(2)
        msh = tmp_path / "r.msh"
        gmsh.write(str(msh))
    finally:
        gmsh.finalize()
    rm = gmsh_msh_to_radioss(msh)
    assert set(rm.element_parts.values()) == {0}
    coords = [(round(n["x"], 5), round(n["y"], 5), round(n["z"], 5)) for n in rm.nodes]
    assert len(coords) == len(set(coords))  # birleşimde ikiz düğüm yok


def test_plastic_modulus():
    assert plastic_modulus_mm3(RopsFrameShellParams()) == pytest.approx(4.0 * (80 * 60 + 80 * 80 / 2))


def test_invalid():
    with pytest.raises(ValidationError):
        RopsFrameShellParams(bend_radius=30.0)  # ≤ d/2
