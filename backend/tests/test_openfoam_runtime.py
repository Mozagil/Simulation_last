"""Faz 2.0 — OpenFOAM (ESI) çalışma ortamı: docker komutu ve log okuma.

Birim testleri Docker'sız koşar. Son test gerçek imajda resmi pitzDaily
vakasını koşturur; OPENFOAM_DOCKER_IMAGE tanımlı ve docker erişilebilir
değilse atlanır.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from app.solvers.openfoam import docker_command, parse_solver_log, resolve_openfoam_image

# simpleFoam pitzDaily log'undan kısaltılmış parça (v2412).
LOG = """\
SIMPLE: convergence criteria
    field p	 tolerance 0.01
Starting time loop

Time = 1

smoothSolver:  Solving for Ux, Initial residual = 1, Final residual = 0.0538101, No Iterations 1
smoothSolver:  Solving for Uy, Initial residual = 1, Final residual = 0.030925, No Iterations 2
GAMG:  Solving for p, Initial residual = 1, Final residual = 0.068427, No Iterations 17
GAMG:  Solving for p, Initial residual = 0.5, Final residual = 0.01, No Iterations 3
ExecutionTime = 0.05 s  ClockTime = 0 s

Time = 2

smoothSolver:  Solving for Ux, Initial residual = 0.437824, Final residual = 0.0308241, No Iterations 5
GAMG:  Solving for p, Initial residual = 0.052242, Final residual = 0.00424173, No Iterations 15
ExecutionTime = 0.11 s  ClockTime = 1 s

SIMPLE solution converged in 2 iterations

End
"""


def test_parse_solver_log_iterations_and_first_residual_per_field():
    log = parse_solver_log(LOG)
    assert log.iterations == [1, 2]
    assert log.last_iteration == 2
    # aynı iterasyonda p iki kez çözülse de ilki alınır
    assert log.initial_residuals["p"] == [1.0, 0.052242]
    assert log.initial_residuals["Ux"] == [1.0, 0.437824]
    assert log.initial_residuals["Uy"] == [1.0]
    assert log.converged and log.finished and log.fatal_error is None


def test_parse_solver_log_fatal_error():
    text = "Time = 1\n\n--> FOAM FATAL ERROR: (openfoam-2412)\ncannot find file \"0/U\"\n\n    From ...\n"
    log = parse_solver_log(text)
    assert not log.finished
    assert log.fatal_error is not None and "cannot find file" in log.fatal_error


def test_docker_command_mounts_case_and_cds_to_work(tmp_path):
    cmd = docker_command("opencfd/openfoam-default:2412", tmp_path, "blockMesh")
    assert Path(cmd[0]).stem == "docker" and cmd[1:3] == ["run", "--rm"]
    assert cmd[cmd.index("-v") + 1].endswith(":/work")
    # ESI giriş noktası ev klasörüne geçer — betik /work'e döner
    assert cmd[-3:] == ["bash", "-c", "cd /work && blockMesh"]


def test_resolve_image_from_env(monkeypatch):
    monkeypatch.delenv("OPENFOAM_DOCKER_IMAGE", raising=False)
    assert resolve_openfoam_image() is None
    monkeypatch.setenv("OPENFOAM_DOCKER_IMAGE", " opencfd/openfoam-default:2412 ")
    assert resolve_openfoam_image() == "opencfd/openfoam-default:2412"


def _docker_ready(image: str | None) -> bool:
    if not image or shutil.which("docker") is None:
        return False
    probe = subprocess.run(["docker", "image", "inspect", image], capture_output=True)
    return probe.returncode == 0


@pytest.mark.skipif(
    not _docker_ready(os.environ.get("OPENFOAM_DOCKER_IMAGE")),
    reason="OPENFOAM_DOCKER_IMAGE tanımlı değil ya da imaj yok",
)
def test_pitzdaily_smoke_runs_in_docker(tmp_path):
    from scripts.openfoam_smoke import run

    assert run(tmp_path, os.environ["OPENFOAM_DOCKER_IMAGE"].strip()) == 0
    log = parse_solver_log((tmp_path / "log.simpleFoam").read_text(errors="replace"))
    assert log.finished and log.converged
    assert log.initial_residuals["p"][-1] < 1e-2
