"""Faz 1.3 — crash bariyer şeması (hız / açı / rigid wall)."""

import math

import pytest
from pydantic import ValidationError

from app.solvers.base import SolverError
from app.solvers.crash_params import (
    CrashBarrierParams,
    CrashModelParams,
    RigidWallParams,
    apply_barrier,
)
from app.solvers.openradioss import OpenRadiossAdapter


def _tiny_nodes():
    return [
        {"id": 1, "x": 0.0, "y": 0.0, "z": 10.0},
        {"id": 2, "x": 1.0, "y": 0.0, "z": 10.0},
        {"id": 3, "x": 0.0, "y": 1.0, "z": 10.0},
        {"id": 4, "x": 0.0, "y": 0.0, "z": 11.0},
    ]


def test_head_on_velocity_is_minus_normal():
    b = CrashBarrierParams(speed_m_s=10.0, angle_deg=0.0)
    vx, vy, vz = b.velocity_mm_per_ms()
    assert vx == pytest.approx(0.0, abs=1e-12)
    assert vy == pytest.approx(0.0, abs=1e-12)
    assert vz == pytest.approx(-10.0)


def test_angle_90_sweeps_along_plus_x_for_z_wall():
    b = CrashBarrierParams(speed_m_s=10.0, angle_deg=90.0)
    vx, vy, vz = b.velocity_mm_per_ms()
    assert vx == pytest.approx(10.0)
    assert vy == pytest.approx(0.0, abs=1e-12)
    assert vz == pytest.approx(0.0, abs=1e-12)


def test_angle_30_splits_speed():
    b = CrashBarrierParams(speed_m_s=10.0, angle_deg=30.0)
    vx, vy, vz = b.velocity_mm_per_ms()
    assert vx == pytest.approx(10.0 * math.sin(math.radians(30)))
    assert vy == pytest.approx(0.0, abs=1e-12)
    assert vz == pytest.approx(-10.0 * math.cos(math.radians(30)))
    assert math.hypot(vx, vy, vz) == pytest.approx(10.0)


def test_x_normal_wall_uses_y_as_sweep():
    b = CrashBarrierParams(
        speed_m_s=5.0,
        angle_deg=90.0,
        wall=RigidWallParams(point=(100.0, 0.0, 0.0), normal=(1.0, 0.0, 0.0)),
    )
    vx, vy, vz = b.velocity_mm_per_ms()
    assert vx == pytest.approx(0.0, abs=1e-12)
    assert vy == pytest.approx(5.0)
    assert vz == pytest.approx(0.0, abs=1e-12)


def test_wall_normal_is_unit_in_rwall():
    b = CrashBarrierParams(
        speed_m_s=1.0,
        wall=RigidWallParams(point=(0.0, 0.0, -40.0), normal=(0.0, 0.0, 2.0)),
    )
    _vel, wall = b.to_inivel_rwall()
    assert wall["point"] == [0.0, 0.0, -40.0]
    assert wall["normal"][2] == pytest.approx(1.0)


def test_rejects_negative_speed():
    with pytest.raises(ValidationError):
        CrashBarrierParams(speed_m_s=-1.0)


def test_rejects_zero_normal():
    with pytest.raises(ValidationError, match="sıfır"):
        CrashBarrierParams(
            speed_m_s=1.0,
            wall=RigidWallParams(normal=(0.0, 0.0, 0.0)),
        )


def test_model_defaults_elastic_isolid1_nip1():
    m = CrashModelParams()
    assert m.law == "elastic"
    assert m.isolid == 1
    assert m.nip == 1


def test_model_rejects_unknown_law():
    with pytest.raises(ValidationError, match="elastic"):
        CrashModelParams(law="ogden")


def test_apply_barrier_overwrites_velocity_dict():
    params = {
        "initial_velocity": {"vx": 9.0, "vy": 0.0, "vz": 0.0},
        "rigid_wall": {"point": [1, 2, 3], "normal": [0, 1, 0]},
    }
    apply_barrier(params, CrashBarrierParams(speed_m_s=8.0, angle_deg=0.0))
    assert params["initial_velocity"]["vz"] == pytest.approx(-8.0)
    assert params["rigid_wall"]["point"] == [0.0, 0.0, 0.0]


def test_build_input_barrier_writes_inivel_and_rwall(tmp_path):
    art = OpenRadiossAdapter().build_input(
        {
            "output_dir": tmp_path,
            "job_name": "bar",
            "nodes": _tiny_nodes(),
            "tets": [(1, 1, 2, 3, 4)],
            "barrier": {
                "speed_m_s": 15.0,
                "angle_deg": 0.0,
                "wall": {"point": [0.0, 0.0, -50.0], "normal": [0.0, 0.0, 1.0]},
            },
        }
    )
    starter = art.path.read_text(encoding="utf-8")
    assert "/INIVEL/TRA/1" in starter
    assert "/RWALL/PLANE/1" in starter
    assert "-15" in starter
    assert "-50" in starter


def test_build_input_invalid_barrier_is_solver_error(tmp_path):
    with pytest.raises(SolverError, match="barrier"):
        OpenRadiossAdapter().build_input(
            {
                "output_dir": tmp_path,
                "nodes": _tiny_nodes(),
                "tets": [(1, 1, 2, 3, 4)],
                "barrier": {"speed_m_s": -4.0},
            }
        )
