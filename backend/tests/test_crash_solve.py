"""Faz 1.7 — POST /crash/solve (CalculiX /solve dokunulmaz)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.api.crash import CRASH_DIR
from app.api.geometry import UPLOAD_DIR
from app.db.session import SessionLocal
from app.jobs.progress import get_hub
from app.main import app
from tests.db_guard import safe_cleanup

client = TestClient(app)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
BOX = FIXTURES_DIR / "box.step"


def _db_available() -> bool:
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        return True
    except OperationalError:
        return False


requires_db = pytest.mark.skipif(
    not _db_available(),
    reason="PostgreSQL bağlantısı yok",
)


@pytest.fixture(autouse=True)
def _clean_state():
    get_hub().reset()
    yield
    get_hub().reset()
    if not _db_available():
        return
    safe_cleanup(
        UPLOAD_DIR,
        "TRUNCATE analysis_runs, material_assignments, physical_groups, "
        "geometries RESTART IDENTITY CASCADE",
    )


def _upload_and_mesh_box() -> int:
    content = BOX.read_bytes()
    upload = client.post(
        "/geometry/upload",
        files={"file": ("box.step", content, "application/octet-stream")},
    )
    geometry_id = upload.json()["geometry_id"]
    mesh_resp = client.post(
        f"/geometry/{geometry_id}/mesh",
        json={"dimension": 3, "element_size": 8, "element_scheme": "tet"},
    )
    assert mesh_resp.status_code == 200
    mats = client.get("/materials").json()["materials"]
    client.post(
        "/materials/assignments",
        json={"geometry_id": geometry_id, "part_id": 0, "material_id": mats[0]["id"]},
    )
    return geometry_id


def _barrier() -> dict:
    return {
        "speed_m_s": 10.0,
        "angle_deg": 0.0,
        "wall": {"point": [0.0, 0.0, 0.0], "normal": [0.0, 0.0, 1.0]},
    }


@requires_db
def test_crash_solve_writes_rad_without_solver():
    geometry_id = _upload_and_mesh_box()
    response = client.post(
        "/crash/solve",
        json={
            "geometry_id": geometry_id,
            "barrier": _barrier(),
            "run_solver": False,
            "t_end_ms": 8.0,
            "name": "box impact",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "rad_only"
    assert body["cards"]["has_tetra4"] is True
    assert body["cards"]["has_rwall"] is True
    assert body["cards"]["has_inivel"] is True
    job_id = body["job_id"]
    starter = CRASH_DIR / job_id / "crash_0000.rad"
    engine = CRASH_DIR / job_id / "crash_0001.rad"
    assert starter.is_file()
    assert engine.is_file()
    text = starter.read_text(encoding="utf-8")
    assert "/TETRA4" in text
    assert "/RWALL" in text
    snap = client.get(f"/crash/jobs/{job_id}")
    assert snap.status_code == 200
    assert snap.json()["geometry_id"] == geometry_id


@requires_db
def test_crash_solve_plastic_writes_law2():
    geometry_id = _upload_and_mesh_box()
    response = client.post(
        "/crash/solve",
        json={
            "geometry_id": geometry_id,
            "barrier": _barrier(),
            "run_solver": False,
            "scenario": "plate_ball",
            "model": {
                "law": "plastic",
                "isolid": 14,
                "ismstr": 2,
                "nip": 4,
                "sigma_y_pa": 235e6,
                "harden_b_mpa": 100.0,
                "harden_n": 0.2,
            },
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["cards"]["has_law2"] is True
    assert body["cards"]["has_law1"] is False
    text = (CRASH_DIR / body["job_id"] / "crash_0000.rad").read_text(encoding="utf-8")
    assert "/MAT/LAW2" in text
    assert "        14         2         0         0         4" in text


@requires_db
def test_crash_solve_rejects_dimension_2():
    geometry_id = _upload_and_mesh_box()
    response = client.post(
        "/crash/solve",
        json={"geometry_id": geometry_id, "barrier": _barrier(), "dimension": 2},
    )
    assert response.status_code == 400


@requires_db
def test_crash_solve_rejects_bad_barrier():
    geometry_id = _upload_and_mesh_box()
    response = client.post(
        "/crash/solve",
        json={
            "geometry_id": geometry_id,
            "barrier": {"speed_m_s": -4.0, "angle_deg": 0.0},
        },
    )
    assert response.status_code == 422


@requires_db
def test_crash_solve_needs_mesh():
    content = BOX.read_bytes()
    upload = client.post(
        "/geometry/upload",
        files={"file": ("box.step", content, "application/octet-stream")},
    )
    gid = upload.json()["geometry_id"]
    mats = client.get("/materials").json()["materials"]
    client.post(
        "/materials/assignments",
        json={"geometry_id": gid, "part_id": 0, "material_id": mats[0]["id"]},
    )
    response = client.post(
        "/crash/solve",
        json={"geometry_id": gid, "barrier": _barrier()},
    )
    assert response.status_code == 404


@requires_db
def test_crash_solve_run_solver_without_binary_fails(monkeypatch):
    geometry_id = _upload_and_mesh_box()
    monkeypatch.setattr("app.api.crash.resolve_openradioss", lambda: None)
    response = client.post(
        "/crash/solve",
        json={
            "geometry_id": geometry_id,
            "barrier": _barrier(),
            "run_solver": True,
            "wait": True,
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert "OpenRadioss" in response.json()["message"]


@requires_db
def test_crash_job_survives_hub_reset():
    geometry_id = _upload_and_mesh_box()
    body = client.post(
        "/crash/solve",
        json={"geometry_id": geometry_id, "barrier": _barrier()},
    ).json()
    get_hub().reset()
    snap = client.get(f"/crash/jobs/{body['job_id']}")
    assert snap.status_code == 200
    assert snap.json()["status"] == "rad_only"
