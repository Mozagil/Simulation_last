"""1.23 C8b — ezilme mesafesi δ(t): crush_ref → ayrı /TH/NODE grubu + post-process izdüşüm."""

from __future__ import annotations

import json

import pytest

from app.postprocess.openradioss_th import crush_distance
from app.solvers.base import SolverError
from app.solvers.openradioss import OpenRadiossAdapter
from tests.test_crash_contact import _card
from tests.test_crash_multipart import _two_part_params


def _build(tmp_path, **extra):
    p = _two_part_params(tmp_path)
    p.update(extra)
    art = OpenRadiossAdapter().build_input(p)
    spec = json.loads((art.path.parent / "th_spec.json").read_text(encoding="utf-8"))
    return art.path.read_text(encoding="utf-8"), spec, p


def test_rigid_body_master_node_group(tmp_path):
    s, spec, p = _build(tmp_path, rigid_bodies=[{"name": "kizak", "part_id": 0, "mass_kg": 10}],
                        crush_ref={"rigid_body": "kizak"}, initial_velocity={"vx": -10.0, "vy": 0.0, "vz": 0.0})
    card = _card(s, "/TH/NODE/8")
    assert card[0] == "crush_ref" and card[1].split() == ["DX", "DY", "DZ"]
    (g,) = [g for g in spec["groups"] if g["kind"] == "crush"]
    master = int(card[2][:10])
    assert g["objects"] == [master] and master > max(int(n["id"]) for n in p["nodes"])  # deck'te yeni ana düğüm
    assert g["direction"] == pytest.approx([-1.0, 0.0, 0.0])  # ilk hız yönü


def test_region_nodes_and_explicit_direction(tmp_path):
    p0 = _two_part_params(tmp_path)
    ids = [int(n["id"]) for n in p0["nodes"]][:3]
    _s, spec, _p = _build(tmp_path, region_nodes={"arka": ids}, crush_ref={"region": "arka", "direction": [0, 0, 2]})
    (g,) = [g for g in spec["groups"] if g["kind"] == "crush"]
    assert g["objects"] == sorted(ids) and g["direction"] == pytest.approx([0.0, 0.0, 1.0])


def test_no_crush_ref_no_group(tmp_path):
    s, spec, _p = _build(tmp_path)
    assert "/TH/NODE/8" not in s and not any(g["kind"] == "crush" for g in spec["groups"])


@pytest.mark.parametrize(
    "ref, msg",
    [({"rigid_body": "yok"}, "tanımlı değil"), ({"region": "yok"}, "bu geometride yok")],
)
def test_unknown_reference_is_solver_error(tmp_path, ref, msg):
    with pytest.raises(SolverError, match=msg):
        _build(tmp_path, crush_ref=ref)


def test_crush_ref_validation():
    from pydantic import ValidationError

    from app.solvers.crash_params import CrashCrushRefParams

    with pytest.raises(ValidationError):
        CrashCrushRefParams()
    with pytest.raises(ValidationError):
        CrashCrushRefParams(rigid_body="a", region="b")
    with pytest.raises(ValidationError):
        CrashCrushRefParams(region="b", direction=(0, 0, 0))


def test_crush_distance_projection_mean_and_missing():
    spec = {"groups": [{"kind": "crush", "objects": [7, 9], "vars": ["DX", "DY", "DZ"], "direction": [-1.0, 0.0, 0.0]}]}
    named = {
        "th_crush_7_DX": [0.0, -2.0, -5.0], "th_crush_7_DY": [0.0, 1.0, 1.0], "th_crush_7_DZ": [0.0, 0.0, 0.0],
        "th_crush_9_DX": [0.0, -4.0, -3.0], "th_crush_9_DY": [0.0, 0.0, 0.0], "th_crush_9_DZ": [0.0, 9.0, 9.0],
    }
    # −x yönünde ilerleme = ezilme +; diğer bileşenler izdüşümde düşer
    assert crush_distance(named, spec) == pytest.approx([0.0, 3.0, 4.0])
    named.pop("th_crush_9_DZ")
    assert crush_distance(named, spec) is None
    assert crush_distance({}, {"groups": []}) is None


def test_mean_crush_force_work_until_max_and_ie_ratio():
    from app.postprocess.openradioss_th import mean_crush_force

    # sabit 50 kN, δ 0 → 10 mm, sonra 2 mm geri sekme (iş δ_maks'ta kesilir)
    crush = [0.0, 5.0, 10.0, 8.0]
    force = [50.0, 50.0, 50.0, 0.0]
    s = mean_crush_force(crush, force, ie_final_j=400.0)
    assert s["crush_work_j"] == pytest.approx(500.0)  # 50 kN × 10 mm = 500 J
    assert s["mean_crush_force_kn"] == pytest.approx(50.0)
    assert s["mean_crush_force_ie_kn"] == pytest.approx(400.0 / 8.0)
    # duvar kuvveti yoksa yalnız IE oranı; ezilme yoksa boş
    assert set(mean_crush_force(crush, None, 400.0)) == {"mean_crush_force_ie_kn"}
    assert mean_crush_force([0.0, -1.0], [1.0, 1.0], 10.0) == {}
