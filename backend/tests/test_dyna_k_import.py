"""1.21a — LS-DYNA keyword (.k / .dyn) okuyucu."""

from pathlib import Path

import pytest

from app.importers.dyna_k import DynaParseError, read_keyword_file


def _fx(widths: tuple[int, ...], *values: object) -> str:
    return "".join(f"{v:>{w}}" for w, v in zip(widths, values))


def _node(nid: int, x: float, y: float, z: float) -> str:
    return _fx((8, 16, 16, 16), nid, x, y, z)


def _elem(*values: int) -> str:
    return _fx((8,) * len(values), *values)


def _card(*values: object) -> str:
    return _fx((10,) * len(values), *values)


def _write(path: Path, lines: list[str]) -> Path:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


SHORT = [
    "$ yorum satırı",
    "*KEYWORD",
    "*TITLE",
    "kutu deneme",
    "*NODE",
    "$#   nid               x               y               z",
    _node(1, 0.0, 0.0, 0.0),
    _node(2, 10.0, 0.0, 0.0),
    _node(3, 10.0, 10.0, 0.0),
    _node(4, 0.0, 10.0, 0.0),
    _node(5, 0.0, 0.0, 10.0),
    _node(6, 10.0, 0.0, 10.0),
    _node(7, 10.0, 10.0, 10.0),
    _node(8, 0.0, 10.0, 10.0),
    "*ELEMENT_SHELL",
    _elem(1, 1, 1, 2, 3, 4),
    _elem(2, 1, 1, 2, 3, 3),
    "*ELEMENT_SOLID",
    _elem(10, 2, 1, 2, 3, 4, 5, 6, 7, 8),
    _elem(11, 2),
    _elem(1, 2, 3, 4, 5, 6, 7, 8),
    "*PART",
    "sac",
    _card(1, 1, 1),
    "blok",
    _card(2, 2, 1),
    "*SECTION_SHELL",
    _card(1, 16, 0.833, 5),
    _card(1.5),
    "*SECTION_SOLID",
    _card(2, 1),
    "*MAT_PIECEWISE_LINEAR_PLASTICITY",
    _card(1, 7.85e-9, 210000.0, 0.3, 250.0),
    "*CONTACT_AUTOMATIC_SINGLE_SURFACE",
    _card(0),
    "*END",
    "*NODE",
    _node(99, 1.0, 1.0, 1.0),
]


def test_short_fixed_width(tmp_path: Path) -> None:
    m = read_keyword_file(_write(tmp_path / "kutu.k", SHORT))
    assert m.title == "kutu deneme"
    assert len(m.nodes) == 8 and 99 not in m.nodes  # *END sonrası okunmaz
    assert m.nodes[7] == (10.0, 10.0, 10.0)
    assert m.shells[1] == (1, (1, 2, 3, 4))
    assert m.shells[2] == (1, (1, 2, 3, 3))  # dejenere üçgen ham kalır
    assert m.solids[10] == (2, (1, 2, 3, 4, 5, 6, 7, 8))
    assert m.solids[11] == (2, (1, 2, 3, 4, 5, 6, 7, 8))  # iki kartlı biçim
    assert m.parts[1].title == "sac" and m.parts[2].secid == 2
    sec = m.shell_sections[1]
    assert sec.elform == 16 and sec.thickness == (1.5, 1.5, 1.5, 1.5)
    assert m.solid_sections[2].elform == 1
    assert m.skipped == {"CONTACT_AUTOMATIC_SINGLE_SURFACE": 1}
    # Yalnız 1. kart yazılmış *MAT_024: kalan kartlar varsayılan.
    mat = m.mats_024[1]
    assert (mat.ro, mat.e, mat.sigy, mat.lcss, mat.fail) == (7.85e-9, 210000.0, 250.0, 0, 1.0e21)
    assert m.warnings == []
    assert m.summary()["nodes"] == 8


def test_free_format_and_dyn_suffix(tmp_path: Path) -> None:
    lines = [
        "*KEYWORD",
        "*NODE",
        "1, 0.0, 0.0, 0.0",
        "2,1.0d1,0,0",
        "3, 10, 10, 0",
        "*ELEMENT_SHELL",
        "5, 7, 1, 2, 3, 3",
        "*PART",
        "",
        "7,3,4",
        "*SECTION_SHELL_TITLE",
        "kabuk kesit",
        "3,2",
        "2.0,2.0,2.0,2.0",
        "*END",
    ]
    m = read_keyword_file(_write(tmp_path / "model.dyn", lines))
    assert m.nodes[2] == (10.0, 0.0, 0.0)
    assert m.shells[5] == (7, (1, 2, 3, 3))
    assert m.parts[7].title == "" and m.parts[7].mid == 4
    assert m.shell_sections[3].thickness == (2.0, 2.0, 2.0, 2.0)
    assert m.warnings == []


def test_long_format(tmp_path: Path) -> None:
    w = (20, 20, 20, 20)
    lines = [
        "*KEYWORD LONG=Y",
        "*NODE",
        _fx(w, 1, 0.0, 0.0, 0.0),
        _fx(w, 2, 1.25, 0.0, 0.0),
        _fx(w, 3, 1.25, 2.5, 0.0),
        "*ELEMENT_SHELL",
        _fx((20,) * 6, 100000001, 1, 1, 2, 3, 3),
        "*END",
    ]
    m = read_keyword_file(_write(tmp_path / "uzun.k", lines))
    assert m.nodes[3] == (1.25, 2.5, 0.0)
    assert m.shells[100000001] == (1, (1, 2, 3, 3))


def test_long_format_plus_suffix(tmp_path: Path) -> None:
    lines = ["*NODE +", _fx((20,) * 4, 5, 1.0, 2.0, 3.0), "*END"]
    m = read_keyword_file(_write(tmp_path / "arti.k", lines))
    assert m.nodes[5] == (1.0, 2.0, 3.0)


def test_include_inside_and_outside(tmp_path: Path) -> None:
    root = tmp_path / "model"
    (root / "inc").mkdir(parents=True)
    _write(root / "inc" / "mesh.k", ["*NODE", _node(1, 0.0, 0.0, 0.0), "*END"])
    _write(tmp_path / "disari.k", ["*NODE", _node(2, 0.0, 0.0, 0.0)])
    main = _write(
        root / "ana.k",
        ["*KEYWORD", "*INCLUDE", "inc/mesh.k", "*INCLUDE", "../disari.k",
         "*INCLUDE", "yok.k", "*NODE", _node(3, 1.0, 0.0, 0.0), "*END"],
    )
    m = read_keyword_file(main)
    assert sorted(m.nodes) == [1, 3]
    assert m.files == ["ana.k", "inc/mesh.k"]
    assert any("ana klasör dışında" in w for w in m.warnings)
    assert any("bulunamadı" in w for w in m.warnings)


def test_include_cycle(tmp_path: Path) -> None:
    _write(tmp_path / "b.k", ["*INCLUDE", "a.k", "*NODE", _node(2, 0.0, 0.0, 0.0)])
    main = _write(tmp_path / "a.k", ["*INCLUDE", "b.k", "*NODE", _node(1, 0.0, 0.0, 0.0)])
    m = read_keyword_file(main)
    assert sorted(m.nodes) == [1, 2]
    assert any("döngüsel" in w for w in m.warnings)


def test_reference_warnings(tmp_path: Path) -> None:
    lines = ["*NODE", _node(1, 0.0, 0.0, 0.0), "*ELEMENT_SHELL", _elem(1, 9, 1, 2, 3, 4)]
    m = read_keyword_file(_write(tmp_path / "eksik.k", lines))
    assert any("part'ı tanımsız: [9]" in w for w in m.warnings)
    assert any("tanımsız düğüm (3)" in w for w in m.warnings)


def test_duplicate_node_is_error(tmp_path: Path) -> None:
    lines = ["*NODE", _node(1, 0.0, 0.0, 0.0), _node(1, 1.0, 0.0, 0.0)]
    with pytest.raises(DynaParseError, match=r"ikili.k:3: düğüm 1 ikinci kez"):
        read_keyword_file(_write(tmp_path / "ikili.k", lines))


def test_bad_number_reports_location(tmp_path: Path) -> None:
    lines = ["*NODE", _node(1, 0.0, 0.0, 0.0), "       2         abc"]
    with pytest.raises(DynaParseError, match=r"bozuk.k:3: sayı beklendi"):
        read_keyword_file(_write(tmp_path / "bozuk.k", lines))


def test_unsupported_suffix(tmp_path: Path) -> None:
    with pytest.raises(DynaParseError, match="desteklenen uzantılar"):
        read_keyword_file(_write(tmp_path / "model.inp", ["*NODE"]))
