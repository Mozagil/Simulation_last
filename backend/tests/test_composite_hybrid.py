"""Karışık malzemeli (hibrit) dizilim: karbon + cam, katman başına ayrı malzeme.

[0C / 45G / −45G / 90C]s — C: T300/epoxy, G: E-glass/epoxy. Kontroller:
- deste: her malzeme bir kez *MATERIAL + dayanım yorumu, COMPOSITE satırları
  doğru katmana doğru malzemeyi bağlar;
- CLT: A11 elle kapalı biçim (Q̄11(±45) = (Q11 + Q22 + 2 Q12 + 4 Q66) / 4),
  simetrik → B = 0, dengeli → A16 = A26 = 0;
- ccx (yoksa atlanır): katman gerilmesi ve IRF CLT ile, her katman kendi
  malzemesinin dayanımıyla.
"""

from __future__ import annotations

import json
import subprocess

import numpy as np
import pytest

from app.composite.assemble import assemble_composite_layup
from app.composite.failure import hashin_irf, strength_from_material, tsai_wu_irf
from app.composite.layup import Ply, abd_matrix, reduced_stiffness
from app.composite.ply_stress import parse_composite_deck
from app.composite.reference import midplane_response, ply_stresses
from app.composite.section_writer import write_composite_section
from app.solvers.base import InputArtifact, JobHandle
from app.solvers.calculix import CalculiXAdapter, _ccx_executable, _ccx_run_env

requires_ccx = pytest.mark.skipif(_ccx_executable() is None, reason="ccx yok")

CARBON = {
    "name": "T300/epoxy",
    "e1": 135e9, "e2": 10e9, "e3": 10e9, "nu12": 0.3, "nu13": 0.3, "nu23": 0.45,
    "g12": 5.2e9, "g13": 5.2e9, "g23": 3.4e9, "density": 1600.0,
    "xt": 1500e6, "xc": 1200e6, "yt": 50e6, "yc": 200e6, "s12": 70e6, "s23": 40e6,
}
# Tipik E-cam/epoksi (ders kitabı mertebesi, mill test değil)
GLASS = {
    "name": "E-glass/epoxy",
    "e1": 39e9, "e2": 8.6e9, "e3": 8.6e9, "nu12": 0.28, "nu13": 0.28, "nu23": 0.4,
    "g12": 3.8e9, "g13": 3.8e9, "g23": 3.0e9, "density": 2100.0,
    "xt": 1080e6, "xc": 620e6, "yt": 39e6, "yc": 128e6, "s12": 89e6, "s23": 30e6,
}
T_MM = 0.25
# (malzeme id, açı) alt → üst; 1 = karbon, 2 = cam
STACK = ((1, 0.0), (2, 45.0), (2, -45.0), (1, 90.0), (1, 90.0), (2, -45.0), (2, 45.0), (1, 0.0))
_MATS = {1: CARBON, 2: GLASS}
_NX = 100.0  # N/mm


def _spec(elset: str | None = None) -> dict:
    spec = assemble_composite_layup(
        part_id=0,
        plies=[{"material_id": m, "thickness_mm": T_MM, "angle_deg": a} for m, a in STACK],
        materials=_MATS,
    )
    if elset:
        spec["elset"] = elset
    return spec


def _clt_plies() -> list[Ply]:
    return [
        Ply(_MATS[m]["e1"], _MATS[m]["e2"], _MATS[m]["g12"], _MATS[m]["nu12"], T_MM, a)
        for m, a in STACK
    ]


def test_deck_binds_each_ply_to_its_material():
    deck = write_composite_section(_spec())
    assert deck.count("*MATERIAL, NAME=T300_epoxy") == 1
    assert deck.count("*MATERIAL, NAME=E-glass_epoxy") == 1
    assert "** PLY_STRENGTH_MPA, NAME=T300_epoxy, 1500, 1200, 50, 200, 70, 40" in deck
    assert "1080, 620, 39, 128, 89, 30" in deck
    sets, strengths = parse_composite_deck(deck)
    got = [(p.material, p.angle_deg) for p in sets["PART_0"]]
    carbon, glass = got[0][0], got[1][0]
    assert carbon != glass
    assert got == [
        (carbon if m == 1 else glass, a) for m, a in STACK
    ]
    assert strengths[carbon][0] == 1500.0 and strengths[glass][0] == 1080.0


def test_clt_hybrid_matches_hand_formula():
    abd = abd_matrix(_clt_plies())
    qc = reduced_stiffness(CARBON["e1"], CARBON["e2"], CARBON["g12"], CARBON["nu12"]) / 1e6
    qg = reduced_stiffness(GLASS["e1"], GLASS["e2"], GLASS["g12"], GLASS["nu12"]) / 1e6
    q45g = (qg[0, 0] + qg[1, 1] + 2 * qg[0, 1] + 4 * qg[2, 2]) / 4
    # 2 × (0C + 90C) + 4 × (±45G), her biri T_MM
    a11 = 2 * T_MM * (qc[0, 0] + qc[1, 1]) + 4 * T_MM * q45g
    assert abd.A[0, 0] == pytest.approx(a11, rel=1e-9)
    assert abd.A[0, 0] == pytest.approx(abd.A[1, 1], rel=1e-9)  # 0/90 + ±45 → yarı-izotrop eksenler
    assert np.abs(abd.B).max() < 1e-6 * abd.A[0, 0]
    assert abs(abd.A[0, 2]) < 1e-9 * abd.A[0, 0] and abs(abd.A[1, 2]) < 1e-9 * abd.A[0, 0]
    # Cam katman karbondan yumuşak: aynı açıda karbon olsaydı A11 daha büyük
    all_carbon = abd_matrix([Ply(CARBON["e1"], CARBON["e2"], CARBON["g12"], CARBON["nu12"], T_MM, a) for _, a in STACK])
    assert abd.A[0, 0] < all_carbon.A[0, 0]


@requires_ccx
def test_ccx_hybrid_ply_stress_and_irf_match_clt(tmp_path, monkeypatch):
    import scripts.composite_validation_vp1 as vp1

    spec = _spec("PLATE")
    monkeypatch.setattr(vp1, "write_composite_section", lambda _s: write_composite_section(spec))
    case = vp1.Case("h", tuple(a for _, a in STACK), 200.0, 50.0, 20, 6, "nx", _NX)
    deck, _ = vp1.build_deck(case)
    deck = deck.replace(
        "*END STEP", "*EL PRINT, ELSET=PLATE\nS\n*NODE FILE\nU\n*EL FILE\nS\n*END STEP"
    )
    inp = tmp_path / "hyb.inp"
    inp.write_text(deck, encoding="utf-8")
    ccx = _ccx_executable()
    proc = subprocess.run(
        [ccx, "hyb"], cwd=tmp_path, env=_ccx_run_env(ccx), capture_output=True, text=True
    )
    assert (tmp_path / "hyb.dat").exists(), proc.stdout[-1500:]

    rs = CalculiXAdapter().parse_results(
        JobHandle(job_id="h", work_dir=tmp_path, artifact=InputArtifact(path=inp))
    )
    sc = rs.scalars
    assert sc["n_plies"] == 8

    plies = _clt_plies()
    eps = midplane_response(abd_matrix(plies), n=(_NX, 0.0, 0.0))
    ref = np.array(ply_stresses(plies, eps["eps0"], eps["kappa"]))
    tw_ref = np.array(
        [
            tsai_wu_irf(ref[k : k + 1, 0], ref[k : k + 1, 1], ref[k : k + 1, 2], strength_from_material(_MATS[m]))[0]
            for k, (m, _a) in enumerate(STACK)
        ]
    )
    hs_ref = np.array(
        [
            hashin_irf(ref[k : k + 1, 0], ref[k : k + 1, 1], ref[k : k + 1, 2], strength_from_material(_MATS[m]))[0].max()
            for k, (m, _a) in enumerate(STACK)
        ]
    )

    field = json.loads((tmp_path / "hyb_ply.json").read_text(encoding="utf-8"))
    plate = field["sets"]["PLATE"]
    assert [p["angle_deg"] for p in plate["plies"]] == [a for _, a in STACK]
    mats = [p["material"] for p in plate["plies"]]
    assert len(set(mats)) == 2 and mats[0] == mats[3] and mats[1] == mats[2] and mats[0] != mats[1]

    # Orta sıra elemanları (serbest kenar / yük girişi dışı): CLT'ye %2
    mid = [i for i in range(120) if (i // 20) in (2, 3)]
    s11 = np.array([plate["s11"][i] for i in mid]).mean(axis=0)
    s22 = np.array([plate["s22"][i] for i in mid]).mean(axis=0)
    np.testing.assert_allclose(s11, ref[:, 0], rtol=0.02, atol=0.5)
    np.testing.assert_allclose(s22, ref[:, 1], rtol=0.02, atol=0.5)
    tw_mid = np.array([plate["tsai_wu_irf"][i] for i in mid]).mean(axis=0)
    hs_mid = np.array([plate["hashin_irf"][i] for i in mid]).mean(axis=0)
    # Alan IRF'i eleman içi IP'lerin en büyüğü (gerilme ise ortalama) → bant %3;
    # ölçülen en büyük sapma 90° karbon katmanda +%2.4 (2026-10-22).
    np.testing.assert_allclose(tw_mid, tw_ref, rtol=0.03)
    np.testing.assert_allclose(hs_mid, hs_ref, rtol=0.03)
    # Uç değer: tüm IP'ler; alt sınır CLT, üst bant %15 (V-P1 / 3.12 ile aynı)
    assert tw_ref.max() * 0.99 <= sc["tsai_wu_irf_max"] <= tw_ref.max() * 1.15
