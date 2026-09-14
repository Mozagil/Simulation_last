"""0.5.2: .inp saklanmaz, DB anlığından yeniden üretilir."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.dataset.rebuild import (
    build_input_from_snapshot,
    discard_solver_input,
)
from app.mesh.base import MeshParams
from app.mesh.gmsh_adapter import GmshMesherAdapter
from app.models.run import AnalysisRun


def _box_mesh(tmp_path: Path):
    import gmsh

    step = tmp_path / "box.step"
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("box")
        gmsh.model.occ.addBox(0, 0, 0, 20, 10, 8)
        gmsh.model.occ.synchronize()
        gmsh.write(str(step))
    finally:
        gmsh.finalize()

    adapter = GmshMesherAdapter()
    geom = adapter.import_geometry(step)
    mesh = adapter.generate_mesh(
        geom, MeshParams(element_size=5.0, dimension=3, element_scheme="tet")
    )
    return mesh.mesh_path


def test_rebuild_inp_matches_original_cards(tmp_path):
    mesh_path = _box_mesh(tmp_path)
    materials = [
        {
            "part_id": 0,
            "name": "S235",
            "youngs_modulus": 210e9,
            "poisson_ratio": 0.3,
            "density": 7850.0,
        }
    ]
    bcs = [
        {"type": "fixed", "face_ids": [1]},
        {"type": "cload", "face_ids": [2], "fx": 0.0, "fy": -500.0, "fz": 0.0},
    ]
    first = build_input_from_snapshot(
        mesh_path=mesh_path,
        output_dir=tmp_path / "a",
        job_name="orig",
        dimension=3,
        bcs=bcs,
        materials=materials,
    )
    second = build_input_from_snapshot(
        mesh_path=mesh_path,
        output_dir=tmp_path / "b",
        job_name="copy",
        dimension=3,
        bcs=bcs,
        materials=materials,
    )
    t1 = first.path.read_text(encoding="utf-8")
    t2 = second.path.read_text(encoding="utf-8")
    for token in ("*MATERIAL", "*ELASTIC", "*CLOAD", "*BOUNDARY", "*SOLID SECTION"):
        assert token in t1
        assert token in t2
    assert t1.count("*CLOAD") == t2.count("*CLOAD")
    # Toplam kuvvet düğümlere bölünür; her iki üretim aynı dağılımı yazmalı.
    assert t1.split("*STEP")[-1] == t2.split("*STEP")[-1]


def test_discard_solver_input_deletes_file_and_clears_path(tmp_path):
    inp = tmp_path / "run1.inp"
    inp.write_text("*HEADING\n", encoding="utf-8")
    run = AnalysisRun(
        geometry_id=1,
        dimension=3,
        bcs=[],
        materials_snapshot=[],
        status="solved",
        inp_path=str(inp),
    )
    discard_solver_input(run)
    assert not inp.exists()
    assert run.inp_path is None
