"""Faz 3.5 — GET/PUT /composite/layups."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

import pytest

from app.api.composite import PutLayupRequest, router as composite_router
from app.db.session import SessionLocal
from app.models.composite import CompositeMaterial
from app.models.geometry import Geometry

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


def _plies(material_id: int, angles: list[float], t: float = 0.125) -> list[dict]:
    return [
        {"material_id": material_id, "thickness_mm": t, "angle_deg": a} for a in angles
    ]


def test_put_request_rejects_empty_plies():
    with pytest.raises(ValidationError):
        PutLayupRequest(geometry_id=1, part_id=0, plies=[])


def test_put_request_rejects_nonpositive_thickness():
    with pytest.raises(ValidationError):
        PutLayupRequest(
            geometry_id=1,
            part_id=0,
            plies=[{"material_id": 1, "thickness_mm": 0, "angle_deg": 0}],
        )


@requires_db
def test_put_and_get_layup_roundtrip():
    db = SessionLocal()
    try:
        geo = Geometry(
            original_filename="layup-test.step",
            current_filename="layup-test.step",
        )
        db.add(geo)
        db.commit()
        db.refresh(geo)
        geometry_id = geo.id
        t300 = (
            db.query(CompositeMaterial)
            .filter(CompositeMaterial.name == "T300/epoxy")
            .one()
        )
        glass = (
            db.query(CompositeMaterial)
            .filter(CompositeMaterial.name == "E-glass/epoxy")
            .one()
        )
        material_id = t300.id
        glass_id = glass.id
    finally:
        db.close()

    created = client.put(
        "/composite/layups",
        json={
            "geometry_id": geometry_id,
            "part_id": 0,
            "plies": _plies(material_id, [0.0, 90.0, 0.0]),
        },
    )
    assert created.status_code == 200, created.text
    layup = created.json()["layup"]
    assert layup["geometry_id"] == geometry_id
    assert layup["part_id"] == 0
    assert layup["n_plies"] == 3
    assert [p["angle_deg"] for p in layup["plies"]] == [0.0, 90.0, 0.0]
    assert layup["plies"][0]["material_name"] == "T300/epoxy"
    assert layup["plies"][0]["thickness_mm"] == pytest.approx(0.125)

    listed = client.get("/composite/layups", params={"geometry_id": geometry_id})
    assert listed.status_code == 200
    body = listed.json()
    assert body["count"] == 1
    assert body["layups"][0]["n_plies"] == 3

    replaced = client.put(
        "/composite/layups",
        json={
            "geometry_id": geometry_id,
            "part_id": 0,
            "plies": _plies(glass_id, [45.0, -45.0]),
        },
    )
    assert replaced.status_code == 200
    assert replaced.json()["layup"]["n_plies"] == 2
    assert replaced.json()["layup"]["plies"][0]["material_name"] == "E-glass/epoxy"
    assert [p["angle_deg"] for p in replaced.json()["layup"]["plies"]] == [45.0, -45.0]

    filtered = client.get(
        "/composite/layups",
        params={"geometry_id": geometry_id, "part_id": 0},
    )
    assert filtered.status_code == 200
    assert filtered.json()["count"] == 1
    empty_part = client.get(
        "/composite/layups",
        params={"geometry_id": geometry_id, "part_id": 9},
    )
    assert empty_part.status_code == 200
    assert empty_part.json()["count"] == 0


@requires_db
def test_put_unknown_geometry_and_material():
    missing_geo = client.put(
        "/composite/layups",
        json={
            "geometry_id": 2_147_000_000,
            "part_id": 0,
            "plies": [{"material_id": 1, "thickness_mm": 0.125, "angle_deg": 0}],
        },
    )
    assert missing_geo.status_code == 404
    assert client.get(
        "/composite/layups", params={"geometry_id": 2_147_000_000}
    ).status_code == 404

    db = SessionLocal()
    try:
        geo = Geometry(
            original_filename="layup-missing-mat.step",
            current_filename="layup-missing-mat.step",
        )
        db.add(geo)
        db.commit()
        db.refresh(geo)
        geometry_id = geo.id
    finally:
        db.close()

    missing_mat = client.put(
        "/composite/layups",
        json={
            "geometry_id": geometry_id,
            "part_id": 0,
            "plies": [
                {"material_id": 2_147_000_000, "thickness_mm": 0.125, "angle_deg": 0}
            ],
        },
    )
    assert missing_mat.status_code == 404
    assert "Ply" in missing_mat.json()["detail"]
