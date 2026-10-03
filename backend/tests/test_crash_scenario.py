"""1.17a — POST /crash/scenario: şablon → mesh → malzeme → crash deck + crash_runs kaydı."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.crash_runs import CRASH_DIR
from app.main import app
from tests.test_crash_contact import _card
from tests.test_crash_solve import _clean_state  # noqa: F401 (autouse temizlik)
from tests.test_materials import requires_db

client = TestClient(app)


def _scenario(**body):
    return client.post("/crash/scenario", json={"run_solver": False, **body})


@requires_db
def test_default_scenario_builds_deck_like_manual_setup():
    r = _scenario(name="varsayılan")
    assert r.status_code == 200, r.text
    d = r.json()
    sc = d["scenario"]
    assert sc["geometry"] == {"box_length": 300.0, "box_height": 50.0, "box_width": 40.0, "wall": 3.0}
    assert sc["material_name"] == "S235" and sc["thickness_mm"] == 3.0
    assert sc["wall"] == {"point": [0.0, 25.0, 20.0], "normal": [1.0, 0.0, 0.0]}
    crash = d["crash"]
    assert crash["status"] == "rad_only" and crash["cards"]["has_shell"] and crash["cards"]["has_law2"]
    deck = (CRASH_DIR / crash["job_id"] / "crash_0000.rad").read_text(encoding="utf-8")
    assert float(_card(deck, "/PROP/TYPE1/1")[3][20:40]) == 3.0  # Thick
    run = client.get(f"/crash/runs/{crash['run_id']}").json()
    assert run["geometry_id"] == d["geometry_id"] and run["name"] == "varsayılan"
    assert run["request"]["parts"][0]["thickness_mm"] == 3.0
    geo_runs = client.get("/crash/runs", params={"geometry_id": d["geometry_id"]}).json()
    assert geo_runs["count"] == 1


@requires_db
def test_parameters_flow_into_deck():
    r = _scenario(geometry={"box_length": 250, "wall": 2}, speed_m_s=15, thickness_mm=2.5,
                  wall={"point": [0, 0, 0], "normal": [1, 0, 0]}, t_end_ms=2.0)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["scenario"]["thickness_mm"] == 2.5  # açık kalınlık şablon wall'unu ezer
    deck = (CRASH_DIR / d["crash"]["job_id"] / "crash_0000.rad").read_text(encoding="utf-8")
    assert float(_card(deck, "/PROP/TYPE1/1")[3][20:40]) == 2.5
    assert float(_card(deck, "/INIVEL/TRA/1")[1][:20]) == -15.0
    engine = (CRASH_DIR / d["crash"]["job_id"] / "crash_0001.rad").read_text(encoding="utf-8")
    assert float(_card(engine, "/RUN/crash/1")[0]) == 2.0


@requires_db
def test_invalid_inputs():
    assert _scenario(template_id="cantilever_beam").status_code == 422  # crash şablonu değil
    assert _scenario(geometry={"box_height": 5, "wall": 3}).status_code == 422  # h ≤ 2t
    assert _scenario(material_name="YOK-BOYLE-MALZEME").status_code == 404
