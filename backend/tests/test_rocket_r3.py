"""R3 — roket rüzgâr tüneli: serbest akım sınırı, katsayılar, basınç merkezi.

Docker'sız: ``rocket_aero`` (bilinen kuvvet/momentten), case yazıcının
``farfield`` yaması, /cfd/rocket/solve (sahte mesh + sahte çözüm çıktısı).
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.api.cfd as cfd_api
import app.api.cfd_mesh as cfd_mesh_api
import app.api.cfd_runs as cfd_runs_api
import app.solvers.openfoam as of
from app.main import app
from app.postprocess.rocket_aero import freestream, rocket_aero, speed_of_sound
from app.solvers.openfoam_case import CfdCaseParams, case_files

FIX = Path(__file__).parent / "fixtures"


def test_freestream_and_speed_of_sound():
    u = freestream(50.0, 4.0)
    assert u[0] == pytest.approx(50 * math.cos(math.radians(4))) and u[2] == pytest.approx(50 * math.sin(math.radians(4)))
    assert speed_of_sound(288.15) == pytest.approx(340.3, abs=0.1)


def test_rocket_aero_coefficients_and_cp():
    d, rho, v, alpha = 0.1, 1.225, 50.0, 4.0
    q = 0.5 * rho * v * v
    area = math.pi * d * d / 4
    fx, fz = 0.35 * q * area, 0.75 * q * area
    x_ref, x_cp = 0.9, 1.18
    my = -(x_cp - x_ref) * fz  # M_y = −(x_cp − x_ref)·F_z
    a = rocket_aero(
        {"force_total_x": fx, "force_total_z": fz, "moment_total_y": my},
        speed_m_s=v, alpha_deg=alpha, rho_kg_m3=rho, diameter_m=d, x_ref_m=x_ref, cg_given=True,
    )
    r = math.radians(alpha)
    assert a["CA"] == pytest.approx(0.35) and a["CN"] == pytest.approx(0.75)
    assert a["CD"] == pytest.approx(0.35 * math.cos(r) + 0.75 * math.sin(r))
    assert a["CL"] == pytest.approx(0.75 * math.cos(r) - 0.35 * math.sin(r))
    assert a["x_cp_m"] == pytest.approx(x_cp) and a["stability_calibers"] == pytest.approx((x_cp - x_ref) / d)
    assert a["CN_alpha_per_rad"] == pytest.approx(0.75 / r)
    zero = rocket_aero({"force_total_x": fx, "force_total_z": 0.0, "moment_total_y": 0.0},
                       speed_m_s=v, alpha_deg=0.0, rho_kg_m3=rho, diameter_m=d, x_ref_m=0.0, cg_given=False)
    assert "x_cp_m" not in zero and "stability_calibers" not in zero
    assert rocket_aero({}, speed_m_s=v, alpha_deg=alpha, rho_kg_m3=rho, diameter_m=d, x_ref_m=0, cg_given=False) == {}


def test_farfield_patch_files():
    u = list(freestream(50.0, 4.0))
    params = CfdCaseParams(
        nu_m2_s=1.46e-5,
        patches=[{"name": "inlet", "kind": "farfield", "velocity_m_s": u}, {"name": "burun", "kind": "wall"}],
        turbulence={"model": "kOmegaSST"},
    )
    f = case_files(params)
    assert "type            freestreamVelocity;" in f["0/U"] and "freestreamValue" in f["0/U"]
    assert "type            freestreamPressure;" in f["0/p"]
    assert "type            inletOutlet;" in f["0/k"] and "inletValue" in f["0/omega"]


# ------------------------------------------------------------------- API (sahte)

LOG = "Time = 1\n\nGAMG:  Solving for p, Initial residual = 1, Final residual = 0.1, No Iterations 3\n\nSIMPLE solution converged in 1 iterations\n\nEnd\n"
D, RHO, V, ALPHA, X_REF, X_CP = 0.1, 1.225, 50.0, 4.0, 0.9, 1.18
Q_A = 0.5 * RHO * V * V * math.pi * D * D / 4
FX, FZ = 0.35 * Q_A, 0.75 * Q_A
MY = -(X_CP - X_REF) * FZ


def _fake(image, case_dir, script):
    case = Path(case_dir)
    if "snappyHexMesh" in script:
        (case / "constant" / "polyMesh").mkdir(parents=True, exist_ok=True)
        (case / "constant" / "polyMesh" / "owner").write_text("sahte")
        (case / "log.snappyHexMesh").write_text((FIX / "cfd" / "snappy_sphere.log").read_text())
        (case / "log.checkMesh").write_text((FIX / "cfd" / "checkMesh_sphere.log").read_text())
        return [sys.executable, "-c", "print('MESH_EXIT=0')"]
    d = case / "postProcessing" / "forces_total" / "0"
    d.mkdir(parents=True, exist_ok=True)
    row = f"1 {FX} 0 {FZ} {FX} 0 {FZ} 0 0 0\n"
    (d / "force.dat").write_text("# Time total_x total_y total_z pressure_x pressure_y pressure_z viscous_x viscous_y viscous_z\n" + row)
    (d / "moment.dat").write_text("# Time total_x total_y total_z pressure_x pressure_y pressure_z viscous_x viscous_y viscous_z\n" + f"1 0 {MY} 0 0 {MY} 0 0 0 0\n")
    code = f"import sys, pathlib\npathlib.Path({str(case)!r}, 'log.simpleFoam').write_text({LOG!r})\nsys.stdout.write({LOG!r})\n"
    return [sys.executable, "-c", code]


def test_api_rocket_solve_fake(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENFOAM_DOCKER_IMAGE", "fake/openfoam:test")
    monkeypatch.setattr(cfd_api, "CFD_DIR", tmp_path / "cfd")
    monkeypatch.setattr(cfd_runs_api, "CFD_DIR", tmp_path / "cfd")
    monkeypatch.setattr(cfd_mesh_api, "CFD_MESH_DIR", tmp_path / "meshes")
    monkeypatch.setattr(of, "docker_command", _fake)
    monkeypatch.setattr(cfd_mesh_api, "docker_command", _fake)
    client = TestClient(app)
    gid = client.post("/templates/rocket/create", json={"params": {}}).json()["geometry_id"]
    m = client.post("/cfd/mesh", json={"geometry_id": gid, "tunnel": {"base_cell_m": 0.3}, "snappy": {"stl_size_mm": 20}, "wait": True}).json()
    assert m["status"] == "meshed", m
    r = client.post(
        "/cfd/rocket/solve",
        json={"mesh_id": m["mesh_id"], "speed_m_s": V, "alpha_deg": ALPHA, "cg_mm": X_REF * 1000, "wait": True},
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "solved" and d["mach"] == pytest.approx(V / speed_of_sound(288.15))
    a = d["rocket_aero"]
    assert a["CN"] == pytest.approx(0.75) and a["CA"] == pytest.approx(0.35)
    assert a["x_cp_m"] == pytest.approx(X_CP) and a["stability_calibers"] == pytest.approx(2.8)
    assert a["barrowman"]["x_cp_barrowman_m"] == pytest.approx(d["barrowman"]["x_cp_mm"] / 1000)
    run = client.get(f"/cfd/runs/{d['run_id']}").json()
    assert run["reference"]["kind"] == "rocket_r3" and run["request"]["rocket"]["alpha_deg"] == ALPHA
    # roket olmayan mesh reddedilir
    up = client.post("/geometry/upload", files={"file": ("box.step", (FIX / "box.step").read_bytes(), "application/octet-stream")})
    m2 = client.post("/cfd/mesh", json={"geometry_id": up.json()["geometry_id"], "tunnel": {"base_cell_m": 0.005}, "wait": True}).json()
    bad = client.post("/cfd/rocket/solve", json={"mesh_id": m2["mesh_id"], "speed_m_s": 10})
    assert bad.status_code == 422 and "roket" in bad.text
