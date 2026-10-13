"""R1 — parametrik roket şablonu (CFD, dış akış).

Burun profilleri (uç ve omuz değerleri, ogive teğetliği), dört burun tipi ×
boat-tail'li / boat-tail'siz kurulum, bölgeler, kapalı yüzey (CFD için şart),
parametre doğrulaması.
"""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

import app.main  # noqa: F401 — .env yüklensin (OPENFOAM_DOCKER_IMAGE, Docker testi)
from app.mesh.cfd_mesher import export_surface_stl
from app.templates import TEMPLATES, build_template
from app.templates.rocket import ROCKET, RocketParams, nose_radius

SHAPES = ("konik", "ogive", "elips", "von_karman")


@pytest.mark.parametrize("shape", SHAPES)
def test_nose_radius_tip_and_shoulder(shape):
    assert nose_radius(shape, 0.0, 300.0, 50.0) == pytest.approx(0.0, abs=1e-9)
    assert nose_radius(shape, 300.0, 300.0, 50.0) == pytest.approx(50.0, rel=1e-9)
    xs = [300.0 * i / 50 for i in range(51)]
    rs = [nose_radius(shape, x, 300.0, 50.0) for x in xs]
    assert all(b >= a - 1e-9 for a, b in zip(rs, rs[1:]))  # monoton artan


def test_ogive_is_tangent_at_shoulder():
    h = 1e-4
    slope = (nose_radius("ogive", 300.0, 300.0, 50.0) - nose_radius("ogive", 300.0 - h, 300.0, 50.0)) / h
    assert slope == pytest.approx(0.0, abs=1e-3)


def test_registered_with_cfd_tag_and_no_structural_bcs():
    assert TEMPLATES["rocket"] is ROCKET
    assert "cfd" in ROCKET.tags and ROCKET.default_bcs == ()


@pytest.mark.parametrize("shape", SHAPES)
@pytest.mark.parametrize("boattail", [0.0, 100.0])
def test_build_regions_and_closed_surface(tmp_path, shape, boattail):
    p = RocketParams(nose_shape=shape, boattail_length=boattail)
    built = build_template(ROCKET, p, tmp_path / "rocket.step")
    assert set(built.regions) == {"burun", "govde", "kanatcik", "taban"}
    assert len(built.regions["taban"]) == 1
    # her kanatçık 5 dış yüz (iki yan, hücum, firar, uç) — 4 kanatçık
    assert len(built.regions["kanatcik"]) == 5 * p.fin_count
    xmin, _ymin, _zmin, xmax, ymax, _zmax = built.bounding_box
    # spline uca yakın birkaç µm taşabilir (elips, von Kármán) — geometrik önemi yok
    assert xmin == pytest.approx(0.0, abs=1e-2) and xmax == pytest.approx(p.total_length, abs=1e-3)
    assert ymax == pytest.approx(p.radius + p.fin_span, abs=1e-3)
    stl = export_surface_stl(built.step_path, tmp_path / "body.stl", regions=built.regions, size_mm=15)
    assert stl.open_edges == 0
    assert set(stl.regions) == ({"burun", "govde", "kanatcik", "taban"} | ({"body"} if boattail else set()))


def test_fin_count_three(tmp_path):
    p = RocketParams(fin_count=3)
    built = build_template(ROCKET, p, tmp_path / "rocket.step")
    assert len(built.regions["kanatcik"]) == 15


def test_param_validation():
    with pytest.raises(ValidationError, match="gövde tüpüne"):
        RocketParams(body_length=100.0, fin_root_chord=150.0)
    with pytest.raises(ValidationError, match="Boat-tail"):
        RocketParams(boattail_length=50.0, boattail_aft_diameter=120.0)
    with pytest.raises(ValidationError, match="kalınlığı"):
        RocketParams(fin_count=8, fin_thickness=40.0)
    assert RocketParams().total_length == pytest.approx(1500.0)
    assert math.isclose(RocketParams(boattail_length=100).total_length, 1600.0)


def _docker_ready(image: str | None) -> bool:
    import shutil
    import subprocess

    exe = shutil.which("docker")
    if not image or exe is None:
        return False
    return subprocess.run([exe, "image", "inspect", image], capture_output=True).returncode == 0


@pytest.mark.skipif(
    not _docker_ready(__import__("os").environ.get("OPENFOAM_DOCKER_IMAGE")),
    reason="OPENFOAM_DOCKER_IMAGE tanımlı değil ya da imaj yok",
)
def test_rocket_tunnel_mesh_and_patch_forces_in_docker(monkeypatch, tmp_path):
    """Şablon → rüzgâr tüneli (kaba) → kısa çözüm: her bölge ayrı yama, toplam = yamaların toplamı."""
    from fastapi.testclient import TestClient

    import app.api.cfd as cfd_api
    import app.api.cfd_mesh as cfd_mesh_api
    import app.api.cfd_runs as cfd_runs_api
    from app.main import app

    monkeypatch.setattr(cfd_api, "CFD_DIR", tmp_path / "cfd")
    monkeypatch.setattr(cfd_runs_api, "CFD_DIR", tmp_path / "cfd")
    monkeypatch.setattr(cfd_mesh_api, "CFD_MESH_DIR", tmp_path / "meshes")
    client = TestClient(app)
    gid = client.post("/templates/rocket/create", json={"params": {}}).json()["geometry_id"]
    m = client.post(
        "/cfd/mesh",
        json={
            "geometry_id": gid,
            "wait": True,
            "tunnel": {"upstream": 1, "downstream": 2, "lateral": 0.5, "base_cell_m": 0.2},
            "snappy": {"surface_level_min": 2, "surface_level_max": 3, "feature_level": 3, "wake_level": 0, "n_layers": 0, "stl_size_mm": 15},
        },
    ).json()
    assert m["status"] == "meshed", m["message"]
    assert m["patches"] == ["inlet", "outlet", "sides", "burun", "govde", "kanatcik", "taban"]
    body = ["burun", "govde", "kanatcik", "taban"]
    case = {
        "nu_m2_s": 1.5e-5,
        "patches": [
            {"name": "inlet", "kind": "inlet", "velocity_m_s": [20, 0, 0]},
            {"name": "outlet", "kind": "outlet"},
            {"name": "sides", "kind": "slip"},
            *({"name": n, "kind": "wall"} for n in body),
        ],
        "control": {"iterations": 60},
        "forces": {"patches": body, "u_ref_m_s": 20, "l_ref_m": 0.1, "a_ref_m2": math.pi * 0.05**2},
    }
    s = client.post("/cfd/solve", json={"case": case, "mesh_id": m["mesh_id"], "wait": True}).json()
    assert s["status"] == "solved", s["message"]
    sc = s["scalars"]
    total = sum(sc[f"force_{n}_x"] for n in body)
    assert sc["force_total_x"] == pytest.approx(total, rel=1e-4)
