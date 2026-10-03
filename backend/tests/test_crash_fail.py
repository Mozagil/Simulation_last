"""1.14d — /FAIL/JOHNSON + /FAIL/TENSSTRAIN (eleman silme), parça başına.

Kart düzenleri hm_cfg: JOHNSON radioss2017, TENSSTRAIN radioss2021. Başlıkta
malzeme kimliği; başlık (title) satırı yok.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.solvers.crash_params import CrashFailJohnson, CrashFailTensStrain
from app.solvers.openradioss import OpenRadiossAdapter
from tests.test_crash_contact import _card
from tests.test_crash_multipart import _two_part_params

_JC = {"d1": 0.05, "d2": 3.44, "d3": -2.12, "d4": 0.002, "d5": 0.61,
       "eps_dot0_per_s": 1.0, "ifail_sh": 1, "ifail_so": 1, "dadv": 0.5}


def _deck(tmp_path, global_model=None, parts=None) -> str:
    p = _two_part_params(tmp_path)
    p["materials"] = [{**m, "yield_strength": 235e6} for m in p["materials"]]
    p["model"] = global_model or {"law": "plastic"}
    if parts is not None:
        p["parts"] = parts
    return OpenRadiossAdapter().build_input(p).path.read_text(encoding="utf-8")


def test_johnson_card_layout(tmp_path):
    s = _deck(tmp_path, {"law": "plastic", "fail": {"johnson": _JC}})
    c = _card(s, "/FAIL/JOHNSON/1")
    assert len(c) == 2
    assert [float(c[0][i : i + 20]) for i in range(0, 100, 20)] == [0.05, 3.44, -2.12, 0.002, 0.61]
    assert float(c[1][:20]) == pytest.approx(1e-3)  # 1/s → 1/ms
    assert c[1][20:40] == f"{1:10d}{1:10d}" and c[1][40:60] == " " * 20
    assert float(c[1][60:80]) == 0.5 and c[1][80:90] == " " * 10 and int(c[1][90:100]) == 0
    # FAIL kartı malzeme kartından sonra, aynı kimlikle
    assert s.index("/MAT/LAW2/1") < s.index("/FAIL/JOHNSON/1")


def test_tensstrain_card_layout_and_both_criteria(tmp_path):
    s = _deck(tmp_path, {"law": "plastic", "fail": {
        "johnson": _JC,
        "tensstrain": {"eps_t1": 0.2, "eps_t2": 0.3, "eps_f1": 0.0, "eps_f2": 0.0, "s_flag": 21}}})
    c = _card(s, "/FAIL/TENSSTRAIN/1")
    assert len(c) == 1 and len(c[0]) == 100
    assert (float(c[0][:20]), float(c[0][20:40])) == (0.2, 0.3)
    assert int(c[0][40:50]) == 0 and int(c[0][90:100]) == 21
    assert "/FAIL/JOHNSON/1" in s  # iki kriter aynı malzemede


def test_fail_per_part_only_on_that_material(tmp_path):
    s = _deck(tmp_path, {"law": "plastic"}, parts=[
        {"part_id": 0, "model": {"law": "plastic", "fail": {"tensstrain": {"eps_t1": 0.1, "eps_t2": 0.2}}}},
        {"part_id": 1, "role": "fixed"},
    ])
    assert "/FAIL/TENSSTRAIN/1" in s and "/FAIL/TENSSTRAIN/2" not in s
    assert "/FAIL/JOHNSON" not in s


def test_no_fail_by_default(tmp_path):
    assert "/FAIL/" not in _deck(tmp_path)


@pytest.mark.parametrize(
    "cls,raw",
    [
        (CrashFailJohnson, {"ifail_so": 3}),
        (CrashFailJohnson, {"d4": 0.01}),  # ε̇₀ yok
        (CrashFailTensStrain, {"eps_t1": 0.3, "eps_t2": 0.2}),  # t2 ≤ t1
        (CrashFailTensStrain, {}),  # hiç sınır yok
        (CrashFailTensStrain, {"eps_t1": 0.1, "eps_t2": 0.2, "s_flag": 2}),  # ek kartlı seçenek
    ],
)
def test_invalid_fail_rejected(cls, raw):
    with pytest.raises(ValidationError):
        cls.model_validate(raw)
