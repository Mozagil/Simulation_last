"""1.16a — crash_runs: /crash/solve kaydı, liste / detay / PATCH / compare, içe aktarma."""

from __future__ import annotations

import json
import uuid

from fastapi.testclient import TestClient

from app.api.crash_runs import CRASH_DIR, import_job_dirs
from app.db.session import SessionLocal
from app.main import app
from tests.test_crash_solve import _barrier, _clean_state, _upload_and_mesh_box  # noqa: F401 (autouse fixture)
from tests.test_materials import requires_db

client = TestClient(app)


def _solve(geometry_id: int, name: str) -> dict:
    r = client.post("/crash/solve", json={"geometry_id": geometry_id, "barrier": _barrier(), "name": name,
                                          "model": {"law": "elastic"}})
    assert r.status_code == 200, r.text
    return r.json()


def _put_curves(job_id: str, curves: dict, scalars: dict) -> None:
    p = CRASH_DIR / job_id / "job.json"
    meta = json.loads(p.read_text(encoding="utf-8"))
    meta.update(curves=curves, scalars=scalars, status="solved")
    p.write_text(json.dumps(meta), encoding="utf-8")


@requires_db
def test_solve_creates_run_with_input_snapshot():
    gid = _upload_and_mesh_box()
    body = _solve(gid, "a")
    assert body["run_id"] is not None
    runs = client.get("/crash/runs", params={"geometry_id": gid}).json()
    assert runs["count"] == 1 and runs["runs"][0]["job_id"] == body["job_id"]
    assert runs["runs"][0]["status"] == "rad_only" and runs["runs"][0]["name"] == "a"
    detail = client.get(f"/crash/runs/{body['run_id']}").json()
    assert detail["request"]["model"]["law"] == "elastic"
    assert detail["request"]["barrier"]["speed_m_s"] == 10.0
    assert detail["materials_snapshot"][0]["part_id"] == 0  # o anki atama
    assert client.get("/crash/runs/999999").status_code == 404


@requires_db
def test_patch_and_exclude_filter():
    gid = _upload_and_mesh_box()
    rid = _solve(gid, "deneme")["run_id"]
    r = client.patch(f"/crash/runs/{rid}", json={"name": "yeni ad", "excluded": True, "exclude_reason": "kurulum hatası"})
    assert r.status_code == 200 and r.json()["excluded"] is True and r.json()["exclude_reason"] == "kurulum hatası"
    assert client.get("/crash/runs", params={"geometry_id": gid, "include_excluded": False}).json()["count"] == 0
    back = client.patch(f"/crash/runs/{rid}", json={"excluded": False}).json()
    assert back["excluded"] is False and back["exclude_reason"] is None and back["name"] == "yeni ad"


@requires_db
def test_compare_returns_force_curves_side_by_side():
    gid = _upload_and_mesh_box()
    a, b = _solve(gid, "a"), _solve(gid, "b")
    _put_curves(a["job_id"], {"time": [0, 1], "rwall_force": [0, 5], "internal_energy": [0, 1]}, {"rwall_force_max": 5})
    _put_curves(b["job_id"], {"time": [0, 2, 4], "rwall_force": [0, 7, 0], "section_1_force": [0, 3, 0]}, {"rwall_force_max": 7})
    # skalerler job.json'dan değil DB'den: kayıt güncellensin
    from app.api.crash_runs import record_from_meta

    db = SessionLocal()
    try:
        for j in (a, b):
            record_from_meta(db, json.loads((CRASH_DIR / j["job_id"] / "job.json").read_text(encoding="utf-8")))
    finally:
        db.close()
    res = client.get("/crash/runs/compare", params={"ids": f"{a['run_id']},{b['run_id']}"}).json()["runs"]
    assert [r["name"] for r in res] == ["a", "b"]
    assert res[0]["curves"] == {"rwall_force": [0, 5], "time": [0, 1]}  # yalnız *_force + time
    assert set(res[1]["curves"]) == {"rwall_force", "section_1_force", "time"}
    assert res[1]["scalars"]["rwall_force_max"] == 7
    only = client.get("/crash/runs/compare", params={"ids": str(a["run_id"]), "curves": "internal_energy"}).json()
    assert only["runs"][0]["curves"] == {"internal_energy": [0, 1], "time": [0, 1]}
    assert client.get("/crash/runs/compare", params={"ids": "x"}).status_code == 422
    # 1.17e2: varsayılan CFC kuvvet + ivme bileşkesini de getirir, enerjiyi getirmez
    _put_curves(a["job_id"], {"time": [0, 1], "rwall_force": [0, 5], "rwall_force_cfc600": [0, 4],
                              "acc_g": [0, 9], "acc_g_cfc1000": [0, 2], "internal_energy": [0, 1]}, {})
    got = client.get("/crash/runs/compare", params={"ids": str(a["run_id"])}).json()["runs"][0]["curves"]
    assert set(got) == {"time", "rwall_force", "rwall_force_cfc600", "acc_g", "acc_g_cfc1000"}


@requires_db
def test_import_job_dirs_idempotent(tmp_path):
    gid = _upload_and_mesh_box()
    ok, gone = str(uuid.uuid4()), str(uuid.uuid4())
    for jid, g in ((ok, gid), (gone, 987654321)):
        (tmp_path / jid).mkdir()
        (tmp_path / jid / "job.json").write_text(
            json.dumps({"job_id": jid, "geometry_id": g, "status": "solved", "name": "eski",
                        "scalars": {"rwall_force_max": 1.0}, "model": {"law": "plastic"}}),
            encoding="utf-8",
        )
    (tmp_path / "bozuk").mkdir()
    (tmp_path / "bozuk" / "job.json").write_text("{", encoding="utf-8")
    db = SessionLocal()
    try:
        assert import_job_dirs(db, tmp_path) == {"imported": 1, "updated": 0, "skipped_no_geometry": 1, "unreadable": 1}
        assert import_job_dirs(db, tmp_path)["updated"] == 1
    finally:
        db.close()
    runs = client.get("/crash/runs", params={"geometry_id": gid}).json()["runs"]
    assert len(runs) == 1 and runs[0]["job_id"] == ok and runs[0]["scalars"] == {"rwall_force_max": 1.0}
    assert client.get(f"/crash/runs/{runs[0]['id']}").json()["request"] == {"model": {"law": "plastic"}}

