"""Faz 3.7 — GET/PUT /composite/orientations (paralel rozet + OSS)."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

import pytest

from app.api.composite import PutOrientationRequest, router as composite_router
from app.db.session import SessionLocal
from app.models import user as _user_model  # noqa: F401  (geometries.owner_id)
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


def _orientations_table() -> bool:
    if not _db_available():
        return False
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1 FROM composite_orientations LIMIT 0"))
        db.close()
        return True
    except Exception:
        return False


requires_db = pytest.mark.skipif(
    not _orientations_table(),
    reason="PostgreSQL veya composite_orientations yok (alembic upgrade head)",
)


def test_put_request_rejects_short_dir0():
    with pytest.raises(ValidationError):
        PutOrientationRequest(geometry_id=1, part_id=0, dir0=[1.0, 0.0])


def test_unit3_rejects_zero_and_normalizes():
    from fastapi import HTTPException

    from app.api.composite import _unit3

    with pytest.raises(HTTPException) as err:
        _unit3([0.0, 0.0, 0.0])
    assert err.value.status_code == 400
    assert "dir0" in err.value.detail
    assert _unit3([2.0, 0.0, 0.0]) == pytest.approx([1.0, 0.0, 0.0])


def test_put_faces_without_ids_rejected_when_geometry_missing_still_validates_shape():
    body = PutOrientationRequest(
        geometry_id=1, part_id=0, target="faces", face_ids=[]
    )
    assert body.target == "faces"
    assert body.face_ids == []


@requires_db
def test_put_and_get_parallel_rosette():
    db = SessionLocal()
    try:
        geo = Geometry(
            original_filename="rosette-test.step",
            current_filename="rosette-test.step",
        )
        db.add(geo)
        db.commit()
        db.refresh(geo)
        geometry_id = geo.id
    finally:
        db.close()

    zero = client.put(
        "/composite/orientations",
        json={
            "geometry_id": geometry_id,
            "part_id": 0,
            "dir0": [0, 0, 0],
            "target": "part",
        },
    )
    assert zero.status_code == 400
    assert "dir0" in zero.json()["detail"]

    faces_empty = client.put(
        "/composite/orientations",
        json={
            "geometry_id": geometry_id,
            "part_id": 0,
            "target": "faces",
            "face_ids": [],
        },
    )
    assert faces_empty.status_code == 400
    assert "face_ids" in faces_empty.json()["detail"]

    created = client.put(
        "/composite/orientations",
        json={
            "geometry_id": geometry_id,
            "part_id": 0,
            "kind": "parallel",
            "dir0": [2, 0, 0],
            "origin": [10, 0, 0],
            "target": "faces",
            "face_ids": [3, 5],
        },
    )
    assert created.status_code == 200, created.text
    ori = created.json()["orientation"]
    assert ori["kind"] == "parallel"
    assert ori["dir0"] == pytest.approx([1.0, 0.0, 0.0])
    assert ori["origin"] == pytest.approx([10.0, 0.0, 0.0])
    assert ori["target"] == "faces"
    assert ori["face_ids"] == [3, 5]

    listed = client.get(
        "/composite/orientations",
        params={"geometry_id": geometry_id, "part_id": 0},
    )
    assert listed.status_code == 200
    assert listed.json()["count"] == 1
    assert listed.json()["orientations"][0]["face_ids"] == [3, 5]
