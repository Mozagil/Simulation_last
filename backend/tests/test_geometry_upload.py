"""Geometri endpoint testleri.

Not: Bu testler artık gerçek bir PostgreSQL bağlantısı gerektiriyor (Geometry
kaydı DB'de tutuluyor) — DATABASE_URL ayarlı değilse ya da servis kapalıysa
zarifçe skip edilir (bkz. `requires_db`, test_db_connection.py'deki desenle
aynı).
"""

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.api.geometry import UPLOAD_DIR
from app.db.session import SessionLocal
from app.main import app

client = TestClient(app)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
VALID_STEP_FILE = FIXTURES_DIR / "box.step"


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
    """Her testten önce/sonra hem dosya sistemini hem DB tablolarını temizle."""
    yield
    if UPLOAD_DIR.exists():
        shutil.rmtree(UPLOAD_DIR)
    if _db_available():
        db = SessionLocal()
        db.execute(text("TRUNCATE physical_groups, geometries RESTART IDENTITY CASCADE"))
        db.commit()
        db.close()


def _upload_box() -> dict:
    content = VALID_STEP_FILE.read_bytes()
    response = client.post(
        "/geometry/upload",
        files={"file": ("box.step", content, "application/octet-stream")},
    )
    assert response.status_code == 200
    return response.json()


@requires_db
def test_upload_step_file_creates_geometry_record_and_tessellates():
    body = _upload_box()

    assert isinstance(body["geometry_id"], int)
    assert body["original_filename"] == "box.step"
    assert body["current_filename"] == f"{body['geometry_id']}.step"

    saved_path = UPLOAD_DIR / body["current_filename"]
    assert saved_path.exists()

    assert body["face_count"] == 6
    assert body["triangle_count"] > 0
    assert len(body["triangle_to_face"]) == body["triangle_count"]
    assert len(set(body["triangle_to_face"])) == 6

    assert body["part_count"] == 1
    assert set(body["triangle_to_part"]) == {0}


@requires_db
def test_upload_assembly_distinguishes_parts():
    assembly_file = FIXTURES_DIR / "assembly_two_boxes.step"
    content = assembly_file.read_bytes()
    response = client.post(
        "/geometry/upload",
        files={"file": ("assembly_two_boxes.step", content, "application/octet-stream")},
    )

    assert response.status_code == 200
    body = response.json()

    assert body["part_count"] == 2
    assert set(body["triangle_to_part"]) == {0, 1}
    part_0_count = body["triangle_to_part"].count(0)
    part_1_count = body["triangle_to_part"].count(1)
    assert part_0_count == part_1_count
    assert body["face_count"] == 12


def test_upload_rejects_unsupported_extension():
    # Uzantı kontrolü DB'ye ulaşmadan önce yapılıyor, DB gerektirmez.
    response = client.post(
        "/geometry/upload",
        files={"file": ("part.txt", b"not a cad file", "text/plain")},
    )
    assert response.status_code == 400
    assert "Desteklenmeyen dosya uzantısı" in response.json()["detail"]


@requires_db
def test_upload_rejects_corrupt_step_file():
    corrupt_content = b"bu gecerli bir STEP dosyasi degil"
    response = client.post(
        "/geometry/upload",
        files={"file": ("bozuk.step", corrupt_content, "application/octet-stream")},
    )
    assert response.status_code == 422
    assert "Geometri okunamadı" in response.json()["detail"]


@requires_db
def test_list_surfaces_after_upload():
    upload_body = _upload_box()
    geometry_id = upload_body["geometry_id"]

    response = client.get(f"/geometry/{geometry_id}/surfaces")

    assert response.status_code == 200
    body = response.json()
    assert body["geometry_id"] == geometry_id
    assert body["surface_count"] == 6

    surface = body["surfaces"][0]
    assert set(surface.keys()) == {"id", "area", "normal", "part_id"}
    assert surface["area"] == pytest.approx(100.0)

    total_area = sum(s["area"] for s in body["surfaces"])
    assert total_area == pytest.approx(600.0)


@requires_db
def test_list_surfaces_returns_404_for_unknown_geometry():
    response = client.get("/geometry/999999/surfaces")
    assert response.status_code == 404


@requires_db
def test_list_edges_after_upload():
    upload_body = _upload_box()
    geometry_id = upload_body["geometry_id"]

    response = client.get(f"/geometry/{geometry_id}/edges")

    assert response.status_code == 200
    body = response.json()
    assert body["edge_count"] == 12
    total_length = sum(e["length"] for e in body["edges"])
    assert total_length == pytest.approx(120.0)


@requires_db
def test_list_edges_returns_404_for_unknown_geometry():
    response = client.get("/geometry/999999/edges")
    assert response.status_code == 404


@requires_db
def test_list_points_after_upload():
    upload_body = _upload_box()
    geometry_id = upload_body["geometry_id"]

    response = client.get(f"/geometry/{geometry_id}/points")

    assert response.status_code == 200
    body = response.json()
    assert body["point_count"] == 8


@requires_db
def test_list_points_returns_404_for_unknown_geometry():
    response = client.get("/geometry/999999/points")
    assert response.status_code == 404


@requires_db
def test_copy_surface_after_upload():
    upload_body = _upload_box()
    geometry_id = upload_body["geometry_id"]

    response = client.post(f"/geometry/{geometry_id}/surfaces/1/copy")

    assert response.status_code == 200
    body = response.json()
    assert body["original_face_id"] == 1
    assert body["new_face_id"] not in {1, 2, 3, 4, 5, 6}
    # Kopya sonrası tessellation da tazelenmeli — 7 yüzey görünmeli.
    assert body["face_count"] == 7


@requires_db
def test_copy_surface_persists_across_separate_requests():
    """KRİTİK TEST: kopyalama gerçekten kalıcı mı? Kopyaladıktan SONRA, tamamen
    AYRI bir GET isteği ile yüzeyleri tekrar sorgulayıp yeni yüzeyin hâlâ
    orada olduğunu doğrular — bu, tüm bu refactor'ın amacı.
    """
    upload_body = _upload_box()
    geometry_id = upload_body["geometry_id"]

    copy_response = client.post(f"/geometry/{geometry_id}/surfaces/1/copy")
    assert copy_response.status_code == 200
    new_face_id = copy_response.json()["new_face_id"]

    # Tamamen ayrı, sonraki bir istek.
    surfaces_response = client.get(f"/geometry/{geometry_id}/surfaces")
    assert surfaces_response.status_code == 200
    surfaces_body = surfaces_response.json()

    assert surfaces_body["surface_count"] == 7
    surface_ids = {s["id"] for s in surfaces_body["surfaces"]}
    assert new_face_id in surface_ids


@requires_db
def test_copy_surface_returns_404_for_unknown_geometry():
    response = client.post("/geometry/999999/surfaces/1/copy")
    assert response.status_code == 404


@requires_db
def test_copy_surface_returns_404_for_unknown_face_id():
    upload_body = _upload_box()
    geometry_id = upload_body["geometry_id"]

    response = client.post(f"/geometry/{geometry_id}/surfaces/999/copy")
    assert response.status_code == 404


@requires_db
def test_create_physical_group_after_upload():
    upload_body = _upload_box()
    geometry_id = upload_body["geometry_id"]

    response = client.post(
        f"/geometry/{geometry_id}/physical-groups",
        json={"name": "inlet", "face_ids": [1, 2]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "inlet"
    assert body["entity_tags"] == [1, 2]
    assert body["face_count"] == 2
    assert isinstance(body["id"], int)


@requires_db
def test_create_physical_group_persists_and_is_listed():
    """KRİTİK TEST: grup ataması gerçekten kalıcı mı? Oluşturduktan SONRA
    ayrı bir GET isteğiyle listede görünmeli.
    """
    upload_body = _upload_box()
    geometry_id = upload_body["geometry_id"]

    client.post(
        f"/geometry/{geometry_id}/physical-groups",
        json={"name": "inlet", "face_ids": [1, 2]},
    )
    client.post(
        f"/geometry/{geometry_id}/physical-groups",
        json={"name": "fixed_support", "face_ids": [3]},
    )

    response = client.get(f"/geometry/{geometry_id}/physical-groups")
    assert response.status_code == 200
    body = response.json()

    assert body["group_count"] == 2
    names = {g["name"] for g in body["groups"]}
    assert names == {"inlet", "fixed_support"}


@requires_db
def test_create_physical_group_rejects_invalid_face_id():
    upload_body = _upload_box()
    geometry_id = upload_body["geometry_id"]

    response = client.post(
        f"/geometry/{geometry_id}/physical-groups",
        json={"name": "gecersiz", "face_ids": [999]},
    )
    assert response.status_code == 422


@requires_db
def test_create_physical_group_rejects_empty_name():
    upload_body = _upload_box()
    geometry_id = upload_body["geometry_id"]

    response = client.post(
        f"/geometry/{geometry_id}/physical-groups",
        json={"name": "", "face_ids": [1]},
    )
    assert response.status_code == 422


@requires_db
def test_list_physical_groups_empty_when_none_created():
    upload_body = _upload_box()
    geometry_id = upload_body["geometry_id"]

    response = client.get(f"/geometry/{geometry_id}/physical-groups")
    assert response.status_code == 200
    assert response.json()["group_count"] == 0


@requires_db
def test_list_physical_groups_returns_404_for_unknown_geometry():
    response = client.get("/geometry/999999/physical-groups")
    assert response.status_code == 404


@requires_db
def test_heal_geometry_after_upload():
    upload_body = _upload_box()
    geometry_id = upload_body["geometry_id"]

    response = client.post(f"/geometry/{geometry_id}/heal")

    assert response.status_code == 200
    body = response.json()
    assert body["volumes_before"] == body["volumes_after"] == 1
    assert body["surfaces_before"] == body["surfaces_after"] == 6
    # Tessellation da tazelenmiş olmalı.
    assert body["face_count"] == 6


@requires_db
def test_heal_geometry_returns_404_for_unknown_geometry():
    response = client.post("/geometry/999999/heal")
    assert response.status_code == 404


@requires_db
def test_defeature_candidates_narrow_threshold_empty():
    upload_body = _upload_box()
    geometry_id = upload_body["geometry_id"]

    response = client.get(
        f"/geometry/{geometry_id}/defeature-candidates", params={"max_diameter": 2.0}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["candidate_count"] == 0
    assert body["candidates"] == []


@requires_db
def test_defeature_candidates_wide_threshold_finds_all_edges():
    upload_body = _upload_box()
    geometry_id = upload_body["geometry_id"]

    response = client.get(
        f"/geometry/{geometry_id}/defeature-candidates", params={"max_diameter": 100.0}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["candidate_count"] == 12


@requires_db
def test_defeature_candidates_rejects_non_positive_threshold():
    upload_body = _upload_box()
    geometry_id = upload_body["geometry_id"]

    response = client.get(
        f"/geometry/{geometry_id}/defeature-candidates", params={"max_diameter": 0}
    )
    assert response.status_code == 400


@requires_db
def test_defeature_candidates_returns_404_for_unknown_geometry():
    response = client.get(
        "/geometry/999999/defeature-candidates", params={"max_diameter": 5.0}
    )
    assert response.status_code == 404


@requires_db
def test_create_midsurface_after_upload():
    upload_body = _upload_box()
    geometry_id = upload_body["geometry_id"]

    response = client.post(
        f"/geometry/{geometry_id}/midsurface",
        json={"face_id_a": 1, "face_id_b": 2},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["new_face_id"] not in {1, 2, 3, 4, 5, 6}
    assert body["face_count"] == 7


@requires_db
def test_create_midsurface_persists_across_separate_requests():
    upload_body = _upload_box()
    geometry_id = upload_body["geometry_id"]

    create_response = client.post(
        f"/geometry/{geometry_id}/midsurface",
        json={"face_id_a": 1, "face_id_b": 2},
    )
    new_face_id = create_response.json()["new_face_id"]

    surfaces_response = client.get(f"/geometry/{geometry_id}/surfaces")
    surfaces_body = surfaces_response.json()

    assert surfaces_body["surface_count"] == 7
    surface_ids = {s["id"] for s in surfaces_body["surfaces"]}
    assert new_face_id in surface_ids


@requires_db
def test_create_midsurface_rejects_non_parallel_faces():
    upload_body = _upload_box()
    geometry_id = upload_body["geometry_id"]

    response = client.post(
        f"/geometry/{geometry_id}/midsurface",
        json={"face_id_a": 1, "face_id_b": 3},
    )
    assert response.status_code == 422


@requires_db
def test_create_midsurface_returns_404_for_unknown_geometry():
    response = client.post(
        "/geometry/999999/midsurface",
        json={"face_id_a": 1, "face_id_b": 2},
    )
    assert response.status_code == 404
