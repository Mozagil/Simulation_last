"""1.21e-1 — POST /crash/import/dyna: yükle → çevir → rapor (koşu yok)."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.api import crash_import
from app.main import app
from tests.test_dyna_setup import BASE, SETUP

UNITS = {"length_to_mm": "1000", "mass_to_kg": "1", "time_to_s": "1"}


def _post(client: TestClient, files, **form):
    return client.post("/crash/import/dyna", files=files, data={**UNITS, **form})


def test_import_report_and_saved_params(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(crash_import, "IMPORT_DIR", tmp_path)
    client = TestClient(app)
    main = "*KEYWORD\n*INCLUDE\nkurulum.k\n" + BASE
    files = [
        ("main", ("model.k", main.encode(), "text/plain")),
        ("includes", ("kurulum.k", SETUP.encode(), "text/plain")),
    ]
    r = _post(client, files, rates_per_s="10, 100")
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["parse"]["files"] == ["model.k", "kurulum.k"]
    assert rep["mesh"]["shells"] == 2
    assert rep["rates_per_s"] == [10.0, 100.0]
    assert [p["law"] for p in rep["materials"]["parts"]] == ["plastic", "plastic"]
    targets = {row["target"] for row in rep["setup"]["rows"]}
    assert {"/INTER/TYPE7", "/INTER/TYPE24", "/BCS", "/INIVEL/TRA", "/RWALL/PLANE", "/GRAV"} <= targets
    saved = tmp_path / rep["import_id"] / "import.json"
    assert saved.is_file()
    assert client.get(f"/crash/import/dyna/{rep['import_id']}").json() == rep
    prev = client.get(f"/crash/import/dyna/{rep['import_id']}/preview").json()
    assert prev["part_faces"] == {"1": 1, "2": 1}
    assert prev["bbox_mm"]["max"] == [100.0, 100.0, 50.0]


def test_bad_input_is_422_and_cleans_up(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(crash_import, "IMPORT_DIR", tmp_path)
    client = TestClient(app)
    bad = "*NODE\n1, 0, 0, 0\n1, 1, 0, 0\n"
    r = _post(client, [("main", ("bozuk.k", bad.encode(), "text/plain"))])
    assert r.status_code == 422 and "ikinci kez" in r.json()["detail"]
    assert list(tmp_path.iterdir()) == []
    r = _post(client, [("main", ("model.inp", b"*NODE", "text/plain"))])
    assert r.status_code == 422
    r = client.post(
        "/crash/import/dyna",
        files=[("main", ("a.k", BASE.encode(), "text/plain"))],
        data={**UNITS, "time_to_s": "0"},
    )
    assert r.status_code == 422 and "pozitif" in r.json()["detail"]
    assert client.get("/crash/import/dyna/../../etc").status_code == 404
    assert client.get(f"/crash/import/dyna/{'0' * 32}/preview").status_code == 404


def test_solve_import_writes_deck_and_records_run(tmp_path: Path, monkeypatch) -> None:
    """1.21e-2c — içe aktarılan model koşulur: deck adaptörden, koşu geometrisiz + import_id ile."""
    from tests.test_materials import _db_available

    monkeypatch.setattr(crash_import, "IMPORT_DIR", tmp_path)
    client = TestClient(app)
    files = [("main", ("model.k", ("*KEYWORD\n*INCLUDE\nkurulum.k\n" + BASE).encode(), "text/plain")),
             ("includes", ("kurulum.k", SETUP.encode(), "text/plain"))]
    imp = _post(client, files).json()["import_id"]

    r = client.post(f"/crash/import/dyna/{imp}/solve", json={"run_solver": False, "t_end_ms": 2.5, "name": "k deneme"})
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["status"] == "rad_only" and res["import_id"] == imp
    from app.api.crash import _job_dir, _read_job

    meta = _read_job(res["job_id"])
    assert meta["import_id"] == imp and meta["geometry_id"] is None and meta["t_end_ms"] == 2.5
    starter = (_job_dir(res["job_id"]) / "crash_0000.rad").read_text(encoding="utf-8")
    assert "/INTER/TYPE7" in starter and "/INTER/TYPE24" in starter and "/RWALL" in starter
    if _db_available():
        assert res["run_id"] is not None
        run = client.get(f"/crash/runs/{res['run_id']}").json()
        assert run["import_id"] == imp and run["geometry_id"] is None and run["name"] == "k deneme"


def test_solve_import_needs_end_time_and_valid_id(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(crash_import, "IMPORT_DIR", tmp_path)
    client = TestClient(app)
    imp = _post(client, [("main", ("a.k", BASE.encode(), "text/plain"))]).json()["import_id"]
    r = client.post(f"/crash/import/dyna/{imp}/solve", json={"run_solver": False})
    assert r.status_code == 422 and "CONTROL_TERMINATION" in r.json()["detail"]
    assert client.post(f"/crash/import/dyna/{'0' * 32}/solve", json={}).status_code == 404
