"""CalculiX adaptör: .inp üretimi (ccx olmadan)."""

from pathlib import Path

import pytest

from app.mesh.base import MeshParams
from app.mesh.gmsh_adapter import GmshMesherAdapter
from app.solvers.calculix import CalculiXAdapter
from app.solvers.base import SolverError

FIXTURES = Path(__file__).parent / "fixtures"
BOX = FIXTURES / "box.step"


def test_calculix_build_input_writes_material_and_section(tmp_path):
    step = tmp_path / "box.step"
    step.write_bytes(BOX.read_bytes())
    adapter = GmshMesherAdapter()
    geom = adapter.import_geometry(step)
    mesh = adapter.generate_mesh(
        geom, MeshParams(element_size=8.0, dimension=3, element_scheme="tet")
    )

    ccx = CalculiXAdapter()
    artifact = ccx.build_input(
        {
            "mesh_path": mesh.mesh_path,
            "dimension": 3,
            "output_dir": tmp_path / "run",
            "job_name": "testjob",
            "materials": [
                {
                    "part_id": 0,
                    "name": "S355",
                    "youngs_modulus": 210e9,
                    "poisson_ratio": 0.3,
                    "density": 7850.0,
                }
            ],
            "bcs": [
                {"type": "fixed", "face_ids": [1]},
                {"type": "cload", "face_ids": [2], "fx": 0, "fy": 0, "fz": -1000},
                {"type": "gravity", "gx": 0, "gy": 0, "gz": -9810},
                {
                    "type": "displacement",
                    "edge_ids": [1],
                    "dofs": {"1": 0.0, "2": 0.0},
                },
                {
                    "type": "bearing",
                    "face_ids": [3],
                    "magnitude": 5000,
                    "axis": [0, 0, -1],
                },
                {
                    "type": "pressure",
                    "face_ids": [4],
                    "magnitude": 1e5,
                    "dz": -1,
                },
            ],
        }
    )
    text = artifact.path.read_text(encoding="utf-8")
    assert "*MATERIAL, NAME=S355" in text
    assert "*ELASTIC" in text
    assert "*DENSITY" in text
    assert "*SOLID SECTION" in text
    assert "*BOUNDARY" in text
    assert "*CLOAD" in text
    assert "*STEP" in text
    assert "GRAV" in text


def test_bcs_pressure_dload_and_sliding_transform():
    from app.solvers.calculix import _bcs_inp_block

    nsets = {"FACE_1": [1, 2, 3], "EDGE_1": [4, 5]}
    elsets = {"FACE_EL_1": [10, 11], "PART_0": [10, 11]}
    text = _bcs_inp_block(
        [
            {"type": "pressure", "face_ids": [1], "magnitude": 1e5},
            {
                "type": "sliding",
                "edge_ids": [1],
                "normal": [0.0, 0.0, 1.0],
            },
            {"type": "gravity", "gx": 0, "gy": 0, "gz": -9810},
        ],
        nsets,
        elsets,
        dimension=2,
    )
    assert "*DLOAD" in text
    assert "FACE_EL_1, P," in text
    assert "*TRANSFORM, NSET=EDGE_1" in text
    assert "EDGE_1, 1, 1" in text
    assert "PART_0, GRAV," in text


def test_calculix_submit_without_ccx_raises(tmp_path):
    inp = tmp_path / "x.inp"
    inp.write_text("*HEADING\n", encoding="utf-8")
    from app.solvers.base import InputArtifact

    ccx = CalculiXAdapter()
    with pytest.raises(SolverError, match="ccx"):
        ccx.submit(InputArtifact(path=inp))
