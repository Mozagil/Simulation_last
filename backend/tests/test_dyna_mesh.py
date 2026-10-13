"""1.21b — LS-DYNA ara modeli → crash mesh parametreleri → Radioss deck."""

from pathlib import Path

import pytest

from app.importers.dyna_k import read_keyword_file
from app.importers.dyna_mesh import DynaMeshError, to_crash_mesh
from app.solvers.openradioss import OpenRadiossAdapter

# Birim: metre (çarpan 1000 → mm). PID 5 kabuk, PID 9 solid.
DECK = """*KEYWORD
*NODE
1, 0.0, 0.0, 0.0
2, 0.01, 0.0, 0.0
3, 0.01, 0.01, 0.0
4, 0.0, 0.01, 0.0
11, 0.0, 0.0, 0.1
12, 0.01, 0.0, 0.1
13, 0.01, 0.01, 0.1
14, 0.0, 0.01, 0.1
15, 0.0, 0.0, 0.11
16, 0.01, 0.0, 0.11
17, 0.01, 0.01, 0.11
18, 0.0, 0.01, 0.11
99, 5.0, 5.0, 5.0
*ELEMENT_SHELL
1, 5, 1, 2, 3, 4
2, 5, 1, 3, 4, 4
*ELEMENT_SOLID
10, 9, 11, 12, 13, 14, 15, 16, 17, 18
11, 9, 11, 12, 13, 15, 15, 15, 15, 15
12, 9, 11, 12, 13, 13, 15, 16, 17, 17
*PART
kapak
5, 1, 1
blok
9, 2, 1
bos
20, 1, 1
*SECTION_SHELL
1, 16
0.0015, 0.0015, 0.0015, 0.0015
*SECTION_SOLID
2, 1
*END
"""


def _model(tmp_path: Path):
    p = tmp_path / "parca.k"
    p.write_text(DECK, encoding="utf-8")
    return read_keyword_file(p)


def test_element_split_parts_and_units(tmp_path: Path) -> None:
    mesh = to_crash_mesh(_model(tmp_path), length_to_mm=1000.0)
    assert mesh.shells == [(1, 1, 2, 3, 4)]
    assert mesh.sh3n == [(2, 1, 3, 4)]
    assert mesh.tets == [(11, 11, 12, 13, 15)]
    assert [b[0] for b in mesh.bricks] == [10, 12]
    assert mesh.degenerate_bricks == 1
    assert dict((n[0], n[1:]) for n in mesh.nodes)[13] == pytest.approx((10.0, 10.0, 100.0))
    assert 99 not in {n[0] for n in mesh.nodes}  # elemansız düğüm alınmaz
    assert mesh.element_parts[1] == 4 and mesh.element_parts[10] == 8
    shell, solid = mesh.parts
    assert (shell.pid, shell.kind, shell.elform, shell.elements) == (5, "shell", 16, 2)
    assert shell.thickness_mm == pytest.approx(1.5)
    assert (solid.pid, solid.kind, solid.thickness_mm, solid.elements) == (9, "solid", None, 3)
    assert any("Elemanı olmayan part(lar) alınmadı: [20]" in w for w in mesh.warnings)
    assert any("1 düğüm alınmadı" in w for w in mesh.warnings)


def test_adapter_writes_radioss_cards_with_file_pids(tmp_path: Path) -> None:
    mesh = to_crash_mesh(_model(tmp_path), length_to_mm=1000.0)
    params = mesh.adapter_params()
    params.update(
        {
            "output_dir": tmp_path / "job",
            "job_name": "dyna",
            "materials": [
                {"part_id": p.part_id, "name": "S235", "density": 7850.0,
                 "youngs_modulus": 210e9, "poisson_ratio": 0.3}
                for p in mesh.parts
            ],
            "barrier": {"speed_m_s": 10.0, "angle_deg": 0.0,
                        "wall": {"point": [0, 0, -1], "normal": [0, 0, 1]}},
        }
    )
    deck = OpenRadiossAdapter().build_input(params).path.read_text(encoding="utf-8")
    for card in ("/SHELL/5", "/SH3N/5", "/BRICK/9", "/TETRA4/9", "/PART/5", "/PART/9"):
        assert card in deck, card
    assert "/PART/21" not in deck
    assert f"{13:10d}{10.0:20.8g}{10.0:20.8g}{100.0:20.8g}" in deck


def test_unit_factor_required(tmp_path: Path) -> None:
    with pytest.raises(DynaMeshError, match="Uzunluk çarpanı"):
        to_crash_mesh(_model(tmp_path), length_to_mm=0.0)


def test_mixed_part_and_missing_node_are_errors(tmp_path: Path) -> None:
    model = _model(tmp_path)
    model.solids[30] = (5, (11, 12, 13, 14, 15, 16, 17, 18))
    with pytest.raises(DynaMeshError, match="Aynı part'ta kabuk ve solid"):
        to_crash_mesh(model, length_to_mm=1.0)
    model = _model(tmp_path)
    model.shells[3] = (5, (1, 2, 3, 777))
    with pytest.raises(DynaMeshError, match=r"tanımsız düğüm \(1\): \[777\]"):
        to_crash_mesh(model, length_to_mm=1.0)
