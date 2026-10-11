"""1.21d — LS-DYNA temas / SPC / ilk hız / duvar / yerçekimi → crash kurulumu."""

from pathlib import Path

import pytest

from app.importers.dyna_k import read_keyword_file
from app.importers.dyna_material import DynaUnits, to_crash_materials
from app.importers.dyna_mesh import to_crash_mesh
from app.importers.dyna_setup import to_crash_setup
from app.solvers.openradioss import OpenRadiossAdapter

# m–kg–s. PID 1 plaka (z = 0), PID 2 kutu kapağı (z = 0.05).
BASE = """*KEYWORD
*NODE
1, 0.0, 0.0, 0.0
2, 0.1, 0.0, 0.0
3, 0.1, 0.1, 0.0
4, 0.0, 0.1, 0.0
5, 0.0, 0.0, 0.05
6, 0.1, 0.0, 0.05
7, 0.1, 0.1, 0.05
8, 0.0, 0.1, 0.05
*ELEMENT_SHELL
1, 1, 1, 2, 3, 4
2, 2, 5, 6, 7, 8
*PART
plaka
1, 1, 1
kapak
2, 1, 1
*SECTION_SHELL
1, 2
0.001
*MAT_024
1, 7850.0, 2.1e11, 0.3, 2.35e8, 1.0e9
"""

SETUP = """*SET_PART_LIST
100
1, 2
*SET_NODE_LIST_TITLE
kenar
200
1, 2
*CONTACT_AUTOMATIC_NODES_TO_SURFACE
2, 1, 3, 3
0.2
*CONTACT_AUTOMATIC_SURFACE_TO_SURFACE_ID
1 temas
100, 1, 2, 3
0.1, 0.05
*CONTACT_AUTOMATIC_SINGLE_SURFACE
2, 0, 3
*CONTACT_AUTOMATIC_SINGLE_SURFACE
0, 0, 0
*CONTACT_NODES_TO_SURFACE
200, 1, 4, 3
*BOUNDARY_SPC_SET
200, 0, 1, 1, 1, 0, 0, 0
*BOUNDARY_SPC_NODE
3, 0, 1, 1, 1, 1, 1, 1
4, 0, 1, 1, 1, 1, 1, 1
4, 5, 1, 0, 0, 0, 0, 0
*INITIAL_VELOCITY_GENERATION
2, 2, 0.0, 0.0, 0.0, -10.0

*INITIAL_VELOCITY_NODE
5, 1.0, 0.0, 0.0
6, 1.0, 0.0, 0.0
*RIGIDWALL_PLANAR
0
0.0, 0.0, -0.01, 0.0, 0.0, 1.0
*LOAD_BODY_Z
7, 1.0
*DEFINE_CURVE
7
0.0, 9.81
1.0, 9.81
*CONTROL_TERMINATION
0.01
*END
"""

M_KG_S = DynaUnits(length_to_mm=1000.0, mass_to_kg=1.0, time_to_s=1.0)


def _load(tmp_path: Path, text: str):
    p = tmp_path / "kurulum.k"
    p.write_text(text, encoding="utf-8")
    model = read_keyword_file(p)
    mesh = to_crash_mesh(model, length_to_mm=M_KG_S.length_to_mm)
    return model, mesh


def _rows(setup, source: str) -> list[dict]:
    return [r for r in setup.rows if r["source"] == source]


def test_contacts(tmp_path: Path) -> None:
    model, mesh = _load(tmp_path, BASE + SETUP)
    s = to_crash_setup(model, mesh, M_KG_S)
    assert s.contacts == [
        {"type": 7, "slave_part": 1, "master_part": 0, "fric": 0.2},
        {"type": 24, "slave_part": 0, "master_part": 0, "fric": 0.1},
        {"type": 24, "slave_part": 1, "master_part": 0, "fric": 0.1},
        {"type": 7, "slave_part": 1, "master_part": 1, "fric": 0.0},
    ]
    singles = _rows(s, "*CONTACT_AUTOMATIC_SINGLE_SURFACE")
    assert [r["status"] for r in singles] == ["çevrildi", "atlandı"]
    assert "çok part'lı" in singles[1]["detail"]
    (n2s,) = _rows(s, "*CONTACT_NODES_TO_SURFACE")
    assert n2s["status"] == "atlandı" and "SSTYP/MSTYP 4" in n2s["detail"]
    assert any("FD=0.05" in w for w in s.warnings)


def test_spc_velocity_wall_gravity_end_time(tmp_path: Path) -> None:
    model, mesh = _load(tmp_path, BASE + SETUP)
    s = to_crash_setup(model, mesh, M_KG_S)
    bcs = {b["dofs"]: s.region_nodes[b["region"]] for b in s.boundary_conditions}
    assert bcs == {"111000": [1, 2], "111111": [3, 4]}
    (cid_row,) = [r for r in _rows(s, "*BOUNDARY_SPC_NODE") if r["status"] == "atlandı"]
    assert "CID 5" in cid_row["detail"]
    part_v, node_v = s.initial_velocities
    assert part_v["part_id"] == 1 and part_v["speed_m_s"] == pytest.approx(10.0)
    assert part_v["direction"] == pytest.approx((0.0, 0.0, -1.0))
    assert s.region_nodes[node_v["region"]] == [5, 6]
    assert node_v["speed_m_s"] == pytest.approx(1.0)
    assert s.rigid_wall["point"] == pytest.approx([0.0, 0.0, -10.0])
    assert s.rigid_wall["normal"] == pytest.approx([0.0, 0.0, 1.01])
    assert s.gravity == {"accel_m_s2": pytest.approx(-9.81), "direction": "Z"}
    assert s.t_end_ms == pytest.approx(10.0)


def test_full_deck(tmp_path: Path) -> None:
    model, mesh = _load(tmp_path, BASE + SETUP)
    params = mesh.adapter_params()
    to_crash_materials(model, mesh, M_KG_S).apply(params)
    to_crash_setup(model, mesh, M_KG_S).apply(params)
    params.update({"output_dir": tmp_path / "job", "job_name": "kur"})
    deck = OpenRadiossAdapter().build_input(params).path.read_text(encoding="utf-8")
    for card in ("/INTER/TYPE7/", "/INTER/TYPE24/", "/BCS/", "/GRAV/", "/RWALL/PLANE/1"):
        assert card in deck, card
    # Bariyer hızı sıfır; ilk hız yalnız dosyadan (kart tabanlı /INIVEL).
    assert "impact_vel\n" not in deck
    assert f"{0.0:20.8g}{0.0:20.8g}{-10.0:20.8g}" in deck


def test_no_wall_in_file_disables_default_wall(tmp_path: Path) -> None:
    model, mesh = _load(tmp_path, BASE + "*INITIAL_VELOCITY_GENERATION\n2, 2, 0.0, 0.0, 0.0, -10.0\n\n*END\n")
    params = mesh.adapter_params()
    to_crash_materials(model, mesh, M_KG_S).apply(params)
    s = to_crash_setup(model, mesh, M_KG_S)
    s.apply(params)
    assert params["use_rigid_wall"] is False and s.contacts == []
    params.update({"output_dir": tmp_path / "job", "job_name": "duvarsiz"})
    deck = OpenRadiossAdapter().build_input(params).path.read_text(encoding="utf-8")
    assert "/RWALL" not in deck
