"""K0 — explicit şablon kataloğu: 15 madde, ready olanlar /crash/scenario şablonları."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.crash_catalog import CATALOG, scenario_templates
from app.api.crash_scenario import CRASH_TEMPLATES
from app.main import app
from app.templates import TEMPLATES

client = TestClient(app)


def test_catalog_has_fifteen_unique_entries_with_valid_fields():
    assert len(CATALOG) == 15 and len({e.id for e in CATALOG}) == 15
    assert {e.sector for e in CATALOG} == {"otomotiv", "savunma", "is_makineleri"}
    assert sum(e.status == "ready" for e in CATALOG) == 15
    for e in CATALOG:
        assert e.status in ("ready", "planned", "major")
        assert e.reference and e.validation
        if e.status == "ready":
            assert e.template_id in TEMPLATES and e.mesh_dim in (2, 3)
        else:
            assert e.infrastructure  # eksik altyapı yazılı


def test_ready_entries_drive_scenario_templates():
    assert scenario_templates() == {"crash_box_shell": 2, "plate_ball_shell": 2, "taylor_bar": 3, "drop_box_shell": 2, "pole_beam_shell": 2, "rops_frame_shell": 2, "s_rail_shell": 2, "door_beam_shell": 2, "hopkinson_bar": 3, "blast_plate_shell": 2, "bucket_rock_shell": 2}
    assert CRASH_TEMPLATES == scenario_templates()


def test_catalog_endpoint():
    r = client.get("/crash/catalog")
    assert r.status_code == 200
    d = r.json()
    assert len(d["entries"]) == 15
    assert d["scenario_templates"]["plate_ball_shell"] == 2
    taylor = next(e for e in d["entries"] if e["id"] == "taylor_bar")
    assert taylor["status"] == "ready" and taylor["template_id"] == "taylor_bar" and taylor["mesh_dim"] == 3
