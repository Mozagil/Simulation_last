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
    assert "        14         2         0         0         0         4" in text


@requires_db
def test_crash_solve_contact_without_wall():
    """1.12a: tek parçalı kutuda TYPE24 self-contact, duvar kapalı."""
    geometry_id = _upload_and_mesh_box()
    response = client.post(
        "/crash/solve",
        json={
            "geometry_id": geometry_id,
            "barrier": _barrier(),
            "run_solver": False,
            "use_rigid_wall": False,
            "contacts": [{"type": 24, "master_part": 0, "slave_part": 0, "fric": 0.1}],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["cards"]["has_rwall"] is False
    assert body["cards"]["n_inter"] == 1
    text = (CRASH_DIR / body["job_id"] / "crash_0000.rad").read_text(encoding="utf-8")
    assert "/SURF/PART/EXT/1001" in text and "/INTER/TYPE24/1" in text
    snap = client.get(f"/crash/jobs/{body['job_id']}").json()
    assert snap["use_rigid_wall"] is False
    assert snap["contacts"][0]["type"] == 24


@requires_db
def test_crash_solve_rejects_bad_contact():
    geometry_id = _upload_and_mesh_box()
    bad_type = client.post(
        "/crash/solve",
        json={
            "geometry_id": geometry_id,
            "barrier": _barrier(),
            "contacts": [{"type": 5, "master_part": 0, "slave_part": 0}],
        },
    )
    assert bad_type.status_code == 422
    missing_part = client.post(
        "/crash/solve",
        json={
            "geometry_id": geometry_id,
            "barrier": _barrier(),
            "contacts": [{"type": 7, "master_part": 3, "slave_part": 0}],
        },
    )
    assert missing_part.status_code == 422
    assert "#3" in missing_part.json()["detail"]


@requires_db
def test_crash_solve_dimension_checks():
    """1.13a: dimension=2 kabuk kabul edilir ama 2D mesh ister; 1 geçersiz."""
    geometry_id = _upload_and_mesh_box()
    no_2d = client.post(
        "/crash/solve",
        json={"geometry_id": geometry_id, "barrier": _barrier(), "dimension": 2},
    )
    assert no_2d.status_code == 404
    assert "dimension=2" in no_2d.json()["detail"]
    bad = client.post(
        "/crash/solve",
        json={"geometry_id": geometry_id, "barrier": _barrier(), "dimension": 1},
    )
    assert bad.status_code == 400


@requires_db
def test_crash_solve_shell_mesh_writes_shell_cards():
    """1.13a + numara düzeltmesi: midsurface → 2D quad → /SHELL + /PROP/TYPE1.

    Dosyada solid (CAD #0) + orta yüzey (CAD #1) var. Kabuk parçası UI'daki
    numarayla (#1) yazılmalı ve #1'in malzemesini (S355) almalı — eskiden 0'dan
    numaralanıyor, solid'in malzemesi (S235) sessizce kabuğa gidiyordu.
    """
    with (FIXTURES_DIR / "thin_plate.step").open("rb") as f:
        up = client.post(
            "/geometry/upload",
            files={"file": ("thin_plate.step", f, "application/octet-stream")},
        )
    geometry_id = up.json()["geometry_id"]
    assert client.post(f"/geometry/{geometry_id}/parts/0/midsurface").status_code == 200
    mesh = client.post(
        f"/geometry/{geometry_id}/mesh",
        json={"element_size": 3.0, "dimension": 2, "element_scheme": "quad"},
    )
    assert mesh.status_code == 200
    mats = {m["name"]: m["id"] for m in client.get("/materials").json()["materials"]}
    for part_id, name in ((0, "S235"), (1, "S355")):
        client.post(
            "/materials/assignments",
            json={"geometry_id": geometry_id, "part_id": part_id, "material_id": mats[name]},
        )
    base = {"geometry_id": geometry_id, "barrier": _barrier(), "dimension": 2}
    no_t = client.post("/crash/solve", json=base)
    assert no_t.status_code == 422
    assert "kalınlığı" in no_t.json()["detail"] and "#1" in no_t.json()["detail"]
    ok = client.post(
        "/crash/solve",
        json={
            **base,
            "parts": [{"part_id": 1, "role": "moving", "thickness_mm": 2.5}],
            "model": {"law": "elastic", "shell": {"ishell": 24, "nip": 5}},
        },
    )
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["cards"]["has_shell"] is True and body["cards"]["has_tetra4"] is False
    text = (CRASH_DIR / body["job_id"] / "crash_0000.rad").read_text(encoding="utf-8")
    # CAD #1 → Radioss part_ID 2; #0 (solid) deck'te yok
    lines = text.splitlines()
    assert "/SHELL/2" in lines and "/PART/2" in lines and "/PART/1" not in lines
    assert text.split("/MAT/LAW1/2\n", 1)[1].splitlines()[0] == "S355"
    prop = text.split("/PROP/TYPE1/2\n", 1)[1].splitlines()
    assert prop[1].startswith(f"{24:10d}")
    assert prop[3].startswith(f"{5:10d}{0:10d}") and float(prop[3][20:40]) == 2.5


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
