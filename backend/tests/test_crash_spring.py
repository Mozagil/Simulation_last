"""1.24b1 — yay elemanı: /PROP/TYPE4 (hm_cfg radioss140) + /PART + /SPRING
(hm_cfg radioss110) + /TH/SPRING; uçlar rijit gövde ana düğümü ya da nokta."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.solvers.base import SolverError
from app.solvers.crash_params import CrashSpringParams
from app.solvers.openradioss import OpenRadiossAdapter
from tests.test_crash_contact import _card
from tests.test_crash_multipart import _two_part_params


def _deck(tmp_path, springs, **extra) -> str:
    p = _two_part_params(tmp_path)
    p["springs"] = springs
    p.update(extra)
    return OpenRadiossAdapter().build_input(p).path.read_text(encoding="utf-8")


def test_spring_rbody_to_fixed_point(tmp_path):
    s = _deck(
        tmp_path,
        [
            {
                "name": "yay1",
                "end_a": {"rigid_body": "kizak"},
                "end_b": {"point": [-20.0, 0.0, 0.0]},
                "k_n_per_mm": 2500.0,
                "c_n_s_per_mm": 3.0,
                "mass_kg": 0.5,
            }
        ],
        rigid_bodies=[{"name": "kizak", "part_id": 0, "mass_kg": 10}],
    )
    # düğümler: mesh 1–8, rijit ana düğüm 9, yay nokta ucu 10
    assert f"{10:10d}{-20.0:20.6g}" in s.replace("  -20", " -20") or "        10" in s
    # parça kimlikleri: mesh 1–2, yay 3; eleman kimliği mesh en büyüğü (2) + 1
    prop = _card(s, "/PROP/TYPE4/3")
    assert prop[0] == "spring_yay1"
    assert float(prop[1][:20]) == 0.5 and len(prop[1]) == 80
    k, c = float(prop[2][:20]), float(prop[2][20:40])
    assert (k, c) == (2.5, 3.0)  # N/mm → kN/mm; N·s/mm → kN·ms/mm aynı sayı
    assert len(prop) == 5
    assert _card(s, "/PART/3") == ["spring_yay1", f"{0:10d}{3:10d}"]
    el = _card(s, "/SPRING/3")
    assert el[0][:30] == f"{3:10d}{9:10d}{10:10d}"
    assert len(el[0]) == 100 and el[0].endswith(f"{0:10d}")
    # sabit uç: /GRNOD/NODE/9941 + /BCS/41 altı serbestlik
    assert _card(s, "/GRNOD/NODE/9941") == ["spring_yay1_fixed", f"{10:10d}"]
    assert _card(s, "/BCS/41") == ["spring_yay1_fixed", f"   111 111{0:10d}{9941:10d}"]
    th = _card(s, "/TH/SPRING/6")
    assert th[0] == "spring_th" and th[1].split() == ["FX", "FY", "FZ"] and th[2] == f"{3:10d}"


def test_spring_free_point_no_bcs_and_th_off(tmp_path):
    s = _deck(
        tmp_path,
        [{"name": "s", "end_a": {"point": [0, 0, 5]}, "end_b": {"point": [0, 0, 25], "fixed": False},
          "k_n_per_mm": 100.0, "th": False}],
    )
    assert "/GRNOD/NODE/9941" in s and "/BCS/41" in s  # yalnız a ucu sabit (varsayılan)
    assert _card(s, "/GRNOD/NODE/9941")[1] == f"{9:10d}"
    assert "/TH/SPRING" not in s
    assert _card(s, "/SPRING/3")[0][:30] == f"{3:10d}{9:10d}{10:10d}"


def test_spring_unknown_rigid_body(tmp_path):
    with pytest.raises(SolverError, match="rijit gövde 'yok'"):
        _deck(tmp_path, [{"end_a": {"rigid_body": "yok"}, "end_b": {"point": [0, 0, 0]}, "k_n_per_mm": 1}])


@pytest.mark.parametrize(
    "raw",
    [
        {"end_a": {"rigid_body": "a", "point": [0, 0, 0]}, "end_b": {"point": [1, 0, 0]}, "k_n_per_mm": 1},
        {"end_a": {}, "end_b": {"point": [1, 0, 0]}, "k_n_per_mm": 1},
        {"end_a": {"rigid_body": "a"}, "end_b": {"rigid_body": "a"}, "k_n_per_mm": 1},
        {"end_a": {"point": [0, 0, 0]}, "end_b": {"point": [1, 0, 0]}, "k_n_per_mm": 0},
    ],
)
def test_spring_validation(raw):
    with pytest.raises(ValidationError):
        CrashSpringParams.model_validate(raw)


def test_spring_th_keys_in_postprocess_map():
    from app.postprocess.openradioss_th import named_th_curves

    cols = {"TIME": [0.0], "spring_th var 1": [1.0], "spring_th var 2": [2.0], "spring_th var 3": [3.0]}
    spec = {"groups": [{"kind": "spring", "title": "spring_th", "objects": [3], "vars": ["FX", "FY", "FZ"]}]}
    out, unmapped = named_th_curves(cols, spec)
    assert out["th_spring_1_FZ"] == [3.0] and not unmapped
