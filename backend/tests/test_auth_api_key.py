"""Bearer API anahtarı (WeWeb): kapı, kapsam, sahiplik.

Middleware doğrudan `SessionLocal` kullanır → testler gerçek (cae_test)
veritabanını ister; ulaşılamıyorsa atlanır.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.auth import generate_key, hash_key
from app.db.session import SessionLocal
from app.main import app
from app.models.geometry import Geometry
from app.models.user import User


def _db_ok() -> bool:
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _db_ok(), reason="DB yok")
client = TestClient(app)


NAMES = ("auth-test-a", "auth-test-b")


def _cleanup(db) -> None:
    """Önce sahipliği kaldır (FK), sonra kullanıcıyı sil; geometri/run kalır (anonim)."""
    ids = [u.id for u in db.query(User).filter(User.name.in_(NAMES))]
    if ids:
        db.query(Geometry).filter(Geometry.owner_id.in_(ids)).update(
            {Geometry.owner_id: None}, synchronize_session=False
        )
        db.query(User).filter(User.id.in_(ids)).delete(synchronize_session=False)
    db.commit()


@pytest.fixture()
def two_users():
    db = SessionLocal()
    keys = {}
    try:
        _cleanup(db)
        for name in NAMES:
            k = generate_key()
            db.add(User(name=name, api_key_hash=hash_key(k)))
            keys[name] = k
        db.commit()
        yield keys
        _cleanup(db)
    finally:
        db.close()


def _h(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def test_anahtar_yoksa_anonim_devam_ve_gecersiz_anahtar_401(two_users):
    assert client.get("/health").status_code == 200
    assert client.get("/templates").status_code == 200  # kapı kapalı: anonim
    r = client.get("/templates", headers=_h("cae_yanlis"))
    assert r.status_code == 401 and "geçersiz" in r.json()["detail"]


def test_auth_required_kapisi(two_users, monkeypatch):
    monkeypatch.setenv("AUTH_REQUIRED", "1")
    assert client.get("/health").status_code == 200
    assert client.get("/templates").status_code == 401
    assert client.get("/templates", headers=_h(two_users["auth-test-a"])).status_code == 200


def test_geometri_sahibine_baglanir_ve_baskasi_404_alir(two_users):
    ka, kb = two_users["auth-test-a"], two_users["auth-test-b"]
    r = client.post("/templates/cantilever_beam/create", json={"params": {}}, headers=_h(ka))
    assert r.status_code == 200, r.text
    gid = r.json()["geometry_id"]

    db = SessionLocal()
    try:
        geo = db.get(Geometry, gid)
        owner = db.query(User).filter(User.name == "auth-test-a").one()
        assert geo.owner_id == owner.id
    finally:
        db.close()

    assert client.get(f"/geometry/{gid}/physical-groups", headers=_h(ka)).status_code == 200
    assert client.get(f"/geometry/{gid}/physical-groups", headers=_h(kb)).status_code == 404
    # Anonim (kapı kapalı) da sahipli geometriyi göremez.
    assert client.get(f"/geometry/{gid}/physical-groups").status_code == 404


def test_run_listesi_kullaniciya_gore_suzulur(two_users):
    ka, kb = two_users["auth-test-a"], two_users["auth-test-b"]
    r = client.post("/templates/cantilever_beam/create", json={"params": {}}, headers=_h(ka))
    gid = r.json()["geometry_id"]
    mats = client.get("/materials").json()["materials"]
    client.post("/materials/assignments", json={"geometry_id": gid, "part_id": 0, "material_id": mats[0]["id"]}, headers=_h(ka))
    client.post(f"/geometry/{gid}/mesh", json={"element_size": 25.0, "dimension": 3}, headers=_h(ka))
    solve = client.post(f"/geometry/{gid}/solve", json={
        "dimension": 3, "run_solver": False, "name": "auth-run",
        "bcs": [{"type": "fixed", "region": "ankastre_uc"},
                {"type": "cload", "region": "yuk_yuzeyi", "fy": -100.0}],
    }, headers=_h(ka))
    assert solve.status_code == 200, solve.text
    rid = solve.json()["run_id"]
    ids_a = {x["id"] for x in client.get("/geometry/runs", headers=_h(ka)).json()["runs"]}
    ids_b = {x["id"] for x in client.get("/geometry/runs", headers=_h(kb)).json()["runs"]}
    assert rid in ids_a and rid not in ids_b
