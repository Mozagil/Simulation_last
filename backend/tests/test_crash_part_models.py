"""1.14b — parça başına malzeme kartı (parts[].model).

Parça kendi kanununu / JC parametrelerini / eleman kartını alır; verilmeyen
parça istekteki global `model`'e düşer (eski davranış).
"""

from __future__ import annotations

import pytest

from app.solvers.openradioss_headers import strip_headers
from app.solvers.base import SolverError
from app.solvers.openradioss import OpenRadiossAdapter
from tests.test_crash_contact import _card
from tests.test_crash_multipart import _two_part_params
from tests.test_crash_shell import _shell_params


def _mats_with_yield(p):
    p["materials"] = [{**m, "yield_strength": 235e6} for m in p["materials"]]
    return p


def test_part_model_overrides_global(tmp_path):
    p = _mats_with_yield(_two_part_params(tmp_path))
    p["model"] = {"law": "elastic", "isolid": 1}
    p["parts"] = [
        {"part_id": 0, "role": "moving",
         "model": {"law": "plastic", "harden_b_mpa": 400.0, "harden_n": 0.25, "isolid": 24,
                   "jc_c": 0.02, "jc_eps_dot0_per_s": 1.0}},
        {"part_id": 1, "role": "fixed"},
    ]
    s = strip_headers(OpenRadiossAdapter().build_input(p).path.read_text(encoding="utf-8"))
    # parça 0 (Radioss 1): LAW2 + kendi JC + Isolid 24; parça 1 (Radioss 2): global LAW1
    assert "/MAT/LAW2/1" in s and "/MAT/LAW1/2" in s
    assert "/MAT/LAW1/1" not in s and "/MAT/LAW2/2" not in s
    law2 = _card(s, "/MAT/LAW2/1")
    assert float(law2[3][20:40]) == pytest.approx(0.4)  # b MPa → GPa
    assert float(law2[4][0:20]) == 0.02  # c
    assert _card(s, "/PROP/TYPE14/1")[1].startswith(f"{24:10d}")
    assert _card(s, "/PROP/TYPE14/2")[1].startswith(f"{1:10d}")


def test_no_part_models_keeps_global_for_all(tmp_path):
    p = _mats_with_yield(_two_part_params(tmp_path))
    p["model"] = {"law": "plastic"}
    s = strip_headers(OpenRadiossAdapter().build_input(p).path.read_text(encoding="utf-8"))
    assert "/MAT/LAW2/1" in s and "/MAT/LAW2/2" in s


def test_shell_part_uses_its_own_shell_flags_and_thickness(tmp_path):
    p = _shell_params(
        tmp_path,
        model={"law": "elastic"},  # global ortak kalınlık yok
        parts=[
            {"part_id": 0, "model": {"law": "elastic", "shell": {"thickness_mm": 1.6, "ishell": 12, "nip": 3}}},
            {"part_id": 1, "role": "fixed"},
        ],
    )
    s = strip_headers(OpenRadiossAdapter().build_input(p).path.read_text(encoding="utf-8"))
    prop = _card(s, "/PROP/TYPE1/1")
    assert prop[1].startswith(f"{12:10d}")
    assert prop[3].startswith(f"{3:10d}") and float(prop[3][20:40]) == 1.6


def test_invalid_part_model_is_solver_error(tmp_path):
    p = _mats_with_yield(_two_part_params(tmp_path))
    p["parts"] = [{"part_id": 0, "model": {"law": "plastic", "jc_c": 0.1}}]  # ε̇₀ eksik
    with pytest.raises(SolverError, match="model geçersiz"):
        OpenRadiossAdapter().build_input(p)
