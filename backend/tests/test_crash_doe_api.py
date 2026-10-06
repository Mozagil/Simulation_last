"""1.19c-2 — /crash/doe: çalışma oluştur, beklemeli koş (çözücüsüz), devam, liste."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models.crash_doe import CrashDoeStudy
from tests.test_crash_solve import _clean_state  # noqa: F401 (autouse temizlik)
from tests.test_materials import requires_db

client = TestClient(app)


@pytest.fixture(autouse=True)
def _drop_studies():
    yield
    db = SessionLocal()
    try:
        db.query(CrashDoeStudy).delete()
        db.commit()
    except Exception:  # noqa: BLE001 — DB yoksa testler zaten atlanır
        db.rollback()
    finally:
        db.close()


def _spec(**kw):
    body = {
        "name": "test-doe",
        "base": {"template_id": "crash_box_shell", "run_solver": False, "t_end_ms": 2.0},
        "vary": {"speed_m_s": [5.0, 15.0], "geometry.wall": [1.5, 3.0]},
        "n_samples": 2,
        "seed": 3,
    }
    body.update(kw)
    return body


@requires_db
def test_create_run_and_resume():
    r = client.post("/crash/doe/studies", params={"wait": True}, json=_spec())
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["template_id"] == "crash_box_shell" and s["n_cases"] == 2
    assert s["status"] == "completed" and s["counts"] == {"rad_only": 2}
    for c in s["cases"]:
        assert c["run_id"] is not None and c["geometry_id"] is not None
        run = client.get(f"/crash/runs/{c['run_id']}").json()
        assert run["name"] == f"DOE {s['id']} · {c['index']}"
        assert run["request"]["barrier"]["speed_m_s"] == pytest.approx(c["values"]["speed_m_s"])
        assert run["request"]["parts"][0]["thickness_mm"] == pytest.approx(c["values"]["geometry.wall"])

    # devam: bitmiş örnekler tekrar koşulmaz
    run_ids = [c["run_id"] for c in s["cases"]]
    again = client.post(f"/crash/doe/studies/{s['id']}/run", params={"wait": True}).json()
    assert [c["run_id"] for c in again["cases"]] == run_ids

    listed = client.get("/crash/doe/studies").json()["studies"]
    assert listed[0]["id"] == s["id"] and "cases" not in listed[0]
    assert client.get(f"/crash/doe/studies/{s['id']}").json()["counts"] == {"rad_only": 2}


@requires_db
def test_invalid_spec_and_missing_study():
    assert client.post("/crash/doe/studies", json=_spec(vary={"geometry.nope": [1, 2]})).status_code == 422
    assert client.post("/crash/doe/studies", json=_spec(vary={"speed_m_s": [5, 5]})).status_code == 422
    assert client.get("/crash/doe/studies/999999").status_code == 404
