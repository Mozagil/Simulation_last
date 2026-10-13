"""Faz 2.3 — parametrik 2B kanal (blockMesh) + laminer Poiseuille doğrulaması.

Birim testleri Docker'sız: blockMeshDict metni, analitik değerler, izleme
fonksiyonu çıktısının okunması, API'de kanal + referans karşılaştırması
(sahte süreç). Son test gerçek imajda koşar (V-C1); OPENFOAM_DOCKER_IMAGE
yoksa atlanır.
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
import app.solvers.openfoam as of
from app.main import app
from app.mesh.cfd_blockmesh import ChannelMeshParams, channel_block_mesh_dict, channel_patches, poiseuille_reference
from app.solvers.openfoam_case import CfdCaseParams, case_files

MESH = {"length_m": 0.2, "height_m": 0.01, "nx": 200, "ny": 20}


def test_channel_block_mesh_dict_patches_and_cells():
    m = ChannelMeshParams(**MESH)
    text = channel_block_mesh_dict(m)
    assert "hex (0 1 2 3 4 5 6 7) (200 20 1) simpleGrading (1 1 1)" in text
    assert "(0.2 0.01 0.0005)" in text  # 2B derinlik = H / ny
    for name, typ in (("inlet", "patch"), ("outlet", "patch"), ("walls", "wall"), ("frontAndBack", "empty")):
        assert f"    {name}\n    {{\n        type {typ};" in text
    assert m.cell_count == 4000


def test_channel_grading_3d_and_validation():
    m = ChannelMeshParams(**{**MESH, "two_d": False, "nz": 4, "depth_m": 0.02, "wall_grading": 4})
    text = channel_block_mesh_dict(m)
    assert "simpleGrading (1 ((0.5 0.5 4) (0.5 0.5 0.25)) 1)" in text
    assert "frontAndBack\n    {\n        type wall;" in text
    with pytest.raises(ValidationError, match="nz = 1"):
        ChannelMeshParams(**{**MESH, "nz": 2})


def test_poiseuille_reference_values():
    ref = poiseuille_reference(ChannelMeshParams(**MESH), 0.01, 1e-5)
    assert ref["re"] == pytest.approx(10.0)
    assert ref["dpdx_kinematic"] == pytest.approx(12 * 1e-5 * 0.01 / 0.01**2)
    assert ref["dp_kinematic"] == pytest.approx(ref["dpdx_kinematic"] * 0.2)
    assert ref["u_max_m_s"] == pytest.approx(0.015)
    assert ref["entrance_length_m"] == pytest.approx(0.005)


def test_case_writer_monitor_functions():
    m = ChannelMeshParams(**MESH)
    params = CfdCaseParams(nu_m2_s=1e-5, patches=channel_patches(m, 0.01), monitor_patches=["inlet", "outlet"])
    cd = case_files(params)["system/controlDict"]
    assert "pAvg_inlet" in cd and "pAvg_outlet" in cd and "uMax" in cd
    assert "operation       areaAverage;" in cd and "type            fieldMinMax;" in cd
    with pytest.raises(ValidationError, match="İzlenen yama"):
        CfdCaseParams(nu_m2_s=1e-5, patches=channel_patches(m, 0.01), monitor_patches=["yok"])


def _write_post(case_dir: Path, p_in: float, u_max: float) -> None:
    for name, val in (("inlet", p_in), ("outlet", 0.0)):
        d = case_dir / "postProcessing" / f"pAvg_{name}" / "0"
        d.mkdir(parents=True, exist_ok=True)
        (d / "surfaceFieldValue.dat").write_text(
            f"# Region type : patch {name}\n# Time        \tareaAverage(p)\n1           \t9.9e-01\n643           \t{val:.6e}\n"
        )
    d = case_dir / "postProcessing" / "uMax" / "0"
    d.mkdir(parents=True, exist_ok=True)
    (d / "fieldMinMax.dat").write_text(
        "# Field minima and maxima\n# Time        \tfield         \tmin           \tlocation(min) \tmax           \tlocation(max) \n"
        f"643           \tmag(U)        \t0.000000e+00\t(0 0 0)\t{u_max:.6e}\t(0.01 0.005 0)\n"
    )


def test_read_monitors_last_row(tmp_path):
    _write_post(tmp_path, 2.468686e-3, 1.492888e-2)
    got = of.read_monitors(tmp_path)
    assert got == {"p_avg_inlet": pytest.approx(2.468686e-3), "p_avg_outlet": 0.0, "u_max": pytest.approx(1.492888e-2)}
    assert of.read_monitors(tmp_path / "yok") == {}


LOG = "Time = 1\n\nGAMG:  Solving for p, Initial residual = 1, Final residual = 0.1, No Iterations 3\n\nSIMPLE solution converged in 1 iterations\n\nEnd\n"


def test_api_channel_reference_comparison(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENFOAM_DOCKER_IMAGE", "fake/openfoam:test")
    monkeypatch.setattr(cfd_api, "CFD_DIR", tmp_path)

    def fake_cmd(image, case_dir, script):
        _write_post(Path(case_dir), 2.468686e-3, 1.492888e-2)
        code = (
            "import sys, pathlib\n"
            f"t = {LOG!r}\n"
            f"pathlib.Path({str(case_dir)!r}, 'log.simpleFoam').write_text(t)\n"
            "sys.stdout.write(t)\n"
        )
        return [sys.executable, "-c", code]

    monkeypatch.setattr(of, "docker_command", fake_cmd)
    m = ChannelMeshParams(**MESH)
    case = {"nu_m2_s": 1e-5, "rho_kg_m3": 1000, "patches": channel_patches(m, 0.01), "monitor_patches": ["inlet", "outlet"]}
    d = TestClient(app).post("/cfd/solve", json={"case": case, "channel": MESH, "wait": True}).json()
    assert d["status"] == "solved", d
    assert d["scalars"]["dp_kinematic"] == pytest.approx(2.468686e-3)
    assert d["scalars"]["dp_pa"] == pytest.approx(2.468686)
    ref = d["reference"]
    assert ref["kind"] == "poiseuille_2d"
    assert ref["diff_percent"]["dp_kinematic"] == pytest.approx(100 * (2.468686e-3 - 2.4e-3) / 2.4e-3)
    assert ref["diff_percent"]["u_max_m_s"] == pytest.approx(100 * (1.492888e-2 - 0.015) / 0.015)
    bmd = (tmp_path / d["job_id"] / "case" / "system" / "blockMeshDict").read_text()
    assert "(200 20 1)" in bmd


def test_api_channel_validation(monkeypatch, tmp_path):
    monkeypatch.setattr(cfd_api, "CFD_DIR", tmp_path)
    client = TestClient(app)
    m = ChannelMeshParams(**MESH)
    case = {"nu_m2_s": 1e-5, "patches": channel_patches(m, 0.01)}
    assert client.post("/cfd/solve", json={"case": case}).status_code == 422  # mesh yok
    both = {"case": case, "channel": MESH, "block_mesh_dict": "x"}
    assert client.post("/cfd/solve", json=both).status_code == 422
    bad = {**case, "patches": [*channel_patches(m, 0.01)[:3], {"name": "yan", "kind": "empty"}]}
    r = client.post("/cfd/solve", json={"case": bad, "channel": MESH})
    assert r.status_code == 422 and "yan" in r.text


def _docker_ready(image: str | None) -> bool:
    exe = shutil.which("docker")
    if not image or exe is None:
        return False
    return subprocess.run([exe, "image", "inspect", image], capture_output=True).returncode == 0


@pytest.mark.skipif(
    not _docker_ready(os.environ.get("OPENFOAM_DOCKER_IMAGE")),
    reason="OPENFOAM_DOCKER_IMAGE tanımlı değil ya da imaj yok",
)
def test_v_c1_poiseuille_channel_in_docker(monkeypatch, tmp_path):
    """V-C1: Re = 10 laminer kanal. Δp girişteki gelişme bölgesini de içerir."""
    monkeypatch.setattr(cfd_api, "CFD_DIR", tmp_path)
    m = ChannelMeshParams(**MESH)
    case = {
        "nu_m2_s": 1e-5,
        "patches": channel_patches(m, 0.01),
        "monitor_patches": ["inlet", "outlet"],
        "control": {"iterations": 5000, "write_interval": 5000, "residual_p": 1e-6, "residual_u": 1e-6},
    }
    d = TestClient(app).post("/cfd/solve", json={"case": case, "channel": MESH, "wait": True}).json()
    assert d["status"] == "solved", d["message"]
    diff = d["reference"]["diff_percent"]
    assert abs(diff["dp_kinematic"]) < 5.0
    assert abs(diff["u_max_m_s"]) < 2.0
