"""Solve API + analiz geçmişi (AnalysisRun) endpoint testleri.

Not: Bu testler gerçek bir PostgreSQL bağlantısı gerektiriyor — bkz.
test_geometry_upload.py'deki `requires_db` deseni.
"""

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.api.geometry import MESH_DIR, UPLOAD_DIR
from app.db.session import SessionLocal
from app.main import app

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
    reason="PostgreSQL bağlantısı yok (DATABASE_URL ayarlı değil ya da servis kapalı)",
)


@pytest.fixture(autouse=True)
def _clean_state():
    yield
    if UPLOAD_DIR.exists():
        shutil.rmtree(UPLOAD_DIR)
    if _db_available():
        db = SessionLocal()
        db.execute(
            text(
                "TRUNCATE analysis_runs, material_assignments, physical_groups, "
                "geometries RESTART IDENTITY CASCADE"
            )
        )
        db.commit()
        db.close()


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
    material_id = mats[0]["id"]
    assign_resp = client.post(
        "/materials/assignments",
        json={"geometry_id": geometry_id, "part_id": 0, "material_id": material_id},
    )
    assert assign_resp.status_code == 200

    return geometry_id


@requires_db
def test_solve_creates_analysis_run_record():
    """KRİTİK: her /solve çağrısı kalıcı bir AnalysisRun satırı üretmeli —
    ROADMAP.md '7. Veritabanına kayıt + geçmiş' gereksinimi.
    """
    geometry_id = _upload_and_mesh_box()

    response = client.post(
        f"/geometry/{geometry_id}/solve",
        json={
            "dimension": 3,
            "run_solver": False,  # ccx olmasa da .inp üretimi + DB kaydı test edilir
            "name": "Test Case 1",
            "bcs": [{"type": "fixed", "face_ids": [1]}],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert "run_id" in body
    assert body["run_id"] is not None

    # Geçmiş listesinde görünmeli
    runs_response = client.get("/geometry/runs")
    assert runs_response.status_code == 200
    runs_body = runs_response.json()
    assert runs_body["count"] == 1
    assert runs_body["runs"][0]["id"] == body["run_id"]
    assert runs_body["runs"][0]["name"] == "Test Case 1"
    assert runs_body["runs"][0]["geometry_id"] == geometry_id


@requires_db
def test_two_solves_on_same_geometry_do_not_overwrite_each_other():
    """KRİTİK: aynı geometride ikinci bir case çözülünce, öncekinin .inp
    dosyası ÜZERİNE YAZILMAMALI — eskiden `geo{id}_d{dim}` adlandırması bu
    hataya sebep oluyordu, artık her run kendi klasöründe.
    """
    geometry_id = _upload_and_mesh_box()

    first = client.post(
        f"/geometry/{geometry_id}/solve",
        json={
            "dimension": 3,
            "run_solver": False,
            "name": "Case A",
            "bcs": [{"type": "fixed", "face_ids": [1]}],
        },
    ).json()
    second = client.post(
        f"/geometry/{geometry_id}/solve",
        json={
            "dimension": 3,
            "run_solver": False,
            "name": "Case B",
            "bcs": [{"type": "fixed", "face_ids": [2]}],
        },
    ).json()

    assert first["run_id"] != second["run_id"]
    assert first["inp_path"] != second["inp_path"]

    # İkisi de diskte hâlâ var (birbirinin üzerine yazmadı).
    assert Path(first["inp_path"]).exists()
    assert Path(second["inp_path"]).exists()

    runs_body = client.get("/geometry/runs").json()
    assert runs_body["count"] == 2
    names = {r["name"] for r in runs_body["runs"]}
    assert names == {"Case A", "Case B"}


@requires_db
def test_get_run_detail_returns_404_for_unknown_id():
    response = client.get("/geometry/runs/999999")
    assert response.status_code == 404


@requires_db
def test_get_run_detail_includes_bcs_and_urls():
    geometry_id = _upload_and_mesh_box()
    solve_body = client.post(
        f"/geometry/{geometry_id}/solve",
        json={
            "dimension": 3,
            "run_solver": False,
            "name": "Detay testi",
            "bcs": [{"type": "fixed", "face_ids": [1]}],
        },
    ).json()
    run_id = solve_body["run_id"]

    detail = client.get(f"/geometry/runs/{run_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["id"] == run_id
    assert body["geometry_id"] == geometry_id
    assert body["name"] == "Detay testi"
    assert body["bcs"] == [{"type": "fixed", "face_ids": [1]}]
    assert body["tessellation_url"] == f"/files/tessellations/{geometry_id}.stl"


@requires_db
def test_solve_without_materials_does_not_create_orphan_run():
    """Malzeme atanmadan /solve çağrılırsa 422 dönmeli VE hiçbir
    AnalysisRun satırı OLUŞMAMALI (validasyon run oluşturulmadan önce
    yapılıyor).
    """
    content = BOX.read_bytes()
    upload = client.post(
        "/geometry/upload",
        files={"file": ("box.step", content, "application/octet-stream")},
    )
    geometry_id = upload.json()["geometry_id"]
    client.post(
        f"/geometry/{geometry_id}/mesh",
        json={"dimension": 3, "element_size": 8, "element_scheme": "tet"},
    )

    response = client.post(
        f"/geometry/{geometry_id}/solve",
        json={"dimension": 3, "run_solver": False, "bcs": []},
    )
    assert response.status_code == 422

    runs_body = client.get("/geometry/runs").json()
    assert runs_body["count"] == 0
