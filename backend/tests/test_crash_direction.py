"""TODO 11.1 — ilk hız yönü duvardan bağımsız (`barrier.direction`)."""

from __future__ import annotations

import math

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.crash import CRASH_DIR
from app.main import app
from app.solvers.crash_params import CrashBarrierParams
from tests.test_crash_contact import _card
from tests.test_crash_solve import _clean_state, _upload_and_mesh_box  # noqa: F401 (autouse temizlik)
from tests.test_materials import requires_db

client = TestClient(app)


def test_direction_overrides_wall_normal_and_angle():
    b = CrashBarrierParams(speed_m_s=10.0, angle_deg=30.0, direction=(0.0, 0.0, -2.0))
    assert b.velocity_mm_per_ms() == pytest.approx((0.0, 0.0, -10.0))
    d = CrashBarrierParams(speed_m_s=5.0, direction=(1.0, 1.0, 0.0)).velocity_mm_per_ms()
    assert d == pytest.approx((5 / math.sqrt(2), 5 / math.sqrt(2), 0.0))


def test_no_direction_keeps_old_behaviour():
    # duvar normali +x → yaklaşım -x (önceki davranış birebir)
    b = CrashBarrierParams(speed_m_s=10.0, wall={"point": (0, 0, 0), "normal": (1, 0, 0)})
    assert b.velocity_mm_per_ms() == pytest.approx((-10.0, 0.0, 0.0))


@pytest.mark.parametrize("bad", [(0, 0, 0), (float("nan"), 0, 1)])
def test_bad_direction_rejected(bad):
    with pytest.raises(ValidationError):
        CrashBarrierParams(speed_m_s=1.0, direction=bad)


@requires_db
def test_wallless_solve_with_direction_needs_no_wall():
    gid = _upload_and_mesh_box()
    r = client.post("/crash/solve", json={
        "geometry_id": gid,
        "barrier": {"speed_m_s": 4.0, "direction": [0, 0, -1]},
        "use_rigid_wall": False,
        "run_solver": False,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cards"]["has_rwall"] is False
    deck = (CRASH_DIR / body["job_id"] / "crash_0000.rad").read_text(encoding="utf-8")
    vel = _card(deck, "/INIVEL/TRA/1")[1]
    assert [float(vel[i:i + 20]) for i in (0, 20, 40)] == pytest.approx([0.0, 0.0, -4.0])


@requires_db
def test_barrier_optional():
    gid = _upload_and_mesh_box()
    r = client.post("/crash/solve", json={"geometry_id": gid, "use_rigid_wall": False, "run_solver": False})
    assert r.status_code == 200, r.text


@requires_db
def test_card_initial_velocity_replaces_barrier_velocity():
    """TODO 11.9 — ilk hız kartı: parça düğümlerine kendi grubu + /INIVEL; bariyer hızı yazılmaz."""
    gid = _upload_and_mesh_box()
    r = client.post("/crash/solve", json={
        "geometry_id": gid,
        "barrier": {"speed_m_s": 10.0},
        "use_rigid_wall": False,
        "run_solver": False,
        "initial_velocities": [{"name": "kutu", "part_id": 0, "speed_m_s": 3.0, "direction": [0, 0, -1]}],
    })
    assert r.status_code == 200, r.text
    body = r.json()
    deck = (CRASH_DIR / body["job_id"] / "crash_0000.rad").read_text(encoding="utf-8")
    assert "/INIVEL/TRA/1\n" not in deck and "/INIVEL/TRA/2\n" not in deck
    assert "/GRNOD/NODE/8601" in deck
    vel = _card(deck, "/INIVEL/TRA/61")[1]
    assert [float(vel[i:i + 20]) for i in (0, 20, 40)] == pytest.approx([0.0, 0.0, -3.0])
    assert int(vel[60:70]) == 8601
    snap = client.get(f"/crash/jobs/{body['job_id']}").json()
    assert snap["initial_velocities"][0]["speed_m_s"] == 3.0


def test_init_vel_params_validation():
    from app.solvers.crash_params import CrashInitVelParams

    v = CrashInitVelParams(name="a", region="taban", speed_m_s=2.0, direction=(3.0, 4.0, 0.0))
    assert v.velocity_mm_per_ms() == pytest.approx((1.2, 1.6, 0.0))
    with pytest.raises(ValidationError):
        CrashInitVelParams(name="a", region="taban", part_id=0, speed_m_s=1.0, direction=(1, 0, 0))
    with pytest.raises(ValidationError):
        CrashInitVelParams(name="a", part_id=0, speed_m_s=1.0, direction=(0, 0, 0))
