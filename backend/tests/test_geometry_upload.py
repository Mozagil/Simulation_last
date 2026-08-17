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
