"""Faz 3.9 — POST /composite/solve + assemble (`/solve` yok)."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

import pytest

from app.api.composite import router as composite_router
from app.composite.assemble import assemble_composite_layup
from app.db.session import SessionLocal
from app.models import user as _user_model  # noqa: F401
from app.models.composite import CompositeLayup, CompositeMaterial
from app.models.geometry import Geometry

app = FastAPI()
app.include_router(composite_router)
client = TestClient(app)

_T300 = {
    "name": "T300/epoxy",
    "e1": 135e9,
    "e2": 10e9,
    "e3": 10e9,
    "nu12": 0.3,
    "nu13": 0.3,
    "nu23": 0.45,
    "g12": 5.2e9,
    "g13": 5.2e9,
    "g23": 3.4e9,
    "density": 1600.0,
}


def _tables() -> bool:
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1 FROM composite_runs LIMIT 0"))
        db.execute(text("SELECT 1 FROM composite_layups LIMIT 0"))
        db.execute(text("SELECT 1 FROM composite_materials LIMIT 0"))
        db.close()
        return True
    except OperationalError:
        return False
    except Exception:
        return False


requires_db = pytest.mark.skipif(
    not _tables(),
    reason="PostgreSQL veya composite_runs yok (alembic upgrade head)",
)


def test_assemble_0_90_0():
    spec = assemble_composite_layup(
        part_id=0,
        plies=[
            {"material_id": 1, "thickness_mm": 0.125, "angle_deg": 0},
            {"material_id": 1, "thickness_mm": 0.125, "angle_deg": 90},
            {"material_id": 1, "thickness_mm": 0.125, "angle_deg": 0},
        ],
        materials={1: _T300},
    )
    assert spec["part_id"] == 0
    assert spec["dir0"] == [1.0, 0.0, 0.0]
    assert [p["angle_deg"] for p in spec["plies"]] == [0.0, 90.0, 0.0]
    assert spec["plies"][0]["e1"] == 135e9
    assert spec["plies"][0]["name"] == "T300/epoxy"


def test_assemble_missing_material_and_empty():
    with pytest.raises(ValueError, match="Ply"):
        assemble_composite_layup(
            part_id=0,
            plies=[{"material_id": 9, "thickness_mm": 0.125, "angle_deg": 0}],
            materials={1: _T300},
        )
    with pytest.raises(ValueError, match="En az bir"):
        assemble_composite_layup(part_id=0, plies=[], materials={1: _T300})


@requires_db
def test_solve_rejects_bad_geometry_dimension_layup_bcs():
    missing = client.post(
        "/composite/solve",
        json={
            "geometry_id": 2_147_000_000,
            "bcs": [{"type": "fixed", "face_ids": [1]}],
        },
    )
    assert missing.status_code == 404

    dim3 = client.post(
        "/composite/solve",
        json={"geometry_id": 1, "dimension": 3, "bcs": [{"type": "fixed", "face_ids": [1]}]},
    )
    assert dim3.status_code == 400

    db = SessionLocal()
    try:
        geo = Geometry(
            original_filename="csolve-test.step",
            current_filename="csolve-test.step",
        )
        db.add(geo)
        db.commit()
        db.refresh(geo)
        gid = geo.id
        t300 = (
            db.query(CompositeMaterial)
            .filter(CompositeMaterial.name == "T300/epoxy")
            .one()
        )
    finally:
        db.close()

    no_layup = client.post(
        "/composite/solve",
        json={
            "geometry_id": gid,
            "bcs": [{"type": "fixed", "face_ids": [1]}],
        },
    )
    assert no_layup.status_code == 422
    assert "dizilim" in no_layup.json()["detail"]

    db = SessionLocal()
    try:
        db.add(
            CompositeLayup(
                geometry_id=gid,
                part_id=0,
                plies=[
                    {
                        "material_id": t300.id,
                        "thickness_mm": 0.125,
                        "angle_deg": 0,
                    }
                ],
            )
        )
        db.commit()
    finally:
        db.close()

    no_bc = client.post("/composite/solve", json={"geometry_id": gid, "bcs": []})
    assert no_bc.status_code == 422

    no_mesh = client.post(
        "/composite/solve",
        json={
            "geometry_id": gid,
            "bcs": [{"type": "fixed", "face_ids": [1]}],
        },
    )
    assert no_mesh.status_code == 404
    assert "mesh" in no_mesh.json()["detail"].lower()

    listed = client.get("/composite/runs", params={"geometry_id": gid})
    assert listed.status_code == 200
    assert listed.json()["count"] == 0


def _gmsh_ok() -> bool:
    try:
        import gmsh  # noqa: F401

        return True
    except Exception:
        return False


@pytest.mark.skipif(not _gmsh_ok(), reason="gmsh yok")
def test_adapter_composite_layup_writes_inp(tmp_path):
    from app.mesh.base import MeshParams
    from app.mesh.gmsh_adapter import GmshMesherAdapter
    from app.solvers.calculix import CalculiXAdapter

    step = tmp_path / "plate.step"
    src = Path(__file__).parent / "fixtures" / "thin_plate.step"
    if not src.exists():
        src = Path(__file__).parent / "fixtures" / "box.step"
    step.write_bytes(src.read_bytes())
    from app.mesh.base import MeshError

    mesher = GmshMesherAdapter()
    geom = mesher.import_geometry(step)
    try:
        mesh = mesher.generate_mesh(
            geom, MeshParams(element_size=10.0, dimension=2, element_scheme="tet")
        )
    except MeshError:
        pytest.skip("2D shell için midsurface yok")
    spec = assemble_composite_layup(
        part_id=0,
        plies=[
            {"material_id": 1, "thickness_mm": 0.125, "angle_deg": 0},
            {"material_id": 1, "thickness_mm": 0.125, "angle_deg": 90},
        ],
        materials={1: _T300},
    )
    art = CalculiXAdapter().build_input(
        {
            "mesh_path": mesh.mesh_path,
            "dimension": 2,
            "output_dir": tmp_path / "crun",
            "job_name": "cjob",
            "materials": [],
            "shell_thickness": 0.25,
            "bcs": [{"type": "fixed", "face_ids": [1]}],
            "analysis_type": "static",
            "composite_layup": spec,
        }
    )
    text = art.path.read_text(encoding="utf-8")
    assert "COMPOSITE" in text
    assert "ENGINEERING CONSTANTS" in text
    assert "*ORIENTATION" in text
    assert "*STEP" in text
