"""Faz 3.11 — katman gerilmesi: ccx `.dat` EL PRINT → ply eksenli tensör.

Ayrıştırıcı / deste okuma testleri her zaman koşar; ccx karşılaştırması
(V-P1 düzeni, simetrik [30/0/90/−45]s, Nx) ccx yoksa atlanır.
"""

from __future__ import annotations

import subprocess

import numpy as np
import pytest

from app.composite.layup import Ply, abd_matrix
from app.composite.ply_stress import (
    el_print_block,
    parse_ply_stress,
    plies_by_set_from_inp,
    ply_stress_scalars,
)
from app.composite.reference import midplane_response, ply_stresses
from app.composite.section_writer import composite_plies_by_elset, write_composite_inp
from app.solvers.base import InputArtifact, JobHandle
from app.solvers.calculix import CalculiXAdapter, _ccx_executable, _ccx_run_env
from scripts.composite_validation_vp1 import PLY_T_MM, T300, Case, build_deck

requires_ccx = pytest.mark.skipif(_ccx_executable() is None, reason="ccx yok")

_HDR = " stresses (elem, integ.pnt.,sxx,syy,szz,sxy,sxz,syz) for set {} and time  0.1000000E+01\n\n"


def _row(eid: int, ip: int, s11: float) -> str:
    return f"{eid:10d}{ip:4d}  {s11:.6E}  1.0E+00  0.0E+00 -2.0E+00  0.0E+00  0.0E+00 OR_0_0_shell_0\n"


def test_parse_two_sets_layers_in_ip_order():
    # A: 2 katman × 2 IP (ip 1–2 alt, 3–4 üst); B: 1 katman × 2 IP
    text = (
        _HDR.format("PART_0")
        + "".join(_row(7, ip, 10.0 * ip) for ip in (1, 2, 3, 4))
        + "\n"
        + _HDR.format("PART_1")
        + "".join(_row(9, ip, -1.0) for ip in (1, 2))
        + "\n displacements (vx,vy,vz) for set X and time 1.0\n\n 1 0 0 0\n"
    )
    out = parse_ply_stress(text, {"part_0": 2, "PART_1": 1})
    a, b = out["PART_0"], out["PART_1"]
    assert a.values.shape == (1, 2, 2, 6)
    assert a.ply_mean()[0, :, 0].tolist() == [15.0, 35.0]
    assert a.values[0, 1, 0, 3] == -2.0  # s12
    assert b.n_plies == 1 and b.element_ids.tolist() == [9]
    ex = a.extremes()
    assert ex["n_plies"] == 2.0
    assert ex["ply2_s11_max"] == 40.0 and ex["ply1_s11_min"] == 10.0
    assert "ply1_s33_max" not in ex
    sc = ply_stress_scalars(out)
    assert sc["part_0_ply2_s11_max"] == 40.0 and sc["part_1_n_plies"] == 1.0
    assert ply_stress_scalars({"PART_0": a})["ply2_s11_max"] == 40.0


def test_parse_rejects_ip_not_divisible_and_skips_unknown_sets():
    text = _HDR.format("PART_0") + "".join(_row(1, ip, 1.0) for ip in (1, 2, 3))
    with pytest.raises(ValueError, match="bölünmüyor"):
        parse_ply_stress(text, {"PART_0": 2})
    assert parse_ply_stress(text, {"OTHER": 1}) == {}


def test_plies_by_set_from_deck_matches_writer():
    ply = {**T300, "thickness_mm": 0.25}
    layup = [
        {"part_id": 0, "plies": [dict(ply, angle_deg=a) for a in (0, 90, 90, 0)]},
        {"part_id": 3, "plies": [dict(ply, angle_deg=45)]},
    ]
    deck = write_composite_inp(layup)
    assert plies_by_set_from_inp(deck) == {"PART_0": 4, "PART_3": 1}
    assert composite_plies_by_elset(layup) == {"PART_0": 4, "PART_3": 1}
    assert el_print_block(["PART_0"]) == "*EL PRINT, ELSET=PART_0\nS\n"
    iso = "*SHELL SECTION, ELSET=PART_0, MATERIAL=S355\n2.0\n"
    assert plies_by_set_from_inp(iso) == {}


_ANGLES = (30.0, 0.0, 90.0, -45.0, -45.0, 90.0, 0.0, 30.0)
_CASE = Case("s", _ANGLES, 200.0, 50.0, 20, 6, "nx", 10.0)


def _run(tmp_path, extra_out: str = ""):
    deck, _ = build_deck(_CASE)
    deck = deck.replace("*END STEP", f"*EL PRINT, ELSET=PLATE\nS\n{extra_out}*END STEP")
    inp = tmp_path / "ps.inp"
    inp.write_text(deck, encoding="utf-8")
    ccx = _ccx_executable()
    subprocess.run(
        [ccx, "ps"], cwd=tmp_path, env=_ccx_run_env(ccx), capture_output=True, timeout=600
    )
    return inp


@requires_ccx
def test_ccx_ply_stress_matches_clt(tmp_path):
    inp = _run(tmp_path)
    by_set = parse_ply_stress(
        (tmp_path / "ps.dat").read_text(encoding="utf-8", errors="replace"),
        plies_by_set_from_inp(inp.read_text(encoding="utf-8")),
    )
    ps = by_set["PLATE"]
    assert ps.n_plies == 8 and ps.values.shape[2] == 8  # 2×2×2 IP / katman
    plies = [
        Ply(T300["e1"], T300["e2"], T300["g12"], T300["nu12"], PLY_T_MM, a)
        for a in _ANGLES
    ]
    eps = midplane_response(abd_matrix(plies), n=(10.0, 0.0, 0.0))
    ref = np.array(ply_stresses(plies, eps["eps0"], eps["kappa"]))
    # Serbest kenar etkisi dışında: y yönünde ortadaki iki eleman sırası
    mean = ps.ply_mean()
    ny, nx = _CASE.ny, _CASE.nx
    rows = [i for i in range(len(ps.element_ids)) if (i // nx) in (ny // 2 - 1, ny // 2)]
    got = mean[rows].mean(axis=0)[:, [0, 1, 3]]
    scale = np.abs(ref).max()
    np.testing.assert_allclose(got, ref, atol=0.02 * scale)
    # Lif yönü gerilmesi katman başına %2 içinde, işaret aynı
    np.testing.assert_allclose(got[:, 0], ref[:, 0], rtol=0.02)


@requires_ccx
def test_adapter_parse_results_reports_ply_scalars(tmp_path):
    inp = _run(tmp_path, "*NODE FILE\nU\n*EL FILE\nS\n")
    job = JobHandle(job_id="ps", work_dir=tmp_path, artifact=InputArtifact(path=inp))
    rs = CalculiXAdapter().parse_results(job)
    assert rs.scalars["n_plies"] == 8.0
    # 0° katman (2.) lif gerilmesi en büyük: Nx yükü lif boyunca taşınır
    s11 = [rs.scalars[f"ply{k}_s11_max"] for k in range(1, 9)]
    assert int(np.argmax(s11)) in (1, 6)
    assert rs.scalars["ply3_s11_min"] < 0  # 90°: lif yönünde basma (Poisson)
