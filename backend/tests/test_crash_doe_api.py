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
def test_current_job_while_case_runs(monkeypatch):
    """1.25a2 — çözücülü örnek koşarken GET çalışan işi (job_id, örnek no) verir; bitince None."""
    import app.api.crash as crash_api
    from app.doe import crash_runner

    seen: list[dict] = []

    def fake_complete(job_id: str) -> None:
        # koşu sırasında: bellekteki çalışan iş + HTTP cevabı
        study_id = next(iter(crash_runner._CURRENT))
        snap = client.get(f"/crash/doe/studies/{study_id}").json()
        seen.append({"job_id": job_id, "cur": crash_runner.current_job(study_id), "http": snap})
        meta = crash_api._read_job(job_id)
        meta.update(status="solved", message="sahte çözüm", solver_ran=True)
        crash_api._write_job(meta)

    monkeypatch.setattr(crash_api, "resolve_openradioss", lambda: "openradioss")
    monkeypatch.setattr(crash_api, "_complete_crash_job", fake_complete)
    body = _spec(base={"template_id": "crash_box_shell", "run_solver": True, "t_end_ms": 2.0})
    s = client.post("/crash/doe/studies", params={"wait": True}, json=body).json()

    assert len(seen) == 2
    for i, rec in enumerate(seen):
        assert rec["cur"] == {"case_index": s["cases"][i]["index"], "job_id": rec["job_id"]}
        assert rec["http"]["current_job_id"] == rec["job_id"]
        assert rec["http"]["current_case_index"] == s["cases"][i]["index"]
        running = [c for c in rec["http"]["cases"] if c["status"] == "running"]
        assert [c["index"] for c in running] == [s["cases"][i]["index"]]
    # bittikten sonra: çalışan iş yok, örnekler işin son durumunu aldı
    assert s["status"] == "completed" and s["counts"] == {"solved": 2}
    assert s["current_job_id"] is None and s["current_case_index"] is None
    assert all(c["message"] == "sahte çözüm" for c in s["cases"])


@requires_db
def test_invalid_spec_and_missing_study():
    assert client.post("/crash/doe/studies", json=_spec(vary={"geometry.nope": [1, 2]})).status_code == 422
    assert client.post("/crash/doe/studies", json=_spec(vary={"speed_m_s": [5, 5]})).status_code == 422
    assert client.get("/crash/doe/studies/999999").status_code == 404


@requires_db
def test_corpus_study_filter():
    """1.19c-3 — korpus yalnız seçilen DOE çalışmasının koşularını alır."""
    from app.ml.crash.corpus import load_crash_corpus, load_records
    from app.models.crash_run import CrashRun

    s = client.post("/crash/doe/studies", params={"wait": True}, json=_spec(n_samples=3)).json()
    other = client.post("/crash/scenario", json={"run_solver": False, "name": "elle"}).json()
    doe_ids = sorted(c["run_id"] for c in s["cases"])
    all_ids = set(doe_ids) | {other["crash"]["run_id"]}

    db = SessionLocal()
    try:
        # çözücüsüz koşuları "solved" + hedef skaleriyle işaretle (korpus yalnız solved alır)
        for run in db.query(CrashRun).filter(CrashRun.id.in_(all_ids)):
            run.status = "solved"
            run.scalars = {"rwall_force_max": 100.0, "internal_energy_final": 50.0}
        db.commit()

        assert all_ids <= {r.run_id for r in load_records(db)}
        assert sorted(r.run_id for r in load_records(db, study_id=s["id"])) == doe_ids
        c = load_crash_corpus(db, "crash_box_shell", "rigid_wall", curves_loader=lambda _j: {}, study_id=s["id"])
        assert sorted(c.run_ids) == doe_ids and c.summary()["study_id"] == s["id"]
        assert "req.barrier.speed_m_s" in c.feature_names and "geom.wall" in c.feature_names
    finally:
        db.close()
