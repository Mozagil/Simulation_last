"""1.13a — kabuk: /SHELL + /SH3N + /PROP/TYPE1, kalınlık, temas yüzeyi.

Kart düzenleri OpenRadioss hm_cfg tanımlarından (radioss2020
prop_p1_shell, radioss41 shell4n/shell3n — 2022 bu düzenleri kullanır).
"""

from __future__ import annotations

import gmsh
import pytest
from pydantic import ValidationError

from app.mesh.openradioss_export import gmsh_msh_to_radioss
from app.solvers.base import SolverError
from app.solvers.crash_params import CrashShellParams
from app.solvers.openradioss import OpenRadiossAdapter
from tests.test_crash_contact import _card

_MATS = [
    {"part_id": 0, "name": "S235", "density": 7850.0, "youngs_modulus": 210e9, "poisson_ratio": 0.3},
    {"part_id": 1, "name": "S355", "density": 7850.0, "youngs_modulus": 210e9, "poisson_ratio": 0.3},
]


def _shell_params(tmp_path, **extra):
    # Parça 0: bir dörtgen + bir üçgen kabuk; parça 1: bir tet (solid).
    nodes = [
        {"id": 1, "x": 0.0, "y": 0.0, "z": 0.0},
        {"id": 2, "x": 1.0, "y": 0.0, "z": 0.0},
        {"id": 3, "x": 1.0, "y": 1.0, "z": 0.0},
        {"id": 4, "x": 0.0, "y": 1.0, "z": 0.0},
        {"id": 5, "x": 2.0, "y": 0.0, "z": 0.0},
        {"id": 6, "x": -5.0, "y": 0.0, "z": 0.0},
        {"id": 7, "x": -4.0, "y": 0.0, "z": 0.0},
        {"id": 8, "x": -5.0, "y": 1.0, "z": 0.0},
        {"id": 9, "x": -5.0, "y": 0.0, "z": 1.0},
    ]
    p = {
        "output_dir": tmp_path / "job",
        "job_name": "sh",
        "nodes": nodes,
        "shells": [(1, 1, 2, 3, 4)],
        "sh3n": [(2, 2, 5, 3)],
        "tets": [(3, 6, 7, 8, 9)],
        "element_parts": {1: 0, 2: 0, 3: 1},
        "materials": _MATS,
        "parts": [{"part_id": 1, "role": "fixed"}],
        "model": {"law": "elastic", "shell": {"thickness_mm": 3.0, "ishell": 24, "nip": 5}},
        "barrier": {"speed_m_s": 10.0, "angle_deg": 0.0, "wall": {"point": [0, 0, 0], "normal": [1, 0, 0]}},
    }
    p.update(extra)
    return p


def _deck(tmp_path, **extra) -> str:
    return OpenRadiossAdapter().build_input(_shell_params(tmp_path, **extra)).path.read_text(encoding="utf-8")


def test_shell_and_sh3n_cards_per_part(tmp_path):
    s = _deck(tmp_path)
    assert _card(s, "/SHELL/1") == [f"{1:10d}{1:10d}{2:10d}{3:10d}{4:10d}"]
    assert _card(s, "/SH3N/1") == [f"{2:10d}{2:10d}{5:10d}{3:10d}"]
    assert "/TETRA4/2" in s and "/SHELL/2" not in s
    # parça 0 kabuk prop, parça 1 solid prop
    assert "/PROP/TYPE1/1" in s and "/PROP/TYPE14/2" in s
    assert "/PROP/TYPE14/1" not in s and "/PROP/TYPE1/2" not in s


def test_prop_type1_layout(tmp_path):
    prop = _card(_deck(tmp_path), "/PROP/TYPE1/1")
    assert prop[0] == "shell" and len(prop) == 4
    # Ishell Ismstr Ish3n Idrill Ipinch · (10 boş) P_Thick_Fail
    assert prop[1][:50] == f"{24:10d}{0:10d}{0:10d}{0:10d}{0:10d}"
    assert prop[1][50:60] == " " * 10 and len(prop[1]) == 80
    assert len(prop[2]) == 100  # Hm Hf Hr Dm Dn
    # N Istrain Thick Ashear · (10 boş) Ithick Iplas
    assert prop[3][:20] == f"{5:10d}{0:10d}"
    assert float(prop[3][20:40]) == 3.0
    assert prop[3][60:70] == " " * 10 and len(prop[3]) == 90


def test_part_thickness_overrides_model(tmp_path):
    s = _deck(tmp_path, parts=[{"part_id": 0, "thickness_mm": 1.2}, {"part_id": 1, "role": "fixed"}])
    assert float(_card(s, "/PROP/TYPE1/1")[3][20:40]) == 1.2


def test_shell_without_thickness_is_error(tmp_path):
    with pytest.raises(SolverError, match="kalınlığı verilmemiş.*#0"):
        _deck(tmp_path, model={"law": "elastic"})


def test_solid_and_shell_in_same_part_is_error(tmp_path):
    with pytest.raises(SolverError, match="aynı parçada solid ve kabuk"):
        _deck(tmp_path, element_parts={1: 0, 2: 0, 3: 0})


def test_contact_surface_card_follows_part_type(tmp_path):
    s = _deck(tmp_path, contacts=[{"type": 24, "master_part": 1, "slave_part": 0}])
    assert "/SURF/PART/1001\n" in s  # kabuk parça: düz /SURF/PART
    assert "/SURF/PART/EXT/1002\n" in s  # solid parça: dış deri
    assert "/SURF/PART/EXT/1001" not in s


@pytest.mark.parametrize(
    "raw",
    [{"nip": 2}, {"ishell": 5}, {"ish3n": 3}, {"ismstr": 11}, {"thickness_mm": 0.0}],
)
def test_invalid_shell_flags_rejected(raw):
    with pytest.raises(ValidationError):
        CrashShellParams.model_validate(raw)


def test_export_quad_and_tri_shells_from_gmsh(tmp_path):
    """Gerçek Gmsh 2D mesh: dörtgen (recombine) ve üçgen yüzeyler → /SHELL, /SH3N."""
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("sh")
        quad_face = gmsh.model.occ.addRectangle(0, 0, 0, 10, 10)
        gmsh.model.occ.addRectangle(30, 0, 0, 10, 10)
        gmsh.model.occ.synchronize()
        gmsh.model.mesh.setRecombine(2, quad_face)
        gmsh.option.setNumber("Mesh.MeshSizeMax", 5)
        gmsh.model.mesh.generate(2)
        msh = tmp_path / "sh_d2.msh"
        gmsh.write(str(msh))
    finally:
        gmsh.finalize()
    rm = gmsh_msh_to_radioss(msh)
    assert rm.shells and rm.sh3n and not rm.tets
    # iki ayrık yüzey → iki parça; dörtgenler bir parçada, üçgenler diğerinde
    assert {rm.element_parts[e[0]] for e in rm.shells} != {rm.element_parts[e[0]] for e in rm.sh3n}
    assert set(rm.element_parts.values()) == {0, 1}


def test_coincident_node_counter(tmp_path):
    """1.13b: aynı konumda ayrı düğüm sayısı veri olarak raporlanır (düzeltilmez)."""
    from tests.test_openradioss_export import _write_msh

    # iki üçgen ortak kenarı paylaşmıyor: düğüm 2/5 ve 3/6 aynı koordinatta
    nodes = [(1, 0, 0, 0), (2, 1, 0, 0), (3, 0, 1, 0), (4, 1, 1, 0), (5, 1, 0, 0), (6, 0, 1, 0)]
    _write_msh(tmp_path / "split.msh", nodes, ["1 2 2 0 1 1 2 3", "2 2 2 0 2 5 4 6"])
    rm = gmsh_msh_to_radioss(tmp_path / "split.msh")
    assert rm.coincident_nodes == 2
    p = _shell_params(tmp_path, coincident_nodes=rm.coincident_nodes)
    s = OpenRadiossAdapter().build_input(p).path.read_text(encoding="utf-8")
    assert s.splitlines()[1] == "# coincident_nodes: 2"
