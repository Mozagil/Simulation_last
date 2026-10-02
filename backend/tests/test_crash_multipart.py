"""1.11b — çok parçalı deck.

Export her elemana parçasını (hacim sırası) yazar; deck parça başına
/TETRA4, /MAT, /PROP, /PART üretir; hareketli parçalar /GRNOD/PART/1 ile
ilk hız alır, sabit parçalar /GRNOD/PART/2 + /BCS ile tutulur. Malzemesi
olmayan parça açık hata; hepsi sabitse hata.
"""

from __future__ import annotations

import gmsh
import pytest

from app.mesh.openradioss_export import gmsh_msh_to_radioss
from app.solvers.base import SolverError
from app.solvers.openradioss import OpenRadiossAdapter


def _two_part_params(tmp_path, parts=None, mats=None):
    # İki ayrı tet: eleman 1 parça 0, eleman 2 parça 1 (düğümler ayrık).
    nodes = [
        {"id": 1, "x": 0.0, "y": 0.0, "z": 0.0},
        {"id": 2, "x": 1.0, "y": 0.0, "z": 0.0},
        {"id": 3, "x": 0.0, "y": 1.0, "z": 0.0},
        {"id": 4, "x": 0.0, "y": 0.0, "z": 1.0},
        {"id": 5, "x": -5.0, "y": 0.0, "z": 0.0},
        {"id": 6, "x": -4.0, "y": 0.0, "z": 0.0},
        {"id": 7, "x": -5.0, "y": 1.0, "z": 0.0},
        {"id": 8, "x": -5.0, "y": 0.0, "z": 1.0},
    ]
    return {
        "output_dir": tmp_path / "job",
        "job_name": "mp",
        "nodes": nodes,
        "tets": [(1, 1, 2, 3, 4), (2, 5, 6, 7, 8)],
        "element_parts": {1: 0, 2: 1},
        "materials": mats
        if mats is not None
        else [
            {"part_id": 0, "name": "S235", "density": 7850.0, "youngs_modulus": 210e9, "poisson_ratio": 0.3},
            {"part_id": 1, "name": "RIGIDISH", "density": 7850.0, "youngs_modulus": 420e9, "poisson_ratio": 0.3},
        ],
        "parts": parts if parts is not None else [{"part_id": 1, "role": "fixed"}],
        "barrier": {"speed_m_s": 10.0, "angle_deg": 0.0, "wall": {"point": [0, 0, 0], "normal": [1, 0, 0]}},
    }


def test_two_parts_get_own_cards_and_groups(tmp_path):
    art = OpenRadiossAdapter().build_input(_two_part_params(tmp_path))
    s = art.path.read_text(encoding="utf-8")
    assert "/TETRA4/1" in s and "/TETRA4/2" in s
    assert "/MAT/LAW1/1" in s and "/MAT/LAW1/2" in s
    assert "/PROP/TYPE14/1" in s and "/PROP/TYPE14/2" in s
    assert "/PART/1" in s and "/PART/2" in s
    assert "part_0_moving" in s and "part_1_fixed" in s
    # ikinci parçanın E'si 420 GPa kendi kartında
    law1_2 = s.split("/MAT/LAW1/2", 1)[1].split("/PROP", 1)[0]
    assert "420" in law1_2
    # gruplar: hareketli = parça 1 (radioss id), sabit = parça 2
    assert "/GRNOD/PART/1\nmoving_parts\n         1\n" in s
    assert "/GRNOD/PART/2\nfixed_parts\n         2\n" in s
    assert "/BCS/1\nfixed_parts\n   111 111         0         2" in s
    # ilk hız hareketli gruba (grnd_ID 1)
    inivel = s.split("/INIVEL/TRA/1", 1)[1].splitlines()[2]
    assert inivel.endswith(f"{1:10d}{0:10d}")
    # TH/PART iki parçayı da listeler
    assert s.split("/TH/PART/1", 1)[1].splitlines()[3] == f"{1:10d}{2:10d}"


def test_all_parts_moving_by_default_no_bcs(tmp_path):
    art = OpenRadiossAdapter().build_input(_two_part_params(tmp_path, parts=[]))
    s = art.path.read_text(encoding="utf-8")
    assert "/GRNOD/PART/1\nmoving_parts\n         1         2\n" in s
    assert "/BCS/" not in s and "/GRNOD/PART/2" not in s


def test_missing_material_for_a_part_is_error(tmp_path):
    mats = [{"part_id": 0, "name": "S235", "density": 7850.0, "youngs_modulus": 210e9, "poisson_ratio": 0.3}]
    with pytest.raises(SolverError, match="#1"):
        OpenRadiossAdapter().build_input(_two_part_params(tmp_path, mats=mats))


def test_all_fixed_is_error(tmp_path):
    with pytest.raises(SolverError, match="hareketli"):
        OpenRadiossAdapter().build_input(
            _two_part_params(tmp_path, parts=[{"part_id": 0, "role": "fixed"}, {"part_id": 1, "role": "fixed"}])
        )


def test_single_part_mesh_keeps_legacy_single_material(tmp_path):
    """Tek parçalı mesh + part_id'siz tek malzeme: eski davranış."""
    p = _two_part_params(tmp_path, parts=[], mats=[{"name": "STEEL", "density": 7850.0, "youngs_modulus": 210e9, "poisson_ratio": 0.3}])
    p["tets"] = [(1, 1, 2, 3, 4)]
    p["element_parts"] = {1: 0}
    s = OpenRadiossAdapter().build_input(p).path.read_text(encoding="utf-8")
    assert "/PART/1" in s and "/PART/2" not in s and "/BCS/" not in s


def test_export_assigns_parts_by_volume_order(tmp_path):
    """İki ayrı kutu → .msh → export: elemanlar iki parçaya ayrılır (0, 1)."""
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("two")
        gmsh.model.occ.addBox(0, 0, 0, 10, 10, 10)
        gmsh.model.occ.addBox(20, 0, 0, 10, 10, 10)
        gmsh.model.occ.synchronize()
        gmsh.option.setNumber("Mesh.MeshSizeMax", 10)
        gmsh.model.mesh.generate(3)
        msh = tmp_path / "two_d3.msh"
        gmsh.write(str(msh))
    finally:
        gmsh.finalize()
    rm = gmsh_msh_to_radioss(msh)
    parts = set(rm.element_parts.values())
    assert parts == {0, 1}
    assert len(rm.element_parts) == len(rm.tets) + len(rm.bricks)
    # parça 0'ın düğümleri x ≤ 10, parça 1'inkiler x ≥ 20
    xyz = {n["id"]: n["x"] for n in rm.nodes}
    for eid, n1, n2, n3, n4 in rm.tets:
        xs = [xyz[n] for n in (n1, n2, n3, n4)]
        if rm.element_parts[eid] == 0:
            assert max(xs) <= 10.0 + 1e-9
        else:
            assert min(xs) >= 20.0 - 1e-9
