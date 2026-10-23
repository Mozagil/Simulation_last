"""Faz 5.2a — POST /mbd/solve ve GET /mbd/jobs/{id}. Chrono koşusu taklit edilir."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.main import app
from app.solvers.base import InputArtifact, JobHandle

client = TestClient(app)

_CSV = "time_s,body_acc_m_s2,susp_force_n\n0,0,-3924\n0.001,2.5,-3900\n"


def _fake_submit(self, artifact: InputArtifact, *, timeout_s: float = 600.0) -> JobHandle:
    case = json.loads((artifact.path / "chrono_case.json").read_text(encoding="utf-8"))
    (artifact.path / "results.csv").write_text(_CSV, encoding="utf-8")
    (artifact.path / "summary.json").write_text('{"steps": 2, "wall_s": 0.01}', encoding="utf-8")
    (artifact.path / "exit_code").write_text("0", encoding="utf-8")
    return JobHandle(job_id=case["job_id"], work_dir=artifact.path, artifact=artifact)


def test_solve_returns_scalars_and_job_is_readable(monkeypatch, tmp_path):
    monkeypatch.setattr("app.api.mbd.MBD_DIR", tmp_path)
    monkeypatch.setattr("app.api.mbd.ChronoAdapter.submit", _fake_submit)
    res = client.post("/mbd/solve", json={"sprung_mass_kg": 350, "t_end_s": 0.5})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["state"] == "done"
    assert body["scalars"]["body_acc_m_s2_max"] == 2.5
    assert body["curves"]["time"] == [0.0, 0.001]
    assert body["diagnostics"]["summary"]["steps"] == 2
    case = json.loads((tmp_path / body["job_id"] / "chrono_case.json").read_text(encoding="utf-8"))
    assert case["params"]["sprung_mass_kg"] == 350

    again = client.get(f"/mbd/jobs/{body['job_id']}")
    assert again.status_code == 200
    assert again.json()["scalars"]["susp_force_n_min"] == -3924.0


def test_solve_without_runtime_is_503(monkeypatch, tmp_path):
    monkeypatch.setattr("app.api.mbd.MBD_DIR", tmp_path)
    monkeypatch.delenv("CHRONO_PYTHON", raising=False)
    monkeypatch.delenv("CHRONO_DOCKER_IMAGE", raising=False)
    res = client.post("/mbd/solve", json={})
    assert res.status_code == 503
    assert "CHRONO_PYTHON" in res.json()["detail"]


def test_solve_rejects_bad_params():
    res = client.post("/mbd/solve", json={"sprung_mass_kg": 0})
    assert res.status_code == 422


def test_unknown_job_is_404(monkeypatch, tmp_path):
    monkeypatch.setattr("app.api.mbd.MBD_DIR", tmp_path)
    assert client.get("/mbd/jobs/yok").status_code == 404
    assert client.get("/mbd/jobs/../chrono_case").status_code == 404
