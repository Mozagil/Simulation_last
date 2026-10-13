"""2.8 — alan görselleştirme: fonksiyon nesneleri, raw/VTK okuyucu, varsayılan ayar."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.api.cfd import auto_visualization
from app.postprocess.openfoam_viz import build_fields, read_vtk_lines
from app.solvers.openfoam_case import CfdCaseParams, case_files

VTK = """# vtk DataFile Version 2.0
tracks
ASCII
DATASET POLYDATA
POINTS 4 float
0 0 0 1 0 0 2 0 0 3 0 0
LINES 1 5
4 0 1 2 3
POINT_DATA 4
FIELD attributes 1
U 3 4 float
1 0 0 2 0 0 3 4 0 0 0 0
"""


def _case(tmp: Path) -> Path:
    surf = tmp / "postProcessing" / "vizSurfaces" / "500"
    surf.mkdir(parents=True)
    (surf / "p_body.raw").write_text("# p\n# x y z p\n0 0 0 50\n1 0 0 -50\n")
    (surf / "U_slice.raw").write_text("# U\n0 0 0 3 4 0\n")
    tr = tmp / "postProcessing" / "sets" / "vizStreamLines" / "500"
    tr.mkdir(parents=True)
    (tr / "track0.vtk").write_text(VTK)
    return tmp


def test_build_fields_incompressible(tmp_path):
    out = build_fields(_case(tmp_path), u_ref=10, p_ref=0, rho_ref=1.2, compressible=False)
    assert out["body"]["cp"] == pytest.approx([1.0, -1.0])
    assert out["slice"]["speed"] == [5.0]
    assert out["streamlines"][0]["speed"] == pytest.approx([1, 2, 5, 0])


def test_build_fields_compressible_reference(tmp_path):
    out = build_fields(_case(tmp_path), u_ref=10, p_ref=50, rho_ref=2.0, compressible=True)
    assert out["body"]["cp"] == pytest.approx([0.0, -1.0])


def test_vtk_reader_lines():
    p = Path(__file__).parent / "_tmp_track.vtk"
    p.write_text(VTK)
    try:
        lines, pts, speed = read_vtk_lines(p)
    finally:
        p.unlink()
    assert lines == [[0, 1, 2, 3]] and pts[3] == (3.0, 0.0, 0.0)


def test_case_has_viz_function_objects():
    viz = auto_visualization({"surface": {"bbox_m": [0, -0.05, -0.05, 1, 0.05, 0.05]}}, ["govde"])
    assert len(viz["streamline_seeds"]) == 25 and viz["slice_point"] == [0.5, 0.0, 0.0]
    f = case_files(CfdCaseParams(
        nu_m2_s=1e-5,
        patches=[{"name": "inlet", "kind": "inlet", "velocity_m_s": [10, 0, 0]}, {"name": "outlet", "kind": "outlet"}, {"name": "govde", "kind": "wall"}],
        visualization=viz,
    ))
    cd = f["system/controlDict"]
    assert "type            surfaces;" in cd and "patches     (govde);" in cd and "cuttingPlane" in cd
    assert "type            streamLine;" in cd and "legacy true" in cd
