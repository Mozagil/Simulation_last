"""Faz 2.6c — Ahmed gövdesi şablonu ve deney Cd tablosu (V-C4)."""

from __future__ import annotations

import math

import gmsh
import pytest
from pydantic import ValidationError

from app.mesh.cfd_mesher import export_surface_stl
from app.postprocess.ahmed_drag import ahmed_cd_experiment
from app.templates import TEMPLATES, build_template

T = TEMPLATES["ahmed_body"]


def test_experiment_table():
    assert ahmed_cd_experiment(25) == pytest.approx(0.285)
    assert ahmed_cd_experiment(30.0) == pytest.approx(0.378)
    assert ahmed_cd_experiment(20) is None  # ara açı için değer uydurulmaz


@pytest.mark.parametrize("phi", [0.0, 25.0, 35.0])
def test_build_closed_and_slant_geometry(tmp_path, phi):
    built = build_template(T, T.parse_params({"slant_angle_deg": phi}), tmp_path / "a.step")
    assert set(built.regions) == {"ahmed"}
    assert len(built.regions["ahmed"]) == (10 if phi == 0 else 11)
    assert built.bounding_box[2] == pytest.approx(50.0, abs=1e-3)  # zemin açıklığı
    stl = export_surface_stl(built.step_path, tmp_path / "b.stl", regions=built.regions, size_mm=20)
    assert stl.open_edges == 0
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.open(str(built.step_path))
        rear = [gmsh.model.getBoundingBox(2, t) for _, t in gmsh.model.getEntities(2)]
        rear = [bb for bb in rear if abs(bb[0] - 1044) < 0.5 and abs(bb[3] - 1044) < 0.5]
        assert len(rear) == 1
        assert rear[0][5] == pytest.approx(338 - 222 * math.sin(math.radians(phi)), abs=0.2)
    finally:
        gmsh.finalize()


def test_param_validation():
    with pytest.raises(ValidationError, match="yarıçap"):
        T.parse_params({"front_radius": 200})
    with pytest.raises(ValidationError):
        T.parse_params({"slant_angle_deg": 50})
