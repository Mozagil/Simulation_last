"""Faz 1.2 — Gmsh .msh → OpenRadioss /TETRA4 (CalculiX tet10 yolu değişmez)."""

from pathlib import Path

import pytest

from app.mesh.base import MeshError, MeshParams
from app.mesh.gmsh_adapter import GmshMesherAdapter
from app.mesh.openradioss_export import gmsh_msh_to_radioss
from app.solvers.openradioss import OpenRadiossAdapter

FIXTURES_DIR = Path(__file__).parent / "fixtures"
BOX_STEP = FIXTURES_DIR / "box.step"


def _write_msh(path: Path, nodes: list[tuple], elements: list[str]) -> None:
    lines = [
        "$MeshFormat",
        "2.2 0 8",
        "$EndMeshFormat",
        "$Nodes",
        str(len(nodes)),
    ]
    for nid, x, y, z in nodes:
        lines.append(f"{nid} {x} {y} {z}")
    lines.extend(["$EndNodes", "$Elements", str(len(elements)), *elements, "$EndElements", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def test_tet4_msh_exports_nodes_and_tets(tmp_path):
    msh = tmp_path / "unit_tet.msh"
    # Sağ el: hacim > 0
    _write_msh(
        msh,
        [
            (1, 0.0, 0.0, 0.0),
            (2, 1.0, 0.0, 0.0),
            (3, 0.0, 1.0, 0.0),
            (4, 0.0, 0.0, 1.0),
        ],
        ["1 4 2 0 1 1 2 3 4"],
    )
    out = gmsh_msh_to_radioss(msh)
    assert len(out.nodes) == 4
    assert len(out.tets) == 1
    assert out.tets[0][1:] == (1, 2, 3, 4)
    assert out.bricks == []


def test_inverted_tet_is_reordered_to_positive_volume(tmp_path):
    msh = tmp_path / "inv_tet.msh"
    _write_msh(
        msh,
        [
            (1, 0.0, 0.0, 0.0),
            (2, 1.0, 0.0, 0.0),
            (3, 0.0, 1.0, 0.0),
            (4, 0.0, 0.0, 1.0),
        ],
        # n3/n4 yer değişik — negatif hacim
        ["1 4 2 0 1 1 2 4 3"],
    )
    out = gmsh_msh_to_radioss(msh)
    _e, n1, n2, n3, n4 = out.tets[0]
    xyz = {n["id"]: (n["x"], n["y"], n["z"]) for n in out.nodes}
    from app.mesh.openradioss_export import _tet_signed_volume

    assert _tet_signed_volume(xyz[n1], xyz[n2], xyz[n3], xyz[n4]) > 0


def test_tet10_drops_midside_nodes(tmp_path):
    """10 düğümlü tet → 4 köşe; kenar-ortası /NODE'a yazılmaz."""
    msh = tmp_path / "tet10.msh"
    nodes = [
        (1, 0.0, 0.0, 0.0),
        (2, 1.0, 0.0, 0.0),
        (3, 0.0, 1.0, 0.0),
        (4, 0.0, 0.0, 1.0),
        (5, 0.5, 0.0, 0.0),
        (6, 0.5, 0.5, 0.0),
        (7, 0.0, 0.5, 0.0),
        (8, 0.0, 0.0, 0.5),
        (9, 0.5, 0.0, 0.5),
        (10, 0.0, 0.5, 0.5),
    ]
    # Gmsh type 11 = tet10, 2 tags
    _write_msh(msh, nodes, ["1 11 2 0 1 1 2 3 4 5 6 7 8 9 10"])
    out = gmsh_msh_to_radioss(msh)
    assert {n["id"] for n in out.nodes} == {1, 2, 3, 4}
    assert out.tets[0][1:] == (1, 2, 3, 4)


def test_triangle_only_msh_rejected(tmp_path):
    msh = tmp_path / "shell.msh"
    _write_msh(
        msh,
        [(1, 0, 0, 0), (2, 1, 0, 0), (3, 0, 1, 0)],
        ["1 2 2 0 1 1 2 3"],
    )
    with pytest.raises(MeshError, match="3D tet/hex"):
        gmsh_msh_to_radioss(msh)


def test_missing_file_raises(tmp_path):
    with pytest.raises(MeshError, match="yok"):
        gmsh_msh_to_radioss(tmp_path / "nope.msh")


def test_generate_mesh_tet10_export_does_not_rewrite_msh(tmp_path):
    """CalculiX tet10 .msh aynı kalır; export ayrı liste üretir."""
    step = tmp_path / "box.step"
    step.write_bytes(BOX_STEP.read_bytes())
    adapter = GmshMesherAdapter()
    geom = adapter.import_geometry(step)
    mesh = adapter.generate_mesh(geom, MeshParams(element_size=5.0, dimension=3))
    assert "Tetrahedron10" in mesh.element_type_counts
    before = mesh.mesh_path.read_bytes()
    out = gmsh_msh_to_radioss(mesh.mesh_path)
    assert mesh.mesh_path.read_bytes() == before
    assert out.tets
    assert all(len(t) == 5 for t in out.tets)
    assert len(out.nodes) < mesh.node_count
    assert len(out.nodes) >= 4


def test_build_input_accepts_mesh_path(tmp_path):
    msh = tmp_path / "unit_tet.msh"
    _write_msh(
        msh,
        [
            (1, 0.0, 0.0, 10.0),
            (2, 1.0, 0.0, 10.0),
            (3, 0.0, 1.0, 10.0),
            (4, 0.0, 0.0, 11.0),
        ],
        ["1 4 2 0 1 1 2 3 4"],
    )
    art = OpenRadiossAdapter().build_input(
        {
            "output_dir": tmp_path / "job",
            "job_name": "from_msh",
            "mesh_path": msh,
            "initial_velocity": {"vx": 0.0, "vy": 0.0, "vz": -1000.0},
        }
    )
    text = art.path.read_text(encoding="utf-8")
    assert "/TETRA4/1/1" in text
    assert "/NODE" in text
    assert "-1000" in text
