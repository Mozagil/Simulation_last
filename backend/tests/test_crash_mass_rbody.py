"""1.17b — /ADMAS ek kütle + /RBODY rijit gövde (bölge ya da parça seçimi); global enerji.

Kart düzenleri hm_cfg: admas radioss110 (MASS grnd_ID), rbody radioss2021
(node_ID sens skew Ispher Mass grnd Ikrem ICoG surf · J · Ioptoff).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.solvers.openradioss_headers import strip_headers
from app.api.crash_runs import CRASH_DIR
from app.main import app
from app.postprocess.openradioss_th import parse_openradioss_dir
from app.solvers.base import SolverError
from app.solvers.crash_params import CrashMassParams, CrashRigidBodyParams
from app.solvers.openradioss import OpenRadiossAdapter
from tests.test_crash_contact import _card
from tests.test_crash_multipart import _two_part_params
from tests.test_crash_solve import _clean_state  # noqa: F401
from tests.test_materials import requires_db

client = TestClient(app)


def _deck(tmp_path, **extra) -> str:
    p = _two_part_params(tmp_path)  # parça 0 hareketli (düğüm 1–4), parça 1 sabit (5–8)
    p.update(extra)
    return strip_headers(OpenRadiossAdapter().build_input(p).path.read_text(encoding="utf-8"))


def test_admas_on_region_total_and_per_node(tmp_path):
    s = _deck(tmp_path, region_nodes={"arka": [2, 3]}, added_masses=[
        {"name": "kizak", "region": "arka", "mass_kg": 50.0},
        {"name": "her", "part_id": 1, "mass_kg": 0.5, "distribution": "per_node"},
    ])
    assert _card(s, "/ADMAS/1/1") == ["kizak", f"{50.0:20.8g}{8501:10d}"]  # type 1 = toplam
    assert _card(s, "/GRNOD/NODE/8501")[1] == f"{2:10d}{3:10d}"
    assert _card(s, "/ADMAS/0/2")[1] == f"{0.5:20.8g}{8502:10d}"  # type 0 = düğüm başına
    assert _card(s, "/GRNOD/NODE/8502")[1] == "".join(f"{n:10d}" for n in (5, 6, 7, 8))


def test_rbody_master_node_at_centroid_and_moving_velocity(tmp_path):
    s = _deck(tmp_path, region_nodes={"uc": [2, 3]}, rigid_bodies=[{"name": "kizak", "region": "uc", "mass_kg": 50}])
    node = _card(s, "/NODE")
    assert node[-1] == f"{9:10d}{0.5:20.8g}{0.5:20.8g}{0.0:20.8g}"  # (1,0,0)+(0,1,0) / 2, yeni id = 9
    rb = _card(s, "/RBODY/1")
    assert rb[0] == "kizak"
    assert rb[1] == f"{9:10d}{0:10d}{0:10d}{0:10d}{50.0:20.8g}{8701:10d}{0:10d}{0:10d}{0:10d}"
    assert len(rb) == 5  # ad + kart + J (2 satır) + Ioptoff
    assert _card(s, "/GRNOD/NODE/8701")[1] == f"{2:10d}{3:10d}"
    # hareketli parçaya bağlı → ana düğüm de ilk hızı alır
    assert _card(s, "/GRNOD/NODE/8700")[1] == f"{9:10d}"
    assert _card(s, "/INIVEL/TRA/2")[1].endswith(f"{8700:10d}{0:10d}")


def test_rbody_on_fixed_part_gets_no_velocity(tmp_path):
    s = _deck(tmp_path, rigid_bodies=[{"name": "sabit", "part_id": 1}])
    assert "/RBODY/1" in s and "/INIVEL/TRA/2" not in s


def test_unknown_region_or_part_is_solver_error(tmp_path):
    with pytest.raises(SolverError, match="bölge 'yok'"):
        _deck(tmp_path, added_masses=[{"name": "m", "region": "yok", "mass_kg": 1}])
    with pytest.raises(SolverError, match="parça #7"):
        _deck(tmp_path, rigid_bodies=[{"name": "r", "part_id": 7}])


@pytest.mark.parametrize(
    "cls,raw",
    [
        (CrashMassParams, {"mass_kg": 1}),  # seçim yok
        (CrashMassParams, {"region": "a", "part_id": 0, "mass_kg": 1}),  # ikisi birden
        (CrashMassParams, {"region": "a", "mass_kg": 0}),
        (CrashMassParams, {"region": "a", "mass_kg": 1, "distribution": "x"}),
        (CrashRigidBodyParams, {"region": "a", "icog": 7}),
        (CrashRigidBodyParams, {"region": "a", "ikrem": 2}),
    ],
)
def test_invalid_rejected(cls, raw):
    with pytest.raises(ValidationError):
        cls.model_validate(raw)


@requires_db
def test_scenario_rbody_on_template_region():
    r = client.post("/crash/scenario", json={"run_solver": False,
                                              "rigid_bodies": [{"name": "kizak", "region": "kutu_arka", "mass_kg": 50}]})
    assert r.status_code == 200, r.text
    deck = strip_headers((CRASH_DIR / r.json()["crash"]["job_id"] / "crash_0000.rad").read_text(encoding="utf-8"))
    ids = "".join(_card(deck, "/GRNOD/NODE/8701")[1:]).split()
    assert len(ids) > 4  # arka uç halkası (x = L) düğümleri
    master = _card(deck, "/RBODY/1")[1][:10]
    xyz = next(l for l in _card(deck, "/NODE") if l[:10] == master)
    assert float(xyz[10:30]) == pytest.approx(300.0)  # halka ağırlık merkezi x = L
    bad = client.post("/crash/scenario", json={"run_solver": False,
                                               "rigid_bodies": [{"name": "x", "region": "olmayan"}]})
    assert bad.status_code == 422 and "olmayan" in bad.json()["detail"]


def test_global_energy_columns_preferred(tmp_path):
    # rijit gövdeli koşu: parça TH'si ana düğüm kütlesini içermez; global sütun içerir
    h = ['"time"', '"INTERNAL ENERGY"', '"KINETIC ENERGY"', '"HOURGLASS ENERGY"', '"EXTERNAL WORK"',
         '"part_0_moving IE"', '"part_0_moving KE"']
    rows = ["0,0,2559,0,0,0,71", "1,2441,4.7,113,0,2441,0.2"]
    (tmp_path / "crashT01.csv").write_text("\n".join([",".join(h), *rows]) + "\n", encoding="utf-8")
    s = parse_openradioss_dir(tmp_path).scalars
    assert s["kinetic_energy_max"] == 2559
    assert s["energy_balance_rel"] == pytest.approx(abs(2441 + 4.7 + 113 - 2559) / 2559)
    assert s["hourglass_energy_final"] == 113 and s["hourglass_ratio"] == pytest.approx(113 / 2441)


def test_hourglass_energy_curve_stored(tmp_path):
    # 1.17h — global HOURGLASS ENERGY sütunu grafikte görünsün diye eğri olarak saklanır
    h = ['"time"', '"INTERNAL ENERGY"', '"KINETIC ENERGY"', '"HOURGLASS ENERGY"']
    rows = ["0,0,100,0", "1,90,5,3"]
    (tmp_path / "crashT01.csv").write_text("\n".join([",".join(h), *rows]) + "\n", encoding="utf-8")
    assert parse_openradioss_dir(tmp_path).curves["hourglass_energy"] == [0.0, 3.0]


def test_energy_balance_scale_for_driven_run(tmp_path):
    # K4 — KE₀ = 0, dış iş = IE: denge ≈ 0 (payda enerji ölçeği), eskiden 1.0
    h = ['"time"', '"INTERNAL ENERGY"', '"KINETIC ENERGY"', '"EXTERNAL WORK"']
    rows = ["0,0,0,0", "1,1000,5,1004"]
    (tmp_path / "crashT01.csv").write_text("\n".join([",".join(h), *rows]) + "\n", encoding="utf-8")
    s = parse_openradioss_dir(tmp_path).scalars
    assert s["energy_balance_rel"] == pytest.approx(1.0 / 1004.0)
