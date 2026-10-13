"""Faz 2.2 — OpenFOAM koşusu + canlı ilerleme: adaptör ``submit`` ve /cfd API.

Docker'sız testler sahte bir süreç (python betiği simpleFoam log'u basar)
kullanır. Son test gerçek imajda pitzDaily ağıyla uçtan uca koşar;
OPENFOAM_DOCKER_IMAGE yoksa atlanır.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

import app.api.cfd as cfd_api
import app.solvers.openfoam as of
from app.main import app
from app.solvers.base import InputArtifact, SolverError

FAKE_LOG = """\
Starting time loop

Time = 1

smoothSolver:  Solving for Ux, Initial residual = 1, Final residual = 0.05, No Iterations 1
GAMG:  Solving for p, Initial residual = 1, Final residual = 0.06, No Iterations 17
ExecutionTime = 0.05 s

Time = 2

smoothSolver:  Solving for Ux, Initial residual = 0.4, Final residual = 0.03, No Iterations 5
GAMG:  Solving for p, Initial residual = 0.05, Final residual = 0.004, No Iterations 15
ExecutionTime = 0.1 s

SIMPLE solution converged in 2 iterations

End
"""

CASE = {
    "nu_m2_s": 1e-5,
    "patches": [
        {"name": "inlet", "kind": "inlet", "velocity_m_s": [10, 0, 0]},
        {"name": "outlet", "kind": "outlet"},
        {"name": "upperWall", "kind": "wall"},
        {"name": "lowerWall", "kind": "wall"},
        {"name": "frontAndBack", "kind": "empty"},
    ],
    "control": {"iterations": 4},
}


def _fake_docker(log_text: str, exit_code: int = 0):
    """docker_command yerine: log'u basan ve log.simpleFoam'a yazan python süreci."""

    def make(image, case_dir, script):
        code = (
            "import sys, pathlib\n"
            f"text = {log_text!r}\n"
            f"pathlib.Path({str(case_dir)!r}, 'log.simpleFoam').write_text(text)\n"
            "sys.stdout.write(text)\n"
            f"sys.exit({exit_code})\n"
        )
        return [sys.executable, "-c", code]

    return make


@pytest.fixture
def fake_openfoam(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENFOAM_DOCKER_IMAGE", "fake/openfoam:test")
    monkeypatch.setattr(of, "docker_command", _fake_docker(FAKE_LOG))
    monkeypatch.setattr(cfd_api, "CFD_DIR", tmp_path)
    return tmp_path


def test_submit_streams_progress_and_parses_residuals(fake_openfoam, tmp_path):
    adapter = of.OpenFoamAdapter()
    art = adapter.build_input({"output_dir": str(tmp_path / "c"), "case": CASE})
    seen: list[int] = []
    handle = adapter.submit(art, progress_cb=lambda log: seen.append(log.last_iteration))
    assert seen[:2] == [1, 2]
    assert adapter.poll_status(handle).state == "done"
    res = adapter.parse_results(handle)
    assert res.scalars["iterations"] == 2 and res.scalars["converged"] == 1.0
    assert res.scalars["residual_final_p"] == pytest.approx(0.05)
    assert res.curves["residuals"]["Ux"] == [1.0, 0.4]


def test_submit_failure_and_missing_image(monkeypatch, tmp_path):
    adapter = of.OpenFoamAdapter()
    art = adapter.build_input({"output_dir": str(tmp_path / "c"), "case": CASE})
    monkeypatch.delenv("OPENFOAM_DOCKER_IMAGE", raising=False)
    with pytest.raises(SolverError, match="yapılandırılmamış"):
        adapter.submit(art)
    monkeypatch.setenv("OPENFOAM_DOCKER_IMAGE", "fake")
    monkeypatch.setattr(of, "docker_command", _fake_docker("Time = 1\n\n--> FOAM FATAL ERROR: \ncannot find patch\n\n", 1))
    with pytest.raises(SolverError, match="cannot find patch"):
        adapter.submit(InputArtifact(path=art.path, kind="directory"))


def test_case_application_from_control_dict(tmp_path):
    with pytest.raises(SolverError, match="controlDict yok"):
        of.case_application(tmp_path)
    of.OpenFoamAdapter().build_input({"output_dir": str(tmp_path), "case": CASE})
    assert of.case_application(tmp_path) == "simpleFoam"


def test_api_solve_wait_writes_job_and_snapshot(fake_openfoam):
    client = TestClient(app)
    r = client.post("/cfd/solve", json={"case": CASE, "block_mesh_dict": "FoamFile {}", "wait": True})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "solved" and "yakınsadı" in d["message"]
    job = fake_openfoam / d["job_id"]
    assert (job / "case" / "system" / "blockMeshDict").read_text() == "FoamFile {}"
    assert (job / "case" / "0" / "U").is_file()
    snap = client.get(f"/cfd/jobs/{d['job_id']}").json()
    assert snap["status"] == "solved" and snap["hub_state"] == "done"
    assert snap["curves"]["residuals"]["p"] == [1.0, 0.05]
    with client.websocket_connect(f"/cfd/jobs/{d['job_id']}/ws") as ws:
        msg = ws.receive_json()
        assert msg["state"] == "done" and msg["kind"] == "cfd"
    assert client.get("/cfd/jobs/yok").status_code == 404


def test_api_case_only_no_image_and_validation(monkeypatch, tmp_path):
    monkeypatch.setattr(cfd_api, "CFD_DIR", tmp_path)
    monkeypatch.delenv("OPENFOAM_DOCKER_IMAGE", raising=False)
    client = TestClient(app)
    r = client.post("/cfd/solve", json={"case": CASE, "block_mesh_dict": "x", "run_solver": False}).json()
    assert r["status"] == "case_only" and r["openfoam_available"] is False
    r = client.post("/cfd/solve", json={"case": CASE, "block_mesh_dict": "x"}).json()
    assert r["status"] == "failed" and "OPENFOAM_DOCKER_IMAGE" in r["message"]
    bad = {**CASE, "patches": [{"name": "w", "kind": "wall"}]}
    assert client.post("/cfd/solve", json={"case": bad, "block_mesh_dict": "x"}).status_code == 422
    assert client.post("/cfd/solve", json={"case": CASE, "block_mesh_dict": ""}).status_code == 422


def _docker_ready(image: str | None) -> bool:
    if not image or shutil.which("docker") is None:
        return False
    return subprocess.run(["docker", "image", "inspect", image], capture_output=True).returncode == 0


@pytest.mark.skipif(
    not _docker_ready(os.environ.get("OPENFOAM_DOCKER_IMAGE")),
    reason="OPENFOAM_DOCKER_IMAGE tanımlı değil ya da imaj yok",
)
def test_api_solve_pitzdaily_in_docker(monkeypatch, tmp_path):
    image = os.environ["OPENFOAM_DOCKER_IMAGE"].strip()
    bmd = subprocess.run(
        [shutil.which("docker") or "docker", "run", "--rm", image, "bash", "-c",
         "cat $FOAM_TUTORIALS/incompressible/simpleFoam/pitzDaily/system/blockMeshDict"],
        capture_output=True, text=True, check=True,
    ).stdout
    monkeypatch.setattr(cfd_api, "CFD_DIR", tmp_path)
    case = {**CASE, "turbulence": {"model": "kOmegaSST", "length_scale_m": 0.0025}, "control": {"iterations": 2000}}
    d = TestClient(app).post("/cfd/solve", json={"case": case, "block_mesh_dict": bmd, "wait": True}).json()
    assert d["status"] == "solved", d["message"]
    assert d["scalars"]["converged"] == 1.0 and d["scalars"]["iterations"] < 2000
