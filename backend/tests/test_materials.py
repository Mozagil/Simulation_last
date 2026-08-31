"""Malzeme kütüphanesi endpoint testleri."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.db.session import SessionLocal
from app.main import app

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


@requires_db
def test_list_materials_returns_seeded_library():
    response = client.get("/materials")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] >= 5
    names = {m["name"] for m in body["materials"]}
    assert {"S235", "S355", "6061-T6"}.issubset(names)

    s355 = next(m for m in body["materials"] if m["name"] == "S355")
    assert s355["category"] == "steel"
    assert s355["source"] == "library"
    assert s355["youngs_modulus"] == pytest.approx(210e9)
    assert s355["yield_strength"] == pytest.approx(355e6)
    assert s355["density"] == pytest.approx(7850.0)


@requires_db
def test_assign_material_to_part_and_list():
    from pathlib import Path

    fixtures = Path(__file__).parent / "fixtures" / "box.step"
    with fixtures.open("rb") as f:
        upload = client.post(
            "/geometry/upload",
            files={"file": ("box.step", f, "application/octet-stream")},
        )
    assert upload.status_code == 200
    geometry_id = upload.json()["geometry_id"]

    materials = client.get("/materials").json()["materials"]
    material_id = next(m["id"] for m in materials if m["name"] == "6061-T6")

    assign = client.post(
        "/materials/assignments",
        json={
            "geometry_id": geometry_id,
            "part_id": 0,
            "material_id": material_id,
        },
    )
    assert assign.status_code == 200
    assignment = assign.json()["assignment"]
    assert assignment["part_id"] == 0
    assert assignment["material_id"] == material_id
    assert assignment["material_name"] == "6061-T6"

    # Aynı parçaya farklı malzeme → güncelle
    s355_id = next(m["id"] for m in materials if m["name"] == "S355")
    update = client.post(
        "/materials/assignments",
        json={
            "geometry_id": geometry_id,
            "part_id": 0,
            "material_id": s355_id,
        },
    )
    assert update.status_code == 200
    assert update.json()["assignment"]["material_name"] == "S355"

    listed = client.get(
        "/materials/assignments", params={"geometry_id": geometry_id}
    )
    assert listed.status_code == 200
    body = listed.json()
    assert body["count"] == 1
    assert body["assignments"][0]["material_name"] == "S355"


@requires_db
def test_create_user_material_and_estimated_sn():
    import uuid

    name = f"TestCustomSteel_{uuid.uuid4().hex[:8]}"
    response = client.post(
        "/materials",
        json={
            "name": name,
            "density": 7850,
            "youngs_modulus": 200e9,
            "poisson_ratio": 0.29,
            "yield_strength": 250e6,
            "ultimate_strength": 400e6,
            "sn_mode": "estimated",
        },
    )
    assert response.status_code == 200
    mat = response.json()["material"]
    assert mat["source"] == "user_defined"
    assert mat["is_editable"] is True
    assert mat["sn_curve"]["source"] == "estimated"

    sn = client.put(
        f"/materials/{mat['id']}/sn-curve",
        json={"source": "tested", "points": [{"N": 1e5, "sigma": 200e6}]},
    )
    assert sn.status_code == 200
    assert sn.json()["material"]["sn_curve"]["source"] == "tested"
