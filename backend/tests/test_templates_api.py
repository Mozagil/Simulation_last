"""Şablon API testleri (0.4.3) + köken kolonları."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.api.geometry import UPLOAD_DIR
from app.db.session import SessionLocal
from app.main import app
from tests.db_guard import safe_cleanup

client = TestClient(app)


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
    if not _db_available():
        return
    safe_cleanup(
        UPLOAD_DIR,
        "TRUNCATE material_assignments, physical_groups, geometries "
        "RESTART IDENTITY CASCADE",
    )


def test_list_templates_includes_cantilever_schema():
    response = client.get("/templates")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] >= 1
    ids = [t["id"] for t in body["templates"]]
    assert "cantilever_beam" in ids
    assert "simply_supported_beam" in ids
    beam = next(t for t in body["templates"] if t["id"] == "cantilever_beam")
    assert beam["has_analytic"] is True
    assert set(beam["params_schema"]["properties"]) == {"length", "thickness", "width"}
    region_names = {r["name"] for r in beam["regions"]}
    assert region_names == {"ankastre_uc", "yuk_yuzeyi"}


def test_create_unknown_template_is_404():
    response = client.post("/templates/yok/create", json={"params": {}})
    assert response.status_code == 404


@requires_db
def test_create_cantilever_persists_template_origin_and_tessellates():
    response = client.post(
        "/templates/cantilever_beam/create",
        json={"params": {"length": 400, "thickness": 12, "width": 40}},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["template_id"] == "cantilever_beam"
    assert body["template_params"]["length"] == 400.0
    assert body["face_count"] == 6
    assert body["regions"]["ankastre_uc"]
    assert (UPLOAD_DIR / body["current_filename"]).exists()

    step = client.get(f"/geometry/{body['geometry_id']}/step")
    assert step.status_code == 200
    assert len(step.content) > 100
    assert "ISO-10303" in step.content.decode("ascii", errors="ignore")[:40]


@requires_db
def test_create_invalid_params_is_422():
    response = client.post(
        "/templates/cantilever_beam/create",
        json={"params": {"length": 10, "thickness": 10}},
    )
    assert response.status_code == 422


@requires_db
def test_uploaded_step_has_null_template_origin():
    from pathlib import Path as P

    box = P(__file__).parent / "fixtures" / "box.step"
    upload = client.post(
        "/geometry/upload",
        files={"file": ("box.step", box.read_bytes(), "application/octet-stream")},
    )
    assert upload.status_code == 200
    geo_id = upload.json()["geometry_id"]
    db = SessionLocal()
    try:
        from app.models.geometry import Geometry

        geo = db.get(Geometry, geo_id)
        assert geo is not None
        assert geo.template_id is None
        assert geo.template_params is None
    finally:
        db.close()
