"""Faz 2.4 — kuvvet / moment / katsayı okuma ve ``cfd_runs`` koşu kaydı.

Docker'sız: case yazıcının kuvvet blokları, çıktı okuyucu (gerçek v2412 biçimi),
API üzerinden kayıt + liste + karşılaştırma + dışlama (sahte süreç). Son test
gerçek imajda pitzDaily duvarlarında kuvvet okur; imaj yoksa atlanır.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import app.api.cfd as cfd_api
import app.api.cfd_runs as cfd_runs_api
import app.solvers.openfoam as of
from app.main import app
from app.solvers.openfoam_case import CfdCaseParams, case_files

PATCHES = [
    {"name": "inlet", "kind": "inlet", "velocity_m_s": [10, 0, 0]},
    {"name": "outlet", "kind": "outlet"},
    {"name": "upperWall", "kind": "wall"},
    {"name": "lowerWall", "kind": "wall"},
    {"name": "frontAndBack", "kind": "empty"},
]
FORCES = {"patches": ["upperWall", "lowerWall"], "u_ref_m_s": 10, "l_ref_m": 0.0254, "a_ref_m2": 2.54e-5, "average_last": 3}

COEFF_DAT = (
    "# Force and moment coefficients\n"
    "# Time        \tCd            \tCd(f)         \tCd(r)         \tCl            \tCl(f)         \tCl(r)         "
    "\tCmPitch       \tCmRoll        \tCmYaw         \tCs            \tCs(f)         \tCs(r)         \n"
    + "".join(
        f"{i}            \t{cd:.6e}\t0\t0\t{cl:.6e}\t0\t0\t{0.5:.6e}\t0\t0\t0\t0\t0\n"
        for i, cd, cl in ((1, 0.40, -0.10), (2, 0.30, -0.08), (3, 0.26, -0.06), (4, 0.27, -0.06), (5, 0.25, -0.05))
    )
)
FORCE_DAT = (
    "# Time        \ttotal_x total_y total_z\tpressure_x pressure_y pressure_z\tviscous_x viscous_y viscous_z\n"
    "5             3.366914e-04 -7.646383e-05 0 2.775803e-04 -7.620857e-05 0 5.911119e-05 -2.552590e-07 0\n"
)
MOMENT_DAT = FORCE_DAT.replace("3.366914e-04 -7.646383e-05 0", "0 0 -1.595327e-05")


def _write_force_output(case_dir: Path) -> None:
    pp = case_dir / "postProcessing"
    (pp / "coeffs" / "0").mkdir(parents=True, exist_ok=True)
    (pp / "coeffs" / "0" / "coefficient.dat").write_text(COEFF_DAT)
    for tag in ("total", "upperWall", "lowerWall"):
        d = pp / f"forces_{tag}" / "0"
        d.mkdir(parents=True, exist_ok=True)
        (d / "force.dat").write_text(FORCE_DAT)
        (d / "moment.dat").write_text(MOMENT_DAT)


def test_case_writer_force_blocks():
    cd = case_files(CfdCaseParams(nu_m2_s=1e-5, rho_kg_m3=1.2, patches=PATCHES, forces=FORCES))["system/controlDict"]
    assert "type            forceCoeffs;" in cd
    assert "patches         (upperWall lowerWall);" in cd
    assert "rhoInf          1.2;" in cd and "Aref            2.54e-05;" in cd
    assert "forces_total" in cd and "forces_upperWall" in cd and "forces_lowerWall" in cd
    one = case_files(CfdCaseParams(nu_m2_s=1e-5, patches=PATCHES, forces={**FORCES, "patches": ["upperWall"]}))
    assert "forces_upperWall" not in one["system/controlDict"]  # tek yamada yalnız toplam
    with pytest.raises(ValidationError, match="yok"):
        CfdCaseParams(nu_m2_s=1e-5, patches=PATCHES, forces={**FORCES, "patches": ["govde"]})
    with pytest.raises(ValidationError, match="drag_dir"):
        CfdCaseParams(nu_m2_s=1e-5, patches=PATCHES, forces={**FORCES, "drag_dir": [0, 0, 0]})


def test_read_forces_last_mean_std_and_components(tmp_path):
    _write_force_output(tmp_path)
    s, c = of.read_forces(tmp_path, average_last=3)
    assert s["Cd"] == pytest.approx(0.25) and s["Cl"] == pytest.approx(-0.05)
    assert s["Cd_mean"] == pytest.approx((0.26 + 0.27 + 0.25) / 3)
    assert s["Cd_std"] == pytest.approx(0.008165, rel=1e-3)
    assert s["coeff_average_window"] == 3
    assert s["force_total_x"] == pytest.approx(3.366914e-4)
    assert s["force_total_pressure_x"] == pytest.approx(2.775803e-4)
    assert s["force_upperWall_viscous_x"] == pytest.approx(5.911119e-5)
    assert s["moment_total_z"] == pytest.approx(-1.595327e-5)
    assert c["force_coeffs"]["iteration"] == [1, 2, 3, 4, 5]
    assert c["force_coeffs"]["Cd"][0] == pytest.approx(0.40)


LOG = "Time = 1\n\nGAMG:  Solving for p, Initial residual = 1, Final residual = 0.1, No Iterations 3\n\nSIMPLE solution converged in 1 iterations\n\nEnd\n"


@pytest.fixture
def fake_run(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENFOAM_DOCKER_IMAGE", "fake/openfoam:test")
    monkeypatch.setattr(cfd_api, "CFD_DIR", tmp_path)
    monkeypatch.setattr(cfd_runs_api, "CFD_DIR", tmp_path)

    def fake_cmd(image, case_dir, script):
        _write_force_output(Path(case_dir))
        code = (
            "import sys, pathlib\n"
            f"t = {LOG!r}\n"
            f"pathlib.Path({str(case_dir)!r}, 'log.simpleFoam').write_text(t)\n"
            "sys.stdout.write(t)\n"
        )
        return [sys.executable, "-c", code]

    monkeypatch.setattr(of, "docker_command", fake_cmd)
    return tmp_path


def test_api_forces_cda_and_run_record(fake_run):
    client = TestClient(app)
    case = {"nu_m2_s": 1e-5, "patches": PATCHES, "forces": FORCES}
    d = client.post("/cfd/solve", json={"case": case, "block_mesh_dict": "x", "wait": True, "name": "test-2.4"}).json()
    assert d["status"] == "solved", d
    assert d["scalars"]["CdA_m2"] == pytest.approx(0.25 * 2.54e-5)
    assert d["scalars"]["CdA_mean_m2"] == pytest.approx(d["scalars"]["Cd_mean"] * 2.54e-5)
    rid = d["run_id"]
    run = client.get(f"/cfd/runs/{rid}").json()
    assert run["status"] == "solved" and run["name"] == "test-2.4" and run["mesh_kind"] == "block_mesh_dict"
    assert run["application"] == "simpleFoam" and run["turbulence"] == "laminar"
    assert run["request"]["forces"]["a_ref_m2"] == pytest.approx(2.54e-5)
    assert run["scalars"]["Cd"] == pytest.approx(0.25)
    assert run["curves"]["force_coeffs"]["Cd"][-1] == pytest.approx(0.25)
    listed = client.get("/cfd/runs").json()
    assert any(r["id"] == rid for r in listed["runs"])
    cmp = client.get("/cfd/runs/compare", params={"ids": f"{rid}"}).json()
    assert cmp["runs"][0]["curves"]["residuals"]["p"] == [1.0]
    patched = client.patch(f"/cfd/runs/{rid}", json={"excluded": True, "exclude_reason": "deneme"}).json()
    assert patched["excluded"] is True and patched["exclude_reason"] == "deneme"
    assert all(r["id"] != rid for r in client.get("/cfd/runs", params={"include_excluded": False}).json()["runs"])
    assert client.get("/cfd/runs/999999999").status_code == 404
    assert client.get("/cfd/runs/compare", params={"ids": "a"}).status_code == 422


def _docker_ready(image: str | None) -> bool:
    exe = shutil.which("docker")
    if not image or exe is None:
        return False
    return subprocess.run([exe, "image", "inspect", image], capture_output=True).returncode == 0


@pytest.mark.skipif(
    not _docker_ready(os.environ.get("OPENFOAM_DOCKER_IMAGE")),
    reason="OPENFOAM_DOCKER_IMAGE tanımlı değil ya da imaj yok",
)
def test_forces_on_pitzdaily_walls_in_docker(monkeypatch, tmp_path):
    image = os.environ["OPENFOAM_DOCKER_IMAGE"].strip()
    bmd = subprocess.run(
        [shutil.which("docker") or "docker", "run", "--rm", image, "bash", "-c",
         "cat $FOAM_TUTORIALS/incompressible/simpleFoam/pitzDaily/system/blockMeshDict"],
        capture_output=True, text=True, check=True,
    ).stdout
    monkeypatch.setattr(cfd_api, "CFD_DIR", tmp_path)
    monkeypatch.setattr(cfd_runs_api, "CFD_DIR", tmp_path)
    case = {
        "nu_m2_s": 1e-5,
        "patches": PATCHES,
        "turbulence": {"model": "kOmegaSST", "length_scale_m": 0.0025},
        "forces": {**FORCES, "average_last": 50},
    }
    d = TestClient(app).post("/cfd/solve", json={"case": case, "block_mesh_dict": bmd, "wait": True}).json()
    assert d["status"] == "solved", d["message"]
    s = d["scalars"]
    for key in ("Cd", "Cd_mean", "Cd_std", "Cl", "force_total_x", "force_upperWall_x", "force_lowerWall_x", "moment_total_z"):
        assert key in s
    # toplam = yamaların toplamı
    assert s["force_total_x"] == pytest.approx(s["force_upperWall_x"] + s["force_lowerWall_x"], rel=1e-4)
