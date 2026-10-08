"""Faz 2.5b — cfMesh (cartesianMesh): snappyHexMesh'e seçilebilir ikinci mesh'leyici.

Docker'sız: tünel kutusu + gövde tek STL (kapalı, dışa bakan normaller),
``meshDict`` (snappy ayarlarıyla aynı anlam), /cfd/mesh ``mesher: cfmesh``
(sahte süreç; gerçek günlük parçaları ``fixtures/cfd``). Son test cfMesh
derlenmiş imajda küre tünelini mesh'ler; imajda cartesianMesh yoksa atlanır.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.api.cfd as cfd_api
import app.api.cfd_mesh as cfd_mesh_api
import app.api.cfd_runs as cfd_runs_api
import app.solvers.openfoam as of
from app.main import app
from app.mesh.cfd_mesher import SnappyParams, TunnelParams, _box_faces, cfmesh_dict, domain_stl, tunnel_box

FIX = Path(__file__).parent / "fixtures"
BBOX = (0.0, -0.05, -0.05, 0.1, 0.05, 0.05)


def _signed_volume(tris) -> float:
    v = 0.0
    for a, b, c in tris:
        v += (a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0]) + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6.0
    return v


@pytest.mark.parametrize("ground", [False, True])
def test_box_faces_closed_and_outward(ground):
    box = tunnel_box(BBOX, TunnelParams(base_cell_m=0.05, ground=ground))
    faces = _box_faces(box, ground)
    assert set(faces) == ({"inlet", "outlet", "sides", "ground"} if ground else {"inlet", "outlet", "sides"})
    tris = [t for ts in faces.values() for t in ts]
    assert len(tris) == 12
    vol = (box.hi[0] - box.lo[0]) * (box.hi[1] - box.lo[1]) * (box.hi[2] - box.lo[2])
    assert _signed_volume(tris) == pytest.approx(vol)  # dışa bakan normaller → pozitif hacim
    text = domain_stl(box, ground, "solid body\nendsolid body\n")
    assert text.splitlines().count("solid inlet") == 1 and text.endswith("endsolid body\n")


def test_cfmesh_dict_maps_snappy_settings():
    box = tunnel_box(BBOX, TunnelParams(base_cell_m=0.08))
    p = SnappyParams(surface_level_max=3, wake_level=1, n_layers=4, expansion_ratio=1.15)
    text = cfmesh_dict(box, BBOX, ["burun", "govde"], ground=True, base_cell_m=0.08, p=p)
    assert 'surfaceFile "constant/triSurface/domain.stl";' in text
    assert "maxCellSize 0.08;" in text
    assert '"(burun|govde)"\n    {\n        cellSize 0.01;' in text  # 0.08 / 2³
    assert "type        box;" in text and "cellSize    0.04;" in text  # iz kutusu 0.08 / 2¹
    assert "nLayers 4;" in text and "thicknessRatio 1.15;" in text
    assert "ground\n        {\n            type    wall;" in text
    assert "burun\n        {\n            type    wall;" in text
    assert "inlet\n        {\n            type    patch;" in text
    bare = cfmesh_dict(box, BBOX, ["body"], ground=False, base_cell_m=0.08, p=SnappyParams(wake_level=0, n_layers=0))
    assert "objectRefinements" not in bare and "boundaryLayers" not in bare and "ground" not in bare


def _fake_docker(image, case_dir, script):
    case = Path(case_dir)
    if "cartesianMesh" in script:
        (case / "constant" / "polyMesh").mkdir(parents=True, exist_ok=True)
        (case / "constant" / "polyMesh" / "owner").write_text("sahte")
        (case / "log.cartesianMesh").write_text((FIX / "cfd" / "cartesianMesh_sphere.log").read_text())
        (case / "log.checkMesh").write_text((FIX / "cfd" / "checkMesh_sphere_cfmesh.log").read_text())
        return [sys.executable, "-c", "print('MESH_EXIT=0')"]
    log = "Time = 1\n\nGAMG:  Solving for p, Initial residual = 1, Final residual = 0.1, No Iterations 3\n\nSIMPLE solution converged in 1 iterations\n\nEnd\n"
    code = f"import sys, pathlib\npathlib.Path({str(case)!r}, 'log.simpleFoam').write_text({log!r})\nsys.stdout.write({log!r})\n"
    return [sys.executable, "-c", code]


def _fake_missing(image, case_dir, script):
    case = Path(case_dir)
    (case / "log.cartesianMesh").write_text("bash: line 1: cartesianMesh: command not found\n")
    return [sys.executable, "-c", "print('MESH_EXIT=127')"]


@pytest.fixture
def api(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENFOAM_DOCKER_IMAGE", "fake/openfoam:test")
    monkeypatch.setattr(cfd_api, "CFD_DIR", tmp_path / "cfd")
    monkeypatch.setattr(cfd_runs_api, "CFD_DIR", tmp_path / "cfd")
    monkeypatch.setattr(cfd_mesh_api, "CFD_MESH_DIR", tmp_path / "meshes")
    monkeypatch.setattr(of, "docker_command", _fake_docker)
    monkeypatch.setattr(cfd_mesh_api, "docker_command", _fake_docker)
    client = TestClient(app)
    up = client.post("/geometry/upload", files={"file": ("box.step", (FIX / "box.step").read_bytes(), "application/octet-stream")})
    assert up.status_code == 200, up.text
    return client, up.json()["geometry_id"]


def test_api_cfmesh_mesh_then_solve(api):
    client, gid = api
    m = client.post(
        "/cfd/mesh",
        json={"geometry_id": gid, "mesher": "cfmesh", "tunnel": {"base_cell_m": 0.005}, "snappy": {"stl_size_mm": 2.5}, "wait": True},
    ).json()
    assert m["status"] == "meshed", m
    assert m["mesher"] == "cfmesh" and m["cfmesh"]["finished"] is True and m["cfmesh"]["layer_cells_added"] == 2720
    assert m["check"]["cells"] == 17094 and m["check"]["mesh_ok"] is True
    case_dir = Path(m["case_dir"])
    assert (case_dir / "system" / "meshDict").is_file() and (case_dir / "constant" / "triSurface" / "domain.stl").is_file()
    assert not (case_dir / "system" / "snappyHexMeshDict").exists()
    case = {
        "nu_m2_s": 1.5e-5,
        "patches": [
            {"name": "inlet", "kind": "inlet", "velocity_m_s": [10, 0, 0]},
            {"name": "outlet", "kind": "outlet"},
            {"name": "sides", "kind": "slip"},
            {"name": "body", "kind": "wall"},
        ],
    }
    s = client.post("/cfd/solve", json={"case": case, "mesh_id": m["mesh_id"], "wait": True}).json()
    assert s["status"] == "solved", s
    assert client.get(f"/cfd/runs/{s['run_id']}").json()["mesh_kind"] == "cfmesh"


def test_api_cfmesh_missing_binary_message(api, monkeypatch):
    client, gid = api
    monkeypatch.setattr(cfd_mesh_api, "docker_command", _fake_missing)
    m = client.post("/cfd/mesh", json={"geometry_id": gid, "mesher": "cfmesh", "tunnel": {"base_cell_m": 0.005}, "wait": True}).json()
    assert m["status"] == "failed" and "cartesianMesh" in m["message"]


def _cfmesh_image(image: str | None) -> bool:
    exe = shutil.which("docker")
    if not image or exe is None:
        return False
    r = subprocess.run([exe, "run", "--rm", image, "bash", "-c", "command -v cartesianMesh"], capture_output=True, text=True)
    return r.returncode == 0 and "cartesianMesh" in r.stdout


@pytest.mark.skipif(
    not _cfmesh_image(os.environ.get("OPENFOAM_DOCKER_IMAGE")),
    reason="OPENFOAM_DOCKER_IMAGE cfMesh içermiyor (backend/docker/openfoam)",
)
def test_sphere_tunnel_cfmesh_in_docker(monkeypatch, tmp_path):
    import gmsh

    step = tmp_path / "sphere.step"
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("s")
        gmsh.model.occ.addSphere(0, 0, 0, 50)
        gmsh.model.occ.synchronize()
        gmsh.write(str(step))
    finally:
        gmsh.finalize()
    monkeypatch.setattr(cfd_mesh_api, "CFD_MESH_DIR", tmp_path / "meshes")
    client = TestClient(app)
    gid = client.post("/geometry/upload", files={"file": ("sphere.step", step.read_bytes(), "application/octet-stream")}).json()["geometry_id"]
    m = client.post(
        "/cfd/mesh",
        json={"geometry_id": gid, "mesher": "cfmesh", "tunnel": {"base_cell_m": 0.05}, "snappy": {"surface_level_max": 3, "n_layers": 3, "stl_size_mm": 5}, "wait": True},
    ).json()
    assert m["status"] == "meshed", m["message"]
    assert m["check"]["mesh_ok"] is True and m["check"]["cells"] > 5000
    assert set(m["check"]["patch_faces"]) == {"inlet", "outlet", "sides", "body"}
