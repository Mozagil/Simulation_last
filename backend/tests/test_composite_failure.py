"""Faz 3.12 — Tsai-Wu + Hashin IRF; deste dayanım yorumu; ccx uçtan uca.

Ölçüt testleri her zaman koşar; ccx koşusu (V-P1 düzeni, [30/0/90/−45]s, Nx)
ccx yoksa atlanır.
"""

from __future__ import annotations

import json
import subprocess

import numpy as np
import pytest

from app.composite.assemble import assemble_composite_layup
from app.composite.failure import Strength, hashin_irf, strength_from_material, tsai_wu_irf
from app.composite.layup import Ply, abd_matrix
from app.composite.ply_stress import parse_composite_deck
from app.composite.reference import midplane_response, ply_stresses
from app.composite.section_writer import write_composite_section
from app.solvers.base import InputArtifact, JobHandle
from app.solvers.calculix import CalculiXAdapter, _ccx_executable, _ccx_run_env
from scripts.composite_validation_vp1 import PLY_T_MM, T300, Case, build_deck

requires_ccx = pytest.mark.skipif(_ccx_executable() is None, reason="ccx yok")

# Seed T300/epoxy dayanımları (Pa) — tipik, mill test değil
_T300_STRENGTH_PA = {"xt": 1500e6, "xc": 1200e6, "yt": 50e6, "yc": 200e6, "s12": 70e6, "s23": 40e6}
ST = Strength(1500.0, 1200.0, 50.0, 200.0, 70.0, 40.0)


@pytest.mark.parametrize(
    "s1, s2, t12, mode",
    [
        (1500.0, 0.0, 0.0, 0),
        (-1200.0, 0.0, 0.0, 1),
        (0.0, 50.0, 0.0, 2),
        (0.0, -200.0, 0.0, 3),
        (0.0, 0.0, 70.0, None),
    ],
)
def test_irf_is_one_at_uniaxial_strength(s1, s2, t12, mode):
    a = np.array([s1])
    b = np.array([s2])
    c = np.array([t12])
    assert tsai_wu_irf(a, b, c, ST)[0] == pytest.approx(1.0)
    h = hashin_irf(a, b, c, ST)[0]
    assert h.max() == pytest.approx(1.0)
    if mode is not None:
        assert int(h.argmax()) == mode


def test_irf_scales_linearly_with_load():
    s = (np.array([400.0]), np.array([-30.0]), np.array([25.0]))
    for k in (0.5, 2.0):
        scaled = tuple(k * x for x in s)
        assert tsai_wu_irf(*scaled, ST)[0] == pytest.approx(k * tsai_wu_irf(*s, ST)[0])
        assert hashin_irf(*scaled, ST)[0].max() == pytest.approx(k * hashin_irf(*s, ST)[0].max())


def test_hashin_modes_exclusive_and_s23_fallback():
    h = hashin_irf(np.array([100.0]), np.array([-20.0]), np.array([0.0]), ST)[0]
    assert h[0] > 0 and h[1] == 0 and h[2] == 0 and h[3] > 0
    no_s23 = Strength(1500.0, 1200.0, 50.0, 200.0, 70.0)
    mc = hashin_irf(np.array([0.0]), np.array([-100.0]), np.array([0.0]), no_s23)[0][3]
    assert mc == pytest.approx(0.5)  # (σ2/Yc)² biçimi


def test_strength_validation_and_units():
    with pytest.raises(ValueError, match="xt"):
        Strength(0.0, 1.0, 1.0, 1.0, 1.0)
    st = strength_from_material(_T300_STRENGTH_PA)
    assert st == ST
    assert strength_from_material({**_T300_STRENGTH_PA, "s23": None}).s23 is None


def test_strengths_flow_assemble_to_deck():
    spec = assemble_composite_layup(
        part_id=2,
        plies=[
            {"material_id": 1, "thickness_mm": 0.25, "angle_deg": 30},
            {"material_id": 1, "thickness_mm": 0.25, "angle_deg": -45},
        ],
        materials={1: {**T300, "name": "T300/epoxy", **_T300_STRENGTH_PA}},
    )
    deck = write_composite_section(spec)
    assert "** PLY_STRENGTH_MPA, NAME=T300_epoxy, 1500, 1200, 50, 200, 70, 40" in deck
    sets, strengths = parse_composite_deck(deck)
    assert strengths == {"T300_EPOXY": [1500.0, 1200.0, 50.0, 200.0, 70.0, 40.0]}
    assert [(p.material, p.angle_deg) for p in sets["PART_2"]] == [
        ("T300_EPOXY", 30.0),
        ("T300_EPOXY", -45.0),
    ]
    # Dayanım yoksa yorum yazılmaz (eski layup'lar)
    bare = write_composite_section({"plies": [{**T300, "thickness_mm": 0.25, "angle_deg": 0}]})
    assert "PLY_STRENGTH" not in bare


_ANGLES = (30.0, 0.0, 90.0, -45.0, -45.0, 90.0, 0.0, 30.0)
_NX = 100.0  # N/mm


@requires_ccx
def test_ccx_irf_matches_clt(tmp_path, monkeypatch):
    import scripts.composite_validation_vp1 as vp1

    monkeypatch.setattr(vp1, "T300", {**T300, **_T300_STRENGTH_PA})
    case = Case("f", _ANGLES, 200.0, 50.0, 20, 6, "nx", _NX)
    deck, _ = build_deck(case)
    deck = deck.replace(
        "*END STEP", "*EL PRINT, ELSET=PLATE\nS\n*NODE FILE\nU\n*EL FILE\nS\n*END STEP"
    )
    inp = tmp_path / "fail.inp"
    inp.write_text(deck, encoding="utf-8")
    ccx = _ccx_executable()
    proc = subprocess.run(
        [ccx, "fail"], cwd=tmp_path, env=_ccx_run_env(ccx), capture_output=True, text=True
    )
    assert (tmp_path / "fail.dat").exists(), proc.stdout[-1500:]

    rs = CalculiXAdapter().parse_results(
        JobHandle(job_id="f", work_dir=tmp_path, artifact=InputArtifact(path=inp))
    )
    sc = rs.scalars

    plies = [Ply(T300["e1"], T300["e2"], T300["g12"], T300["nu12"], PLY_T_MM, a) for a in _ANGLES]
    eps = midplane_response(abd_matrix(plies), n=(_NX, 0.0, 0.0))
    ref = np.array(ply_stresses(plies, eps["eps0"], eps["kappa"]))
    tw_ref = tsai_wu_irf(ref[:, 0], ref[:, 1], ref[:, 2], ST)
    hs_ref = hashin_irf(ref[:, 0], ref[:, 1], ref[:, 2], ST).max(axis=1)

    # En büyük değer tüm IP'lerden: serbest kenar / yük girişi bölgesi CLT'nin
    # üstüne çıkar (ölçülen Tsai-Wu +%7) → alt sınır CLT, üst bant %15.
    assert tw_ref.max() * 0.99 <= sc["tsai_wu_irf_max"] <= tw_ref.max() * 1.15
    assert hs_ref.max() * 0.99 <= sc["hashin_irf_max"] <= hs_ref.max() * 1.15
    assert sc["hashin_mc_s23"] == 1.0
    # En kritik katman CLT ile aynı açıda (simetri: k ya da 9−k)
    assert int(sc["tsai_wu_ply"]) - 1 in {int(np.argmax(tw_ref)), 7 - int(np.argmax(tw_ref))}

    field = json.loads((tmp_path / "fail_ply.json").read_text(encoding="utf-8"))
    plate = field["sets"]["PLATE"]
    assert len(plate["element_ids"]) == 120
    assert len(plate["tsai_wu_irf"][0]) == 8
    assert [p["angle_deg"] for p in plate["plies"]] == list(_ANGLES)
    # Orta sıra elemanlarında katman IRF'i CLT'ye %2 yakın
    mid = [i for i in range(120) if (i // 20) in (2, 3)]
    tw_mid = np.array([plate["tsai_wu_irf"][i] for i in mid]).mean(axis=0)
    np.testing.assert_allclose(tw_mid, tw_ref, rtol=0.02)
