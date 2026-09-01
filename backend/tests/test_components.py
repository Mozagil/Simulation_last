"""Component / ürün ağacı endpoint testleri."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.db.session import SessionLocal
from app.main import app

client = TestClient(app)
FIXTURES = Path(__file__).parent / "fixtures"


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
def test_create_mesh_component_and_product_tree():
    fixtures = FIXTURES / "box.step"
    with fixtures.open("rb") as f:
        upload = client.post(
            "/geometry/upload",
            files={"file": ("box.step", f, "application/octet-stream")},
        )
    assert upload.status_code == 200
    geometry_id = upload.json()["geometry_id"]
    part_count = upload.json()["part_count"]

    materials = client.get("/materials").json()["materials"]
    material_id = next(m["id"] for m in materials if m["name"] == "S355")

    created = client.post(
        f"/geometry/{geometry_id}/components",
        json={
            "part_id": 0,
            "name": "BoxShell",
            "source": "mesh",
            "material_id": material_id,
            "property_kind": "shell",
            "thickness": 3.0,
        },
    )
    assert created.status_code == 200
    comp = created.json()["component"]
    assert comp["name"] == "BoxShell"
    assert comp["source"] == "mesh"
    assert comp["part_id"] == 0
    assert comp["material_name"] == "S355"
    assert comp["property_kind"] == "shell"
    assert comp["thickness"] == pytest.approx(3.0)

    tree = client.get(
        f"/geometry/{geometry_id}/product-tree",
        params={"part_count": part_count},
    )
    assert tree.status_code == 200
    body = tree.json()
    assert body["geometry_id"] == geometry_id
    assert body["item_count"] >= 1
    item0 = next(i for i in body["items"] if i["part_id"] == 0)
    assert item0["label"] == "PART_0"
    assert item0["material_name"] == "S355"
    assert item0["property_kind"] == "shell"
    assert item0["thickness"] == pytest.approx(3.0)
    assert item0["component"]["name"] == "BoxShell"

    patched = client.patch(
        f"/components/{comp['id']}",
        json={"thickness": 4.5},
    )
    assert patched.status_code == 200
    assert patched.json()["component"]["thickness"] == pytest.approx(4.5)
    assert patched.json()["component"]["material_name"] == "S355"


@requires_db
def test_ensure_default_components_skips_existing():
    fixtures = FIXTURES / "box.step"
    with fixtures.open("rb") as f:
        upload = client.post(
            "/geometry/upload",
            files={"file": ("box.step", f, "application/octet-stream")},
        )
    assert upload.status_code == 200
    geometry_id = upload.json()["geometry_id"]

    materials = client.get("/materials").json()["materials"]
    material_id = next(m["id"] for m in materials if m["name"] == "S355")

    first = client.post(
        f"/geometry/{geometry_id}/components/defaults",
        json={
            "part_ids": [0],
            "property_kind": "shell",
            "thickness": 3.0,
            "material_id": material_id,
        },
    )
    assert first.status_code == 200
    assert first.json()["created_count"] == 1
    assert first.json()["components"][0]["name"] == "COMP_PART_0"
    assert first.json()["components"][0]["thickness"] == pytest.approx(3.0)

    second = client.post(
        f"/geometry/{geometry_id}/components/defaults",
        json={
            "part_ids": [0],
            "property_kind": "shell",
            "thickness": 9.0,
            "material_id": material_id,
        },
    )
    assert second.status_code == 200
    assert second.json()["created_count"] == 0
    assert second.json()["skipped_count"] == 1

    tree = client.get(f"/geometry/{geometry_id}/product-tree")
    assert tree.status_code == 200
    item0 = next(i for i in tree.json()["items"] if i["part_id"] == 0)
    assert item0["component"]["name"] == "COMP_PART_0"
    assert item0["thickness"] == pytest.approx(3.0)
    assert item0["material_name"] == "S355"
