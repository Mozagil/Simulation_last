"""1.17c — bölge / parça /BCS + /IMPVEL (bölge, parça ya da rijit gövde ana düğümü).

Kart düzenleri hm_cfg: bcs radioss51 ("   111 111" skew grnod), impvel radioss120
(funct Dir skew sensor grnod frame Icoor · Scale_x Scale_y Tstart Tstop).
Hız /FUNCT değerinde, Scale_y = 1: Radioss Scale_y = 0'ı varsayılan 1 sayar
(gerçek koşuda sıfır hız 1 mm/ms uygulandı, model patladı).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.solvers.base import SolverError
from app.solvers.crash_params import CrashBcParams, CrashImpVelParams
from app.solvers.openradioss import OpenRadiossAdapter
from tests.test_crash_contact import _card
from tests.test_crash_multipart import _two_part_params


def _deck(tmp_path, **extra) -> str:
    p = _two_part_params(tmp_path)  # parça 0: düğüm 1–4, parça 1: 5–8
    p.update(extra)
    return OpenRadiossAdapter().build_input(p).path.read_text(encoding="utf-8")


def test_bcs_on_region_and_part(tmp_path):
    s = _deck(tmp_path, region_nodes={"arka": [2, 3]}, boundary_conditions=[
        {"name": "yz", "region": "arka", "dofs": "011000"},
        {"name": "tam", "part_id": 1},
    ])
    assert _card(s, "/BCS/11") == ["yz", f"   011 000{0:10d}{8801:10d}"]
    assert _card(s, "/GRNOD/NODE/8801")[1] == f"{2:10d}{3:10d}"
    assert _card(s, "/BCS/12")[1] == f"   111 111{0:10d}{8802:10d}"
    assert "/BCS/1\n" in s  # sabit parça (1.11b) yerinde


def test_impvel_velocity_in_function_scale_one(tmp_path):
    s = _deck(tmp_path, region_nodes={"arka": [2, 3]}, imposed_velocities=[
        {"name": "itme", "region": "arka", "direction": "X", "velocity_m_s": -10, "t_stop_ms": 5},
        {"name": "sifir", "part_id": 0, "direction": "YY", "velocity_m_s": 0},
    ])
    assert _card(s, "/FUNCT/9901")[1:] == [f"{0.0:20.8g}{-10.0:20.8g}", f"{1e30:20.8g}{-10.0:20.8g}"]
    iv = _card(s, "/IMPVEL/1")
    assert iv[0] == "itme"
    assert iv[1] == f"{9901:10d}{'X':>10}{0:10d}{0:10d}{8901:10d}{'':10}{0:10d}"
    assert iv[2] == f"{1.0:20.8g}{1.0:20.8g}{0.0:20.8g}{5.0:20.8g}"
    # sıfır hız: fonksiyon 0, ölçek yine 1 (0 ölçek = Radioss varsayılanı 1)
    assert _card(s, "/FUNCT/9902")[1] == f"{0.0:20.8g}{0.0:20.8g}"
    assert _card(s, "/IMPVEL/2")[2][:40] == f"{1.0:20.8g}{1.0:20.8g}"
    assert _card(s, "/IMPVEL/2")[1][10:20] == f"{'YY':>10}"


def test_impvel_on_rigid_body_master(tmp_path):
    s = _deck(tmp_path, region_nodes={"uc": [2, 3]},
              rigid_bodies=[{"name": "itici", "region": "uc"}],
              imposed_velocities=[{"name": "x", "rigid_body": "itici", "direction": "X", "velocity_m_s": -10}])
    master = _card(s, "/RBODY/1")[1][:10]
    assert _card(s, "/GRNOD/NODE/8901")[1] == master  # yalnız ana düğüm
    with pytest.raises(SolverError, match="rijit gövde 'yok'"):
        _deck(tmp_path, imposed_velocities=[{"name": "x", "rigid_body": "yok", "velocity_m_s": 1}])


@pytest.mark.parametrize(
    "cls,raw",
    [
        (CrashBcParams, {"region": "a", "dofs": "11100"}),
        (CrashBcParams, {"region": "a", "dofs": "000000"}),
        (CrashBcParams, {"region": "a", "dofs": "11a000"}),
        (CrashImpVelParams, {"velocity_m_s": 1}),  # hedef yok
        (CrashImpVelParams, {"region": "a", "rigid_body": "b", "velocity_m_s": 1}),
        (CrashImpVelParams, {"region": "a", "direction": "W", "velocity_m_s": 1}),
        (CrashImpVelParams, {"region": "a", "velocity_m_s": 1, "t_start_ms": 2, "t_stop_ms": 1}),
    ],
)
def test_invalid_rejected(cls, raw):
    with pytest.raises(ValidationError):
        cls.model_validate(raw)
