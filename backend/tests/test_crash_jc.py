"""1.14a — LAW2 Johnson-Cook: hız / sıcaklık terimleri ve sınırlar.

Kart düzeni hm_cfg radioss140 matl2_plas_johns (Radioss 2022 bu düzeni
kullanır): ρ · E ν Iflag · a b n EPS_p_max SIG_max0 · c ε̇₀ ICC Fsmooth F_cut
Chard · m T_melt ρCp T_r. Birimler kg–mm–ms'ye çevrilir.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.solvers.crash_params import CrashModelParams
from app.solvers.openradioss import OpenRadiossAdapter
from tests.test_crash_contact import _card
from tests.test_crash_multipart import _two_part_params


def _law2(tmp_path, **model) -> list[str]:
    p = _two_part_params(tmp_path)
    p["materials"] = [{**m, "yield_strength": 235e6} for m in p["materials"]]
    p["model"] = {"law": "plastic", "harden_b_mpa": 500.0, "harden_n": 0.3, **model}
    s = OpenRadiossAdapter().build_input(p).path.read_text(encoding="utf-8")
    return _card(s, "/MAT/LAW2/1")


def _fields(line: str, widths: list[int]) -> list[str]:
    out, i = [], 0
    for w in widths:
        out.append(line[i : i + w].strip())
        i += w
    return out


def test_defaults_keep_terms_off(tmp_path):
    c = _law2(tmp_path)
    assert len(c) == 6  # başlık + 5 veri satırı
    assert len(c[2]) == 50  # E ν Iflag (%20 %20 %10)
    a, b, n, eps_max, sig_max = (float(x) for x in _fields(c[3], [20] * 5))
    assert (a, b, n) == (pytest.approx(0.235), pytest.approx(0.5), 0.3)
    assert (eps_max, sig_max) == (0.0, 0.0)
    assert all(float(x) == 0.0 for x in _fields(c[4], [20, 20, 10, 10, 20, 20]))
    assert len(c[5]) == 80 and all(float(x) == 0.0 for x in _fields(c[5], [20] * 4))


def test_rate_temperature_and_limits_with_unit_conversion(tmp_path):
    c = _law2(
        tmp_path,
        eps_p_max=0.35,
        sig_max0_mpa=900.0,
        jc_c=0.014,
        jc_eps_dot0_per_s=1.0,
        jc_icc=2,
        jc_fsmooth=1,
        jc_fcut_hz=10000.0,
        jc_chard=0.5,
        jc_m=1.03,
        jc_t_melt_k=1793.0,
        jc_rho_cp=3.7e6,
        jc_t_r_k=293.0,
    )
    _a, _b, _n, eps_max, sig_max = (float(x) for x in _fields(c[3], [20] * 5))
    assert eps_max == 0.35 and sig_max == pytest.approx(0.9)  # MPa → GPa
    cc, eps0, icc, fs, fcut, chard = _fields(c[4], [20, 20, 10, 10, 20, 20])
    assert float(cc) == 0.014
    assert float(eps0) == pytest.approx(1e-3)  # 1/s → 1/ms
    assert (int(icc), int(fs)) == (2, 1)
    assert float(fcut) == pytest.approx(10.0)  # Hz → 1/ms
    assert float(chard) == 0.5
    m, tmelt, rhocp, tr = (float(x) for x in _fields(c[5], [20] * 4))
    assert (m, tmelt, tr) == (1.03, 1793.0, 293.0)
    assert rhocp == pytest.approx(3.7e-3)  # J/(m³K) → J/(mm³K)


@pytest.mark.parametrize(
    "raw",
    [
        {"jc_c": 0.01},  # ε̇₀ yok
        {"jc_m": 1.0, "jc_t_melt_k": 0.0},  # T_melt yok
        {"jc_m": 1.0, "jc_t_melt_k": 300.0, "jc_t_r_k": 300.0},  # T_melt ≤ T_r
        {"jc_icc": 3},
        {"jc_fsmooth": 2},
        {"jc_chard": 1.5},
        {"eps_p_max": -0.1},
    ],
)
def test_invalid_jc_rejected(raw):
    with pytest.raises(ValidationError):
        CrashModelParams.model_validate({"law": "plastic", **raw})


def test_elastic_law1_unaffected(tmp_path):
    p = _two_part_params(tmp_path)
    p["model"] = {"law": "elastic", "jc_c": 0.1, "jc_eps_dot0_per_s": 1.0}
    s = OpenRadiossAdapter().build_input(p).path.read_text(encoding="utf-8")
    assert "/MAT/LAW1/1" in s and "/MAT/LAW2" not in s
