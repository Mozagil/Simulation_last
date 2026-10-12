"""Faz 3.1 — kompozit ply kütüphanesi (composite_materials)."""

import uuid

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from fastapi import FastAPI

from app.api.composite import router as composite_router
from app.db.session import SessionLocal

app = FastAPI()
app.include_router(composite_router)
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


def _create_body(**over: object) -> dict:
    body = {
        "name": "UD-test",
        "density": 1600,
        "e1": 120e9,
        "e2": 9e9,
        "e3": 9e9,
        "nu12": 0.30,
        "nu13": 0.30,
        "nu23": 0.40,
        "g12": 5e9,
        "g13": 5e9,
        "g23": 3e9,
        "xt": 1400e6,
        "xc": 1100e6,
        "yt": 45e6,
        "yc": 180e6,
        "s12": 65e6,
    }
    body.update(over)
    return body


def test_create_request_rejects_nonpositive_e1():
    from app.api.composite import CreateCompositeMaterialRequest

    with pytest.raises(ValidationError):
        CreateCompositeMaterialRequest(**_create_body(e1=0))


@requires_db
def test_list_composite_materials_returns_ud_seed():
    response = client.get("/composite/materials")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] >= 2
    names = {m["name"] for m in body["materials"]}
    assert {"T300/epoxy", "E-glass/epoxy"}.issubset(names)

    t300 = next(m for m in body["materials"] if m["name"] == "T300/epoxy")
    assert t300["ply_kind"] == "ud"
    assert t300["category"] == "cfrp"
    assert t300["source"] == "library"
    assert t300["is_editable"] is False
    assert t300["e1"] == pytest.approx(135e9)
    assert t300["e2"] == pytest.approx(10e9)
    assert t300["xt"] == pytest.approx(1500e6)
    assert t300["s12"] == pytest.approx(70e6)
    assert t300["density"] == pytest.approx(1600.0)

    glass = next(m for m in body["materials"] if m["name"] == "E-glass/epoxy")
    assert glass["category"] == "gfrp"
    assert glass["e1"] == pytest.approx(41e9)


@requires_db
def test_create_user_composite_ply_and_duplicate_name():
    name = f"TestUD_{uuid.uuid4().hex[:8]}"
    payload = _create_body(name=name)
    response = client.post("/composite/materials", json=payload)
    assert response.status_code == 200
    mat = response.json()["material"]
    assert mat["name"] == name
    assert mat["source"] == "user_defined"
    assert mat["is_editable"] is True
    assert mat["ply_kind"] == "ud"
    assert mat["e1"] == pytest.approx(120e9)

    dup = client.post("/composite/materials", json=payload)
    assert dup.status_code == 409
