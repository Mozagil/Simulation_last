import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.geometry import UPLOAD_DIR
from app.main import app

client = TestClient(app)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
VALID_STEP_FILE = FIXTURES_DIR / "box.step"


@pytest.fixture(autouse=True)
def _clean_upload_dir():
    """Her testten önce/sonra uploads/ klasörünü temizle, testler birbirini etkilemesin."""
    yield
    if UPLOAD_DIR.exists():
        shutil.rmtree(UPLOAD_DIR)


def test_upload_step_file_saves_and_tessellates():
    content = VALID_STEP_FILE.read_bytes()
    response = client.post(
        "/geometry/upload",
        files={"file": ("box.step", content, "application/octet-stream")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["original_filename"] == "box.step"
    assert body["size_bytes"] == str(len(content))

    saved_path = Path(body["path"])
    assert saved_path.exists()
    assert saved_path.read_bytes() == content

    tessellation_path = Path(body["tessellation_path"])
    assert tessellation_path.exists()
    assert tessellation_path.suffix == ".stl"
    assert tessellation_path.stat().st_size > 0

    assert body["tessellation_url"] == f"/files/tessellations/{tessellation_path.stem}.stl"

    # Kutu 6 yüzeyden oluşur — her üçgen bu 6 yüzeyden birine ait olmalı.
    assert body["face_count"] == 6
    assert body["triangle_count"] > 0
    assert len(body["triangle_to_face"]) == body["triangle_count"]
    assert len(set(body["triangle_to_face"])) == 6

    disk_path = Path("uploads/tessellations") / Path(body["triangle_to_face_url"]).name
    assert disk_path.exists()

    # Tek parçalı bir dosya için part_count=1, tüm üçgenler part 0'a ait olmalı.
    assert body["part_count"] == 1
    assert len(body["triangle_to_part"]) == body["triangle_count"]
    assert set(body["triangle_to_part"]) == {0}

    part_disk_path = Path("uploads/tessellations") / Path(body["triangle_to_part_url"]).name
    assert part_disk_path.exists()


def test_upload_assembly_distinguishes_parts():
    """İki ayrı katıdan oluşan bir montaj dosyasında, üçgenler doğru parçaya
    atanmalı (ROADMAP dışı ek özellik — montaj/parça ayrımı desteği).
    """
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
    # İki kutu simetrik olduğu için üçgen sayıları eşit olmalı.
    part_0_count = body["triangle_to_part"].count(0)
    part_1_count = body["triangle_to_part"].count(1)
    assert part_0_count == part_1_count
    assert part_0_count + part_1_count == body["triangle_count"]

    # 2 parça x 6 yüzey = 12 benzersiz face tag.
    assert body["face_count"] == 12


def test_upload_rejects_unsupported_extension():
    response = client.post(
        "/geometry/upload",
        files={"file": ("part.txt", b"not a cad file", "text/plain")},
    )
    assert response.status_code == 400
    assert "Desteklenmeyen dosya uzantısı" in response.json()["detail"]


def test_upload_rejects_corrupt_step_file():
    corrupt_content = b"bu gecerli bir STEP dosyasi degil"
    response = client.post(
        "/geometry/upload",
        files={"file": ("bozuk.step", corrupt_content, "application/octet-stream")},
    )
    assert response.status_code == 422
    assert "Geometri okunamadı" in response.json()["detail"]


def test_list_surfaces_after_upload():
    content = VALID_STEP_FILE.read_bytes()
    upload_response = client.post(
        "/geometry/upload",
        files={"file": ("box.step", content, "application/octet-stream")},
    )
    stored_filename = upload_response.json()["stored_filename"]

    response = client.get(f"/geometry/{stored_filename}/surfaces")

    assert response.status_code == 200
    body = response.json()
    assert body["surface_count"] == 6
    assert len(body["surfaces"]) == 6

    surface = body["surfaces"][0]
    assert set(surface.keys()) == {"id", "area", "normal", "part_id"}
    assert surface["area"] == pytest.approx(100.0)
    assert len(surface["normal"]) == 3

    total_area = sum(s["area"] for s in body["surfaces"])
    assert total_area == pytest.approx(600.0)


def test_list_surfaces_returns_404_for_unknown_file():
    response = client.get("/geometry/nonexistent-file.step/surfaces")
    assert response.status_code == 404


def test_list_edges_after_upload():
    content = VALID_STEP_FILE.read_bytes()
    upload_response = client.post(
        "/geometry/upload",
        files={"file": ("box.step", content, "application/octet-stream")},
    )
    stored_filename = upload_response.json()["stored_filename"]

    response = client.get(f"/geometry/{stored_filename}/edges")

    assert response.status_code == 200
    body = response.json()
    assert body["edge_count"] == 12
    assert len(body["edges"]) == 12

    edge = body["edges"][0]
    assert set(edge.keys()) == {"id", "length", "part_id", "start_point", "end_point"}
    assert edge["length"] == pytest.approx(10.0)

    total_length = sum(e["length"] for e in body["edges"])
    assert total_length == pytest.approx(120.0)


def test_list_edges_returns_404_for_unknown_file():
    response = client.get("/geometry/nonexistent-file.step/edges")
    assert response.status_code == 404


def test_list_points_after_upload():
    content = VALID_STEP_FILE.read_bytes()
    upload_response = client.post(
        "/geometry/upload",
        files={"file": ("box.step", content, "application/octet-stream")},
    )
    stored_filename = upload_response.json()["stored_filename"]

    response = client.get(f"/geometry/{stored_filename}/points")

    assert response.status_code == 200
    body = response.json()
    assert body["point_count"] == 8
    assert len(body["points"]) == 8

    point = body["points"][0]
    assert set(point.keys()) == {"id", "coordinate", "part_id"}
    assert len(point["coordinate"]) == 3


def test_list_points_returns_404_for_unknown_file():
    response = client.get("/geometry/nonexistent-file.step/points")
    assert response.status_code == 404


def test_copy_surface_after_upload():
    content = VALID_STEP_FILE.read_bytes()
    upload_response = client.post(
        "/geometry/upload",
        files={"file": ("box.step", content, "application/octet-stream")},
    )
    stored_filename = upload_response.json()["stored_filename"]

    response = client.post(f"/geometry/{stored_filename}/surfaces/1/copy")

    assert response.status_code == 200
    body = response.json()
    assert body["original_face_id"] == 1
    assert body["new_face_id"] != 1
    assert body["new_face_id"] not in {1, 2, 3, 4, 5, 6}


def test_copy_surface_returns_404_for_unknown_file():
    response = client.post("/geometry/nonexistent-file.step/surfaces/1/copy")
    assert response.status_code == 404


def test_copy_surface_returns_404_for_unknown_face_id():
    content = VALID_STEP_FILE.read_bytes()
    upload_response = client.post(
        "/geometry/upload",
        files={"file": ("box.step", content, "application/octet-stream")},
    )
    stored_filename = upload_response.json()["stored_filename"]

    response = client.post(f"/geometry/{stored_filename}/surfaces/999/copy")
    assert response.status_code == 404
