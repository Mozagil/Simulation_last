"""1.24c2 — Rayleigh sönümü /DAMP (hm_cfg radioss110 Damp.cfg):
Alpha Beta grnod_id skew_id Tstart Tstop; α 1/s → 1/ms, β s → ms."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.solvers.base import SolverError
from app.solvers.crash_params import CrashDampingParams
from app.solvers.openradioss import OpenRadiossAdapter
from tests.test_crash_contact import _card
from tests.test_crash_multipart import _two_part_params


def _deck(tmp_path, damping) -> str:
    p = _two_part_params(tmp_path)
    p["damping"] = damping
    return OpenRadiossAdapter().build_input(p).path.read_text(encoding="utf-8")


def _row(s: str) -> tuple[float, float, int, int, float, float]:
    card = _card(s, "/DAMP/1")
    assert card[0] == "rayleigh" and card[1].startswith("#")
    r = card[2]
    assert len(r) == 100  # 20 20 10 10 20 20
    return float(r[:20]), float(r[20:40]), int(r[40:50]), int(r[50:60]), float(r[60:80]), float(r[80:100])


def test_whole_model_units_and_group(tmp_path):
    s = _deck(tmp_path, {"alpha_per_s": 200.0, "beta_s": 1e-6})
    a, b, g, skew, t0, t1 = _row(s)
    assert a == pytest.approx(0.2)  # 200 1/s → 0.2 1/ms
    assert b == pytest.approx(1e-3)  # 1e-6 s → 1e-3 ms
    assert (g, skew, t0, t1) == (9930, 0, 0.0, 0.0)
    # boş part_ids → tüm parçalar (mesh parça 0, 1 → kart kimliği 1, 2)
    assert _card(s, "/GRNOD/PART/9930") == ["damp_parts", f"{1:10d}{2:10d}"]
    # /END'den önce
    assert s.index("/DAMP/1") < s.index("/END")


def test_selected_part_and_window(tmp_path):
    s = _deck(tmp_path, {"alpha_per_s": 50.0, "part_ids": [1], "t_start_ms": 2.0, "t_stop_ms": 8.0})
    a, b, g, _skew, t0, t1 = _row(s)
    assert (a, b, t0, t1) == (pytest.approx(0.05), 0.0, 2.0, 8.0)
    assert _card(s, "/GRNOD/PART/9930") == ["damp_parts", f"{2:10d}"]


def test_no_damping_no_card(tmp_path):
    assert "/DAMP/" not in _deck(tmp_path, None)


def test_unknown_part_rejected(tmp_path):
    with pytest.raises(SolverError, match="parça \\[7\\]"):
        _deck(tmp_path, {"alpha_per_s": 1.0, "part_ids": [7]})


@pytest.mark.parametrize(
    "body",
    [
        {"alpha_per_s": 0.0, "beta_s": 0.0},
        {"alpha_per_s": -1.0},
        {"alpha_per_s": 1.0, "t_start_ms": 5.0, "t_stop_ms": 2.0},
        {"alpha_per_s": float("nan")},
    ],
)
def test_validation(body):
    with pytest.raises(ValidationError):
        CrashDampingParams.model_validate(body)
