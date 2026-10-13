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


def test_triangle_only_msh_becomes_sh3n(tmp_path):
    """1.13: hacimsiz mesh kabuk olarak okunur (önce reddediliyordu)."""
    msh = tmp_path / "shell.msh"
    _write_msh(
        msh,
        [(1, 0, 0, 0), (2, 1, 0, 0), (3, 0, 1, 0)],
        ["1 2 2 0 1 1 2 3"],
    )
    out = gmsh_msh_to_radioss(msh)
    assert out.sh3n == [(1, 1, 2, 3)] and not out.tets and not out.shells
    assert out.element_parts == {1: 0}


def test_line_only_msh_rejected(tmp_path):
    msh = tmp_path / "wire.msh"
    _write_msh(msh, [(1, 0, 0, 0), (2, 1, 0, 0)], ["1 1 2 0 1 1 2"])
    with pytest.raises(MeshError, match="kabuk"):
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
    assert "/TETRA4/1\n" in text
    assert "/NODE" in text
    assert "-1000" in text


def test_element_ids_are_gmsh_tags(tmp_path):
    """1.22: deck eleman no'su = Gmsh eleman tag'i (1'den yeniden numaralama yok)."""
    msh = tmp_path / "tagged.msh"
    nodes = [(1, 0.0, 0.0, 0.0), (2, 1.0, 0.0, 0.0), (3, 0.0, 1.0, 0.0), (4, 0.0, 0.0, 1.0)]
    _write_msh(msh, nodes, ["57 4 2 0 1 1 2 3 4"])
    out = gmsh_msh_to_radioss(msh)
    assert out.tets[0][0] == 57 and out.element_parts == {57: 0}

    shell = tmp_path / "tagged_shell.msh"
    _write_msh(shell, nodes[:3], ["42 2 2 0 1 1 2 3"])
    assert gmsh_msh_to_radioss(shell).sh3n == [(42, 1, 2, 3)]


def test_preview_element_and_node_tags_match_export(tmp_path):
    """Viewport eleman/düğüm seçimi (önizleme `element_tags` / `node_tags`) deck no'larıyla aynı."""
    import gmsh

    from app.mesh.gmsh_adapter import _extract_mesh_wireframe_preview, _gmsh_lock

    step = tmp_path / "box.step"
    step.write_bytes(BOX_STEP.read_bytes())
    adapter = GmshMesherAdapter()
    mesh = adapter.generate_mesh(adapter.import_geometry(step), MeshParams(element_size=5.0, dimension=3))
    out = gmsh_msh_to_radioss(mesh.mesh_path)

    with _gmsh_lock:
        gmsh.initialize(interruptible=False)
        try:
            gmsh.option.setNumber("General.Terminal", 0)
            gmsh.open(str(mesh.mesh_path))
            preview = _extract_mesh_wireframe_preview(3)
        finally:
            gmsh.finalize()

    deck_eids = {t[0] for t in out.tets}
    tags = preview["element_tags"]
    assert len(tags) == len(out.tets)
    assert set(tags) == deck_eids
    # Yüzey üçgeninin elemanı deck'teki aynı tet: düğümleri o tet'in köşeleri.
    tet_by_id = {t[0]: set(t[1:]) for t in out.tets}
    node_tags = preview["node_tags"]
    faces = preview["faces"]
    for tri, el in enumerate(preview["triangle_to_element"][:50]):
        corners = {node_tags[faces[tri * 3 + k]] for k in range(3)}
        assert corners <= tet_by_id[tags[el]]
