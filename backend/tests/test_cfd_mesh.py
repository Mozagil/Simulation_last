"""Faz 2.5a — CFD mesh: STEP → bölge başına STL, sanal rüzgâr tüneli,
snappyHexMesh sözlükleri, checkMesh / snappy günlüğü okuma, /cfd/mesh API ve
/cfd/solve ``mesh_id``.

Docker'sız testler gerçek v2412 günlüklerinden alınmış parçaları
(``fixtures/cfd``) ve sahte süreci kullanır. Son test gerçek imajda küre
tünelini mesh'leyip çözer; OPENFOAM_DOCKER_IMAGE yoksa atlanır.
"""

from __future__ import annotations

import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import app.api.cfd as cfd_api
import app.api.cfd_mesh as cfd_mesh_api
import app.api.cfd_runs as cfd_runs_api
import app.solvers.openfoam as of
from app.main import app
from app.mesh.cfd_mesher import (
    SnappyParams,
    TunnelParams,
    export_surface_stl,
    location_in_mesh,
    parse_check_mesh,
    parse_snappy_log,
    snappy_dict,
    tunnel_block_mesh_dict,
    tunnel_box,
    tunnel_patches,
)

FIX = Path(__file__).parent / "fixtures"
BOX = FIX / "box.step"  # 10 mm küp, 6 yüzey


def test_export_surface_stl_regions_scale_and_closed(tmp_path):
    out = tmp_path / "body.stl"
    stl = export_surface_stl(BOX, out, regions={"front": [1], "back": [2]}, size_mm=2.5)
    assert set(stl.regions) == {"front", "back", "body"}
    assert stl.open_edges == 0  # kapalı küp
    assert stl.bbox_m[3] - stl.bbox_m[0] == pytest.approx(0.01, rel=1e-4)  # mm → m
    text = out.read_text()
    assert text.splitlines().count("solid front") == 1 and "endsolid body" in text
    assert stl.triangles == sum(stl.triangles_per_region.values()) == text.count("facet normal")
    with pytest.raises(ValueError, match="CFD yaması"):
        export_surface_stl(BOX, out, regions={"inlet": [1]})


def test_tunnel_box_and_block_mesh_dict():
    bbox = (0.0, -0.05, -0.05, 0.1, 0.05, 0.05)
    box = tunnel_box(bbox, TunnelParams(base_cell_m=0.05))
    assert box.lo == pytest.approx((-0.3, -0.35, -0.35)) and box.hi == pytest.approx((0.7, 0.35, 0.35))
    assert box.cells == (20, 14, 14) and box.background_cells == 3920
    text = tunnel_block_mesh_dict(box, ground=False)
    assert "sides\n    {\n        type patch;\n        faces ((0 1 5 4) (3 7 6 2) (4 5 6 7) (0 3 2 1));" in text
    assert "ground" not in text
    g = tunnel_box(bbox, TunnelParams(base_cell_m=0.05, ground=True, ground_clearance_m=0.01))
    assert g.lo[2] == pytest.approx(-0.06)
    gt = tunnel_block_mesh_dict(g, ground=True)
    assert "ground\n    {\n        type wall;\n        faces ((0 3 2 1));" in gt
    assert tunnel_patches(["nose", "fins"], True) == ["inlet", "outlet", "sides", "ground", "nose", "fins"]


def test_snappy_dict_regions_wake_layers_location():
    bbox = (0.0, -0.05, -0.05, 0.1, 0.05, 0.05)
    box = tunnel_box(bbox, TunnelParams(base_cell_m=0.05))
    p = SnappyParams(surface_level_min=2, surface_level_max=4, n_layers=5, wake_level=2)
    text = snappy_dict(box, bbox, ["nose", "body"], p)
    assert "nose { name nose; }" in text and "body { name body; }" in text
    assert "level (2 4);" in text and "nSurfaceLayers 5;" in text and '"(nose|body)"' in text
    assert "levels ((1E15 2));" in text and "type box;" in text
    loc = location_in_mesh(box)
    assert all(box.lo[i] < loc[i] < box.hi[i] for i in range(3))
    assert not (bbox[0] <= loc[0] <= bbox[3])  # gövde kutusunun dışında
    no_wake = snappy_dict(box, bbox, ["body"], SnappyParams(wake_level=0, n_layers=0))
    assert "wake" not in no_wake and "addLayers       false;" in no_wake
    with pytest.raises(ValidationError, match="surface_level_max"):
        SnappyParams(surface_level_min=4, surface_level_max=2)


def test_parse_check_mesh_and_snappy_log():
    c = parse_check_mesh((FIX / "cfd" / "checkMesh_sphere.log").read_text())
    assert c["cells"] == 12544 and c["hexahedra"] == 9924 and c["polyhedra"] == 2620
    assert c["non_orthogonality_max"] == pytest.approx(34.5265)
    assert c["skewness_max"] == pytest.approx(0.51671)
    assert c["aspect_ratio_max"] == pytest.approx(3.82726)
    assert c["min_face_area"] == pytest.approx(4.75424e-06)
    assert c["mesh_ok"] is True and c["failed_checks"] == 0
    assert c["patch_faces"] == {"inlet": 196, "outlet": 196, "sides": 1120, "body": 744}
    s = parse_snappy_log((FIX / "cfd" / "snappy_sphere.log").read_text())
    assert s["background_cells"] == 3920 and s["snapped_cells"] == 10312 and s["layer_cells"] == 12544
    assert s["cells_per_level"] == {0: 3744, 1: 1104, 2: 1688, 3: 6008}
    assert s["layers"]["body"] == {
        "faces": 744, "target_layers": 3.0, "layers": 3.0, "thickness_m": 0.00474, "thickness_percent": 100.0,
    }
    assert s["finished"] is True and s["seconds"] == pytest.approx(1.12)


# ------------------------------------------------------------------- API (sahte süreç)

LOG = "Time = 1\n\nGAMG:  Solving for p, Initial residual = 1, Final residual = 0.1, No Iterations 3\n\nSIMPLE solution converged in 1 iterations\n\nEnd\n"


def _fake_docker(image, case_dir, script):
    case = Path(case_dir)
    if "snappyHexMesh" in script:
        (case / "constant" / "polyMesh").mkdir(parents=True, exist_ok=True)
        (case / "constant" / "polyMesh" / "owner").write_text("sahte")
        (case / "log.snappyHexMesh").write_text((FIX / "cfd" / "snappy_sphere.log").read_text())
        (case / "log.checkMesh").write_text((FIX / "cfd" / "checkMesh_sphere.log").read_text())
        return [sys.executable, "-c", "print('MESH_EXIT=0')"]
    code = (
        "import sys, pathlib\n"
        f"assert pathlib.Path({str(case)!r}, 'constant', 'polyMesh', 'owner').is_file()\n"
        f"t = {LOG!r}\n"
        f"pathlib.Path({str(case)!r}, 'log.simpleFoam').write_text(t)\n"
        "sys.stdout.write(t)\n"
    )
    return [sys.executable, "-c", code]


@pytest.fixture
def api(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENFOAM_DOCKER_IMAGE", "fake/openfoam:test")
    monkeypatch.setattr(cfd_api, "CFD_DIR", tmp_path / "cfd")
    monkeypatch.setattr(cfd_runs_api, "CFD_DIR", tmp_path / "cfd")
    monkeypatch.setattr(cfd_mesh_api, "CFD_MESH_DIR", tmp_path / "meshes")
    monkeypatch.setattr(of, "docker_command", _fake_docker)
    monkeypatch.setattr(cfd_mesh_api, "docker_command", _fake_docker)
    client = TestClient(app)
    up = client.post("/geometry/upload", files={"file": ("box.step", BOX.read_bytes(), "application/octet-stream")})
    assert up.status_code == 200, up.text
    gid = up.json()["geometry_id"]
    r = client.post(f"/geometry/{gid}/physical-groups", json={"name": "nose", "face_ids": [1]})
    assert r.status_code == 200, r.text
    return client, gid


def test_api_mesh_then_solve_with_mesh_id(api):
    client, gid = api
    m = client.post(
        "/cfd/mesh",
        json={"geometry_id": gid, "tunnel": {"base_cell_m": 0.005}, "snappy": {"stl_size_mm": 2.5}, "wait": True},
    ).json()
    assert m["status"] == "meshed", m
    assert m["patches"] == ["inlet", "outlet", "sides", "nose", "body"]
    assert m["surface"]["open_edges"] == 0 and set(m["surface"]["regions"]) == {"nose", "body"}
    assert m["check"]["cells"] == 12544 and m["snappy"]["layers"]["body"]["layers"] == 3.0
    assert client.get(f"/cfd/mesh/{m['mesh_id']}").json()["status"] == "meshed"
    case = {
        "nu_m2_s": 1.5e-5,
        "patches": [
            {"name": "inlet", "kind": "inlet", "velocity_m_s": [10, 0, 0]},
            {"name": "outlet", "kind": "outlet"},
            {"name": "sides", "kind": "slip"},
            {"name": "nose", "kind": "wall"},
            {"name": "body", "kind": "wall"},
        ],
    }
    s = client.post("/cfd/solve", json={"case": case, "mesh_id": m["mesh_id"], "wait": True}).json()
    assert s["status"] == "solved", s
    run = client.get(f"/cfd/runs/{s['run_id']}").json()
    assert run["mesh_kind"] == "snappy" and run["geometry_id"] == gid
    assert run["request"]["mesh"]["cells"] == 12544
    bad = {**case, "patches": [*case["patches"][:3], {"name": "fins", "kind": "wall"}]}
    r = client.post("/cfd/solve", json={"case": bad, "mesh_id": m["mesh_id"]})
    assert r.status_code == 422 and "fins" in r.text


def test_api_mesh_validation(api):
    client, gid = api
    r = client.post("/cfd/mesh", json={"geometry_id": gid, "tunnel": {"base_cell_m": 0.005}, "regions": ["yok"]})
    assert r.status_code == 422 and "yok" in r.text
    case = {"nu_m2_s": 1e-5, "patches": [{"name": "inlet", "kind": "inlet", "velocity_m_s": [1, 0, 0]}, {"name": "outlet", "kind": "outlet"}]}
    r = client.post("/cfd/solve", json={"case": case, "mesh_id": "olmayan"})
    assert r.status_code == 422 and "hazır değil" in r.text
    assert client.get("/cfd/mesh/olmayan").status_code == 404


# ------------------------------------------------------------------- gerçek Docker


def _docker_ready(image: str | None) -> bool:
    exe = shutil.which("docker")
    if not image or exe is None:
        return False
    return subprocess.run([exe, "image", "inspect", image], capture_output=True).returncode == 0


@pytest.mark.skipif(
    not _docker_ready(os.environ.get("OPENFOAM_DOCKER_IMAGE")),
    reason="OPENFOAM_DOCKER_IMAGE tanımlı değil ya da imaj yok",
)
def test_sphere_tunnel_mesh_and_solve_in_docker(monkeypatch, tmp_path):
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
    monkeypatch.setattr(cfd_api, "CFD_DIR", tmp_path / "cfd")
    monkeypatch.setattr(cfd_runs_api, "CFD_DIR", tmp_path / "cfd")
    monkeypatch.setattr(cfd_mesh_api, "CFD_MESH_DIR", tmp_path / "meshes")
    client = TestClient(app)
    gid = client.post("/geometry/upload", files={"file": ("sphere.step", step.read_bytes(), "application/octet-stream")}).json()["geometry_id"]
    m = client.post(
        "/cfd/mesh",
        json={"geometry_id": gid, "tunnel": {"base_cell_m": 0.05}, "snappy": {"surface_level_min": 3, "stl_size_mm": 5}, "wait": True},
    ).json()
    assert m["status"] == "meshed", m["message"]
    assert m["check"]["mesh_ok"] is True and m["check"]["cells"] > 5000
    case = {
        "nu_m2_s": 1.5e-5,
        "rho_kg_m3": 1.2,
        "patches": [
            {"name": "inlet", "kind": "inlet", "velocity_m_s": [10, 0, 0]},
            {"name": "outlet", "kind": "outlet"},
            {"name": "sides", "kind": "slip"},
            {"name": "body", "kind": "wall"},
        ],
        "turbulence": {"model": "kOmegaSST", "intensity": 0.01, "length_scale_m": 0.01},
        "control": {"iterations": 800},
        "forces": {"patches": ["body"], "u_ref_m_s": 10, "l_ref_m": 0.1, "a_ref_m2": math.pi * 0.05**2},
    }
    s = client.post("/cfd/solve", json={"case": case, "mesh_id": m["mesh_id"], "wait": True}).json()
    assert s["status"] == "solved", s["message"]
    assert 0.1 < s["scalars"]["Cd"] < 1.5  # kaba ağ — doğrulama 2.6'da
