"""1.21c — *MAT_024 (+ *DEFINE_CURVE) → LAW36 / LAW2; *MAT_001 → LAW1;
*MAT_020 → /RBODY + kısıt."""

from pathlib import Path

import pytest

from app.importers.dyna_k import read_keyword_file
from app.importers.dyna_material import DynaMaterialError, DynaUnits, to_crash_materials
from app.importers.dyna_mesh import to_crash_mesh
from app.solvers.openradioss import OpenRadiossAdapter

# mm–t–s: gerilme MPa, yoğunluk t/mm³. Altı kabuk part, altı MID.
DECK = """*KEYWORD
*NODE
1, 0.0, 0.0, 0.0
2, 10.0, 0.0, 0.0
3, 10.0, 10.0, 0.0
4, 0.0, 10.0, 0.0
*ELEMENT_SHELL
1, 1, 1, 2, 3, 4
2, 2, 1, 2, 3, 4
3, 3, 1, 2, 3, 4
4, 4, 1, 2, 3, 4
5, 5, 1, 2, 3, 4
6, 6, 1, 2, 3, 4
*PART
egri
1, 1, 10
bilineer
2, 1, 20
noktali
3, 1, 30
rijit
4, 1, 40
elastik
5, 1, 50
kinematik
6, 1, 60
*SECTION_SHELL
1, 2
1.2
*MAT_PIECEWISE_LINEAR_PLASTICITY_TITLE
DP600
10, 7.85e-9, 210000.0, 0.3, 0.0, 0.0, 0.25
40.0, 5.0, 100
0, 0, 0, 0, 0, 0, 0, 0
0, 0, 0, 0, 0, 0, 0, 0
*DEFINE_CURVE
100, 0, 0.0, 2.0
0.0, 175.0
0.1, 250.0
0.5, 300.0
*MAT_024
20, 7.85e-9, 210000.0, 0.3, 235.0, 1000.0
*MAT_024
30, 2.7e-9, 70000.0, 0.33
0, 0, 0, 0
0.0, 0.05, 0.2
150.0, 200.0, 240.0
*MAT_RIGID
40, 7.85e-9, 210000.0, 0.3
1.0, 7.0, 4.0
0
*MAT_ELASTIC_TITLE
cam
50, 2.5e-9, 70000.0, 0.22
*MAT_003
60, 7.85e-9, 210000.0, 0.3, 300.0
*END
"""

MM_T_S = DynaUnits(length_to_mm=1.0, mass_to_kg=1000.0, time_to_s=1.0)


def _setup(tmp_path: Path):
    p = tmp_path / "malzeme.k"
    p.write_text(DECK, encoding="utf-8")
    model = read_keyword_file(p)
    mesh = to_crash_mesh(model, length_to_mm=MM_T_S.length_to_mm)
    return model, mesh


def test_unit_factors() -> None:
    assert MM_T_S.stress_to_pa == pytest.approx(1e6)
    assert MM_T_S.density_to_kgm3 * 7.85e-9 == pytest.approx(7850.0)
    mm_kg_ms = DynaUnits(1.0, 1.0, 1e-3)
    assert mm_kg_ms.stress_to_pa == pytest.approx(1e9)
    with pytest.raises(DynaMaterialError):
        DynaUnits(1.0, 0.0, 1.0)


def test_mat024_mapping(tmp_path: Path) -> None:
    model, mesh = _setup(tmp_path)
    m = to_crash_materials(model, mesh, MM_T_S)
    curve = m.part_models[0]
    assert curve["law"] == "tabulated" and curve["eps_p_max"] == 0.25
    # SFO = 2 uygulanmış, MPa
    assert curve["tab_curves"][0]["points"] == [(0.0, 350.0), (0.1, 500.0), (0.5, 600.0)]
    bil = m.part_models[1]
    assert bil["law"] == "plastic" and "eps_p_max" not in bil  # FAIL varsayılan → kopma yok
    assert bil["sigma_y_pa"] == pytest.approx(235e6)
    assert bil["harden_b_mpa"] == pytest.approx(210000.0 * 1000.0 / 209000.0)
    pts = m.part_models[2]["tab_curves"][0]["points"]
    assert pts == [(0.0, 150.0), (0.05, 200.0), (0.2, 240.0)]
    mats = {x["part_id"]: x for x in m.materials}
    assert mats[0]["name"] == "DP600"
    assert mats[0]["density"] == pytest.approx(7850.0)
    assert mats[0]["youngs_modulus"] == pytest.approx(210e9)
    assert mats[2]["name"] == "MAT_024_30"
    assert m.unassigned == [6]
    rows = {r["pid"]: r for r in m.parts}
    assert rows[6]["note"] == "*MAT_003 çevrilmedi"
    assert rows[1]["note"] == "LCSS eğri 100 (3 nokta)"
    # *MAT_001 → LAW1
    assert m.part_models[4] == {"law": "elastic"}
    assert mats[4]["name"] == "cam" and mats[4]["density"] == pytest.approx(2500.0)
    # *MAT_020 → /RBODY (part seçimi) + CMO=1 kısıtı: CON1=7 (xyz), CON2=4 (x+y)
    assert m.part_models[3] == {"law": "elastic"}
    assert mats[3]["name"] == "MAT_RIGID_40"
    assert m.rigid_bodies == [{"name": "rigid_part_4", "part_id": 3}]
    assert m.boundary_conditions == [
        {"name": "rigid_part_4_con", "rigid_body": "rigid_part_4", "dofs": "111110"}
    ]
    assert any("Cowper–Symonds C=40, P=5" in w for w in m.warnings)


def test_missing_curve_is_unassigned(tmp_path: Path) -> None:
    model, mesh = _setup(tmp_path)
    del model.curves[100]
    m = to_crash_materials(model, mesh, MM_T_S)
    assert 1 in m.unassigned
    assert "tablo desteklenmiyor" in {r["pid"]: r for r in m.parts}[1]["note"]


def test_adapter_writes_law36_and_law2(tmp_path: Path) -> None:
    model, mesh = _setup(tmp_path)
    params = mesh.adapter_params()
    to_crash_materials(model, mesh, MM_T_S).apply(params)
    # Çevrilmeyen part 6'ya (*MAT_003) malzemeyi mühendis atar.
    params["materials"].append(
        {"part_id": 5, "name": "elle", "density": 7850.0, "youngs_modulus": 210e9, "poisson_ratio": 0.3}
    )
    params.update(
        {
            "output_dir": tmp_path / "job",
            "job_name": "mat",
            "barrier": {"speed_m_s": 10.0, "angle_deg": 0.0,
                        "wall": {"point": [0, 0, -1], "normal": [0, 0, 1]}},
        }
    )
    deck = OpenRadiossAdapter().build_input(params).path.read_text(encoding="utf-8")
    for card in ("/MAT/LAW36/1", "/MAT/LAW2/2", "/MAT/LAW36/3", "/MAT/LAW1/4",
                 "/MAT/LAW1/5", "/MAT/LAW1/6", "/FUNCT/101", "/RBODY/"):
        assert card in deck, card
    assert "   111 110" in deck  # rijit gövde ana düğümüne kısıt
    assert f"{0.1:20.8g}{0.5:20.8g}" in deck  # eğri noktası, σ GPa


def test_cowper_symonds_rates_to_law36_curves(tmp_path: Path) -> None:
    model, mesh = _setup(tmp_path)
    m = to_crash_materials(model, mesh, MM_T_S, rates_per_s=[100.0, 10.0])
    curves = m.part_models[0]["tab_curves"]
    assert [c["eps_dot_per_s"] for c in curves] == [0.0, 10.0, 100.0]
    k10 = 1.0 + (10.0 / 40.0) ** (1.0 / 5.0)
    assert curves[1]["points"][0] == pytest.approx((0.0, 350.0 * k10))
    assert m.part_models[0]["tab_vp"] == 0
    assert not any("Cowper" in w for w in m.warnings)
    assert "Cowper–Symonds C=40 1/s, P=5; 3 eğri" in {r["pid"]: r for r in m.parts}[1]["note"]
    # Hız etkisi olmayan malzeme değişmez.
    assert m.part_models[1]["law"] == "plastic"


def test_lcsr_rates_on_bilinear(tmp_path: Path) -> None:
    from app.importers.dyna_k import DynaCurve

    model, mesh = _setup(tmp_path)
    model.mats_024[20].lcsr = 101
    model.curves[101] = DynaCurve(lcid=101, title="", points=[(0.0, 1.0), (100.0, 1.5)])
    m = to_crash_materials(model, mesh, MM_T_S, rates_per_s=[10.0, 200.0])
    bil = m.part_models[1]
    assert bil["law"] == "tabulated" and "sigma_y_pa" not in bil
    b = 210000.0 * 1000.0 / 209000.0
    static, r10, r200 = bil["tab_curves"]
    assert static["points"] == pytest.approx([(0.0, 235.0), (1.0, 235.0 + b)])
    assert r10["points"][0][1] == pytest.approx(235.0 * 1.05)
    assert r200["points"][0][1] == pytest.approx(235.0 * 2.0)  # doğrusal uzatma


def test_rates_must_be_positive(tmp_path: Path) -> None:
    model, mesh = _setup(tmp_path)
    with pytest.raises(DynaMaterialError, match="pozitif"):
        to_crash_materials(model, mesh, MM_T_S, rates_per_s=[0.0])


def test_rate_curves_reach_deck(tmp_path: Path) -> None:
    model, mesh = _setup(tmp_path)
    params = mesh.adapter_params()
    to_crash_materials(model, mesh, MM_T_S, rates_per_s=[10.0, 100.0]).apply(params)
    params["materials"].append(
        {"part_id": 5, "name": "elle", "density": 7850.0, "youngs_modulus": 210e9, "poisson_ratio": 0.3}
    )
    params.update({"output_dir": tmp_path / "job", "job_name": "hiz",
                   "barrier": {"speed_m_s": 10.0, "angle_deg": 0.0,
                               "wall": {"point": [0, 0, -1], "normal": [0, 0, 1]}}})
    deck = OpenRadiossAdapter().build_input(params).path.read_text(encoding="utf-8")
    assert "/FUNCT/103" in deck  # part 1: 3 eğri
    assert f"{0.0:20.8g}{0.01:20.8g}{0.1:20.8g}" in deck  # ε̇ 1/ms
