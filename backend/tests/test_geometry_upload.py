import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.geometry import UPLOAD_DIR
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clean_upload_dir():
    """Her testten önce/sonra uploads/ klasörünü temizle, testler birbirini etkilemesin."""
    yield
    if UPLOAD_DIR.exists():
        shutil.rmtree(UPLOAD_DIR)


def test_upload_step_file_saves_to_disk():
    fake_step_content = b"ISO-10303-21;\nHEADER;\nENDSEC;\nEND-ISO-10303-21;\n"
    response = client.post(
        "/geometry/upload",
        files={"file": ("part.step", fake_step_content, "application/octet-stream")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["original_filename"] == "part.step"
    assert body["size_bytes"] == str(len(fake_step_content))

    saved_path = Path(body["path"])
    assert saved_path.exists()
    assert saved_path.read_bytes() == fake_step_content


def test_upload_iges_file_is_accepted():
    response = client.post(
        "/geometry/upload",
        files={"file": ("part.iges", b"dummy content", "application/octet-stream")},
    )
    assert response.status_code == 200


def test_upload_rejects_unsupported_extension():
    response = client.post(
        "/geometry/upload",
        files={"file": ("part.txt", b"not a cad file", "text/plain")},
    )
    assert response.status_code == 400
    assert "Desteklenmeyen dosya uzantısı" in response.json()["detail"]
