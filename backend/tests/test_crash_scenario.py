"""1.17a — POST /crash/scenario: şablon → mesh → malzeme → crash deck + crash_runs kaydı."""

from __future__ import annotations

import pytest
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
    assert sc["use_rigid_wall"] is True and sc["direction"] is None and sc["t_end_ms"] > 0
    assert sc["part_roles"] == {"0": "moving"}
    # Sunucu mesh'i arayüze döner (viewport'a yüklenir)
    assert d["mesh"]["dimension"] == 2 and d["mesh"]["preview_url"].endswith(".preview.json")
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


@requires_db
def test_plate_ball_scenario_template_setup():
    # 1.18b — plaka free + kenar /BCS, küre moving + /RBODY, küre → plaka TYPE7, duvar yok
    r = _scenario(template_id="plate_ball_shell", element_size_mm=10, speed_m_s=12, ball_mass_kg=2.0,
                  ball_thickness_mm=1.5, name="plaka–küre")
    assert r.status_code == 200, r.text
    d = r.json()
    sc = d["scenario"]
    assert sc["thickness_mm"] == 5.0 and sc["ball_thickness_mm"] == 1.5 and sc["ball_mass_kg"] == 2.0
    assert sc["ball_material_name"] == "S235"
    deck = (CRASH_DIR / d["crash"]["job_id"] / "crash_0000.rad").read_text(encoding="utf-8")
    assert "part_0_free" in deck and "part_1_moving" in deck
    assert float(_card(deck, "/PROP/TYPE1/1")[3][20:40]) == 5.0
    assert float(_card(deck, "/PROP/TYPE1/2")[3][20:40]) == 1.5
    assert "/RWALL" not in deck
    assert "/INTER/TYPE7/1" in deck
    assert "/RBODY/1" in deck and float(_card(deck, "/RBODY/1")[1][40:60]) == 2.0
    assert "/BCS/" in deck and "bcs_plaka_kenar" in deck
    vel = _card(deck, "/INIVEL/TRA/1")[1]
    assert [float(vel[i:i + 20]) for i in (0, 20, 40)] == [0.0, 0.0, -12.0]
    run = client.get(f"/crash/runs/{d['crash']['run_id']}").json()
    assert [p["role"] for p in run["request"]["parts"]] == ["free", "moving"]


@requires_db
def test_plate_ball_without_template_defaults_keeps_lists_empty():
    r = _scenario(template_id="plate_ball_shell", element_size_mm=10, template_defaults=False)
    assert r.status_code == 200, r.text
    deck = (CRASH_DIR / r.json()["crash"]["job_id"] / "crash_0000.rad").read_text(encoding="utf-8")
    assert "/RBODY/" not in deck and "/INTER/" not in deck and "bcs_plaka_kenar" not in deck


@requires_db
def test_taylor_bar_scenario_solid_deck():
    # K1 — 3D tet mesh, tek parça hareketli, rijit duvar x = 0 (+x), ilk hız −x
    r = _scenario(template_id="taylor_bar", element_size_mm=3.0, speed_m_s=120, t_end_ms=0.3)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["scenario"]["element_scheme"] == "tet" and d["scenario"]["thickness_mm"] is None
    deck = (CRASH_DIR / d["crash"]["job_id"] / "crash_0000.rad").read_text(encoding="utf-8")
    assert "/TETRA4/1" in deck and "/SHELL/" not in deck and "/RWALL/PLANE/1" in deck
    vel = _card(deck, "/INIVEL/TRA/1")[1]
    assert [float(vel[i:i + 20]) for i in (0, 20, 40)] == [-120.0, 0.0, 0.0]


@requires_db
def test_drop_box_scenario_height_gravity_ground():
    # K2 — H 1000 mm → v0 = √(2·9.81·1) = 4.4294 m/s; /GRAV −9.81 Z; zemin z = 0 (+z)
    r = _scenario(template_id="drop_box_shell", element_size_mm=20, drop_height_mm=1000.0, t_end_ms=2.0)
    assert r.status_code == 200, r.text
    sc = r.json()["scenario"]
    assert sc["speed_m_s"] == pytest.approx(4.42945, rel=1e-5)
    assert sc["gravity"] == {"accel_m_s2": -9.81, "direction": "Z"}
    assert sc["wall"] == {"point": [0.0, 0.0, 0.0], "normal": [0.0, 0.0, 1.0]}
    deck = (CRASH_DIR / r.json()["crash"]["job_id"] / "crash_0000.rad").read_text(encoding="utf-8")
    assert "/GRAV/1" in deck and "/RWALL/PLANE/1" in deck
    vel = _card(deck, "/INIVEL/TRA/1")[1]
    assert float(vel[40:60]) == pytest.approx(-4.42945, rel=1e-5)


@requires_db
def test_drop_box_floor_plate_contact_instead_of_wall():
    # V7 kontrolü — floor_size > 0: rijit duvar yok; zemin parça 1 sabit (/BCS), kutu → zemin TYPE7
    r = _scenario(template_id="drop_box_shell", element_size_mm=20, drop_height_mm=1000.0, t_end_ms=2.0,
                  geometry={"gap": 5.0, "floor_size": 400.0})
    assert r.status_code == 200, r.text
    deck = (CRASH_DIR / r.json()["crash"]["job_id"] / "crash_0000.rad").read_text(encoding="utf-8")
    assert "/RWALL/" not in deck
    assert "/INTER/TYPE7/1" in deck and "/BCS/" in deck and "/PART/2" in deck
    vel = _card(deck, "/INIVEL/TRA/1")[1]
    assert float(vel[40:60]) == pytest.approx(-4.42945, rel=1e-5)


@requires_db
def test_pole_beam_scenario_cylindrical_wall_and_end_masses():
    # K3 — /RWALL/CYL Ø254: eksen z, nokta (−g − D/2, L/2, b/2); uçlar rijit gövde + kütle
    r = _scenario(template_id="pole_beam_shell", element_size_mm=20, speed_m_s=5, end_mass_kg=10.0, t_end_ms=1.0)
    assert r.status_code == 200, r.text
    d = r.json()
    w = d["scenario"]["wall"]
    assert w["kind"] == "cyl" and w["diameter_mm"] == 254.0 and w["axis"] == [0.0, 0.0, 1.0]
    assert w["point"] == [-128.0, 400.0, 20.0]
    deck = (CRASH_DIR / d["crash"]["job_id"] / "crash_0000.rad").read_text(encoding="utf-8")
    cyl = _card(deck, "/RWALL/CYL/1")
    assert float(cyl[2][40:60]) == 254.0
    assert [float(cyl[3][i:i + 20]) for i in (0, 20, 40)] == [-128.0, 400.0, 20.0]
    assert [float(cyl[4][i:i + 20]) for i in (0, 20, 40)] == [-128.0, 400.0, 21.0]
    assert "/RWALL/PLANE" not in deck
    assert "/RBODY/1" in deck and "/RBODY/2" in deck
    assert float(_card(deck, "/RBODY/1")[1][40:60]) == 10.0


@requires_db
def test_rops_scenario_push_without_moving_part():
    # K4 — hareketli parça / duvar / ilk hız yok; tabanlar /BCS, yük köşesi RBODY + IMPVEL Y, /SECT z = H/2
    r = _scenario(template_id="rops_frame_shell", element_size_mm=40, push_speed_m_s=2.0, t_end_ms=1.0)
    assert r.status_code == 200, r.text
    deck = (CRASH_DIR / r.json()["crash"]["job_id"] / "crash_0000.rad").read_text(encoding="utf-8")
    assert "part_0_free" in deck and "/INIVEL/" not in deck and "/RWALL" not in deck
    assert "bcs_taban_1" in deck and "bcs_taban_2" in deck and "/RBODY/1" in deck
    imp = _card(deck, "/IMPVEL/1")
    assert imp[1][10:20].strip() == "Y"
    assert float(_card(deck, "/FUNCT/9901")[1][20:40]) == 2.0
    assert "/SECT/PARAL/" in deck


@requires_db
def test_head_impactor_total_mass_and_accel_channel():
    # K5 — toplam 4.5 kg: ek = 4.5 − π·165²·1·7850e-9 (S235) ; küre ana düğümü /TH/NODE ilk sırada
    r = _scenario(template_id="plate_ball_shell", element_size_mm=30,
                  geometry={"plate_size": 600, "plate_thickness": 0.8, "ball_diameter": 165, "gap": 1},
                  ball_total_mass_kg=4.5, ball_thickness_mm=1.0, speed_m_s=11.1, filters={"acc_cfc": 1000})
    assert r.status_code == 200, r.text
    sc = r.json()["scenario"]
    shell = 3.141592653589793 * 165 ** 2 * 1.0 * 7850 * 1e-9
    assert sc["ball_mass_kg"] == pytest.approx(4.5 - shell, rel=1e-9)
    deck = (CRASH_DIR / r.json()["crash"]["job_id"] / "crash_0000.rad").read_text(encoding="utf-8")
    master = int(_card(deck, "/RBODY/1")[1][:10])
    th = deck.split("/TH/NODE/4", 1)[1].splitlines()
    assert int(th[3][:10]) == master  # başlık, vars satırı, sonra ilk düğüm


@requires_db
def test_door_beam_scenario_impactor_push():
    # K8 — iki parça free, impaktör RBODY + IMPVEL X, TYPE7 impaktör → kiriş, uçlar /BCS, duvar / ilk hız yok
    r = _scenario(template_id="door_beam_shell", element_size_mm=30, push_speed_m_s=2.0, t_end_ms=1.0)
    assert r.status_code == 200, r.text
    deck = (CRASH_DIR / r.json()["crash"]["job_id"] / "crash_0000.rad").read_text(encoding="utf-8")
    assert "part_0_free" in deck and "part_1_free" in deck
    assert "/INIVEL/" not in deck and "/RWALL" not in deck and "/INTER/TYPE7/1" in deck
    assert "bcs_uc_1" in deck and "bcs_uc_2" in deck and "/RBODY/1" in deck
    assert "bcs_impaktor_kilavuz" in deck and "   011 111" in deck
    assert _card(deck, "/IMPVEL/1")[1][10:20].strip() == "X"


@requires_db
def test_hopkinson_scenario_two_solid_parts():
    # K9 — giriş çubuğu free + çarpıcı moving (+x), TYPE7, x = Li/4 kesiti, duvar yok
    r = _scenario(template_id="hopkinson_bar", element_size_mm=8, speed_m_s=10, t_end_ms=0.05)
    assert r.status_code == 200, r.text
    deck = (CRASH_DIR / r.json()["crash"]["job_id"] / "crash_0000.rad").read_text(encoding="utf-8")
    assert "part_0_free" in deck and "part_1_moving" in deck and "/TETRA4/" in deck
    assert "/RWALL" not in deck and "/INTER/TYPE7/1" in deck and "/SECT/PARAL/" in deck
    vel = _card(deck, "/INIVEL/TRA/1")[1]
    assert float(vel[:20]) == 10.0


@requires_db
def test_blast_plate_pload_friedlander():
    # K10 — /SURF/PART + /FUNCT (normalize Friedlander) + /PLOAD Fscale = Ps (GPa); hareketli parça yok
    r = _scenario(template_id="blast_plate_shell", element_size_mm=50, blast_peak_mpa=2.0, blast_duration_ms=0.2,
                  t_end_ms=0.5)
    assert r.status_code == 200, r.text
    deck = (CRASH_DIR / r.json()["crash"]["job_id"] / "crash_0000.rad").read_text(encoding="utf-8")
    assert "/INIVEL/" not in deck and "/RWALL" not in deck and "bcs_plaka_kenar" in deck
    assert "/SURF/PART/9961" in deck
    pl = _card(deck, "/PLOAD/1")[1]
    assert int(pl[:10]) == 9961 and int(pl[10:20]) == 9971
    assert float(pl[60:80]) == 1.0 and float(pl[80:100]) == pytest.approx(2.0e-3)
    fn = _card(deck, "/FUNCT/9971")
    assert float(fn[1][:20]) == 0.0 and float(fn[1][20:40]) == pytest.approx(1.0)


@requires_db
def test_mine_pblast_oriented_segments():
    # K13 — /SURF/SEG (patlamaya bakan segmentler) + /LOAD/PBLAST zemin yansımalı; basınç kartı yok
    r = _scenario(template_id="blast_plate_shell", element_size_mm=100, mine_tnt_kg=6.0, mine_standoff_mm=500.0,
                  t_end_ms=0.5)
    assert r.status_code == 200, r.text
    deck = (CRASH_DIR / r.json()["crash"]["job_id"] / "crash_0000.rad").read_text(encoding="utf-8")
    assert "/LOAD/PBLAST/1" in deck and "/SURF/SEG/9996" in deck and "/PLOAD/" not in deck
    pb = _card(deck, "/LOAD/PBLAST/1")
    assert int(pb[1][10:20]) == 2  # Exp_data zemin yansımalı
    assert [float(pb[2][i:i + 20]) for i in (0, 20, 40, 60, 80)] == [0.0, 0.0, -500.0, 0.0, 6.0]
