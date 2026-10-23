"""1.14c — LAW36 (tabulated): /MAT/LAW36 + /FUNCT akma eğrileri.

Kart düzeni hm_cfg radioss2017 matl36_plas_tab (2022 bunu kullanır), /FUNCT
radioss90 (X Y çiftleri, %20). Eğriler istekte; yoksa malzeme kütüphanesinden (1.14c2,
test_crash_material_curves).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.solvers.openradioss_headers import strip_headers
from app.solvers.crash_params import CrashModelParams
from app.solvers.openradioss import OpenRadiossAdapter
from tests.test_crash_contact import _card
from tests.test_crash_multipart import _two_part_params

_CURVES = [
    {"eps_dot_per_s": 1.0, "points": [(0.0, 235.0), (0.1, 300.0), (0.5, 400.0)]},
    {"eps_dot_per_s": 100.0, "points": [(0.0, 260.0), (0.5, 430.0)]},
]


def _deck(tmp_path, **model) -> str:
    p = _two_part_params(tmp_path)
    p["model"] = {"law": "tabulated", "tab_curves": _CURVES, **model}
    return strip_headers(OpenRadiossAdapter().build_input(p).path.read_text(encoding="utf-8"))


def test_law36_card_layout_and_units(tmp_path):
    s = _deck(tmp_path, eps_p_max=0.6, tab_eps_f=0.8, tab_vp=1, jc_fsmooth=1, jc_fcut_hz=5000.0)
    c = _card(s, "/MAT/LAW36/1")
    assert c[0] == "S235"
    assert len(c[2]) == 100 and float(c[2][40:60]) == 0.6  # E ν Eps_p_max Eps_t Eps_m
    # N_funct F_smooth C_hard F_cut Eps_f · VP
    assert c[3][:20] == f"{2:10d}{1:10d}"
    assert float(c[3][40:60]) == pytest.approx(5.0)  # 5000 Hz → 1/ms
    assert float(c[3][60:80]) == 0.8 and c[3][80:90] == " " * 10 and int(c[3][90:100]) == 1
    assert c[4] == f"{0:10d}{0.0:20.8g}{0:10d}{0.0:20.8g}{0.0:20.8g}"
    assert c[5] == f"{101:10d}{102:10d}"  # eğri kimlikleri (card_id·100 + k)
    assert [float(c[6][i : i + 20]) for i in (0, 20)] == [1.0, 1.0]  # ölçek
    assert [float(c[7][i : i + 20]) for i in (0, 20)] == pytest.approx([1e-3, 0.1])  # 1/s → 1/ms
    f = _card(s, "/FUNCT/101")
    assert f[0] == "yield_1_1_per_s" and len(f) == 4
    x, y = float(f[3][:20]), float(f[3][20:40])
    assert (x, y) == (0.5, pytest.approx(0.4))  # σ MPa → GPa
    assert len(_card(s, "/FUNCT/102")) == 3


def test_each_part_gets_its_own_function_ids(tmp_path):
    s = _deck(tmp_path)  # global model → iki parça da LAW36
    assert "/MAT/LAW36/1" in s and "/MAT/LAW36/2" in s
    assert "/FUNCT/101" in s and "/FUNCT/201" in s and "/FUNCT/202" in s
    assert _card(s, "/MAT/LAW36/2")[5] == f"{201:10d}{202:10d}"


@pytest.mark.parametrize(
    "raw",
    [
        {"law": "tabulated", "tab_curves": [{"eps_dot_per_s": 1.0, "points": [(0.0, 235.0)]}]},  # tek nokta
        {"law": "tabulated", "tab_curves": [{"eps_dot_per_s": 1.0, "points": [(0.1, 235.0), (0.1, 300.0)]}]},  # ε_p artmıyor
        {"law": "tabulated", "tab_curves": [_CURVES[1], _CURVES[0]]},  # hız azalan
        {"law": "tabulated", "tab_curves": _CURVES, "tab_vp": 2},
        {"law": "tabulated", "tab_curves": [{"eps_dot_per_s": 1.0, "points": [(0.0, -1.0), (0.1, 2.0)]}]},
    ],
)
def test_invalid_law36_rejected(raw):
    with pytest.raises(ValidationError):
        CrashModelParams.model_validate(raw)


def test_law36_per_part_with_law2_other_part(tmp_path):
    p = _two_part_params(tmp_path)
    p["materials"] = [{**m, "yield_strength": 235e6} for m in p["materials"]]
    p["model"] = {"law": "plastic"}
    p["parts"] = [{"part_id": 0, "model": {"law": "tabulated", "tab_curves": _CURVES[:1]}}, {"part_id": 1, "role": "fixed"}]
    s = strip_headers(OpenRadiossAdapter().build_input(p).path.read_text(encoding="utf-8"))
    assert "/MAT/LAW36/1" in s and "/MAT/LAW2/2" in s and "/FUNCT/101" in s and "/FUNCT/2" not in s
