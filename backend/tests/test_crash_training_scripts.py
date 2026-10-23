"""Crash eğitim testleri betikleri — adım planı, istek mutasyonları, özellik dizini, kurulum farkı."""

import copy

from scripts.crash_training_report import diff, features, training_texts
from scripts.crash_training_runs import MODELS, plan

BASE = {
    "geometry_id": 1, "dimension": 2, "t_end_ms": 20.0, "use_rigid_wall": True,
    "barrier": {"speed_m_s": 10.0, "angle_deg": 0.0,
                "wall": {"kind": "plane", "point": [0.0, 25.0, 20.0], "normal": [1.0, 0.0, 0.0]}},
    "model": {"law": "plastic"}, "parts": [{"part_id": 0, "role": "moving", "thickness_mm": 3.0}],
    "rigid_bodies": [{"name": "kizak", "region": "kutu_arka", "mass_kg": 100.0}],
    "boundary_conditions": [], "contacts": [], "springs": [],
}


def test_plan_belgedeki_testleri_kapsar():
    steps = plan()
    keys = [s.key for s in steps]
    assert len(keys) == len(set(keys))
    assert {s.test for s in steps} == {f"T{i}" for i in range(1, 31)}
    assert set(training_texts()) == {f"T{i}" for i in range(1, 31)}
    for s in steps:
        assert s.model in MODELS or s.model == "M5x"
        assert not s.base or s.base in MODELS
        if s.kind.startswith("reuse:"):
            assert s.kind.split(":", 1)[1] in keys


def test_mutasyonlar_tabani_bozmaz_ve_tek_seyi_degistirir():
    by = {s.key: s for s in plan()}
    base = copy.deepcopy(BASE)
    r = by["T2b"].mutate(copy.deepcopy(base), {})
    assert r["model"]["harden_b_mpa"] == 500.0 and r["model"]["harden_n"] == 0.5
    assert base == BASE
    r = by["T6c"].mutate(copy.deepcopy(base), {})
    assert r["barrier"]["wall"]["normal"] == [-1.0, 0.0, 0.0]
    r = by["T21b"].mutate(copy.deepcopy(base), {"T21a": {"scalars": {"model_disp_peak_t_ms": 12.5}}})
    assert r["t_end_ms"] == 40.0 and r["damping"]["t_start_ms"] == 12.5 and r["damping"]["beta_s"] == 1e-5
    r = by["T22c"].mutate(copy.deepcopy(base), {})
    assert r["springs"][0]["k_n_per_mm"] == 500.0 and r["springs"][0]["c_n_s_per_mm"] == 20.0
    assert r["springs"][0]["end_a"] == {"rigid_body": "kizak"}


def test_ozellik_dizini_ve_fark():
    r = copy.deepcopy(BASE)
    r["boundary_conditions"] = [{"name": "kizak_ray", "rigid_body": "kizak", "dofs": "011111"}]
    r["springs"] = [{"name": "yay_1", "end_a": {"rigid_body": "kizak"},
                     "end_b": {"point": [-50.0, 25.0, 20.0], "fixed": True}, "k_n_per_mm": 500.0}]
    r["damping"] = {"alpha_per_s": 0.0, "beta_s": 1e-5, "part_ids": [0], "t_start_ms": 10.0}
    names = [n for n, _ in features(r)]
    for want in ("Rijit duvar", "İlk hız (/INIVEL)", "Kızak / rijit gövde (/RBODY + kütle)",
                 "Ray (kızak yönlendirme, /BCS)", "Yay (/SPRING + /PROP/TYPE4)", "Rayleigh sönüm (/DAMP)"):
        assert want in names
    d = diff(BASE, r)
    assert any(x.startswith("damping.beta_s") for x in d)
    assert not any(x.startswith("geometry_id") for x in diff(BASE, {**BASE, "geometry_id": 9}))


def test_fiziksel_okuma_sekme_durma_bitmedi():
    from scripts.crash_training_report import physical_reading

    # T1a (#384) elastik: impuls 2017 N·s ≈ 2·m·v → sekme
    sc = {"mass_model": 101.2, "kinetic_energy_max": 5077.6, "kinetic_energy_final": 5038.1, "internal_energy_final": 101.5,
          "rwall_impulse_final": 2017.2, "energy_balance_rel": 0.0246, "hourglass_ratio": 0.33, "mass_added_rel": 0.0}
    what, chk = physical_reading(sc, BASE)
    assert what.startswith("Geri sekti") and "1.99·p₀" in what
    assert any("HG / IE" in c and "AŞIYOR" in c for c in chk)
    assert any("Enerji dengesi" in c and "içinde" in c for c in chk)
    # T1b (#385) plastik: impuls 0.75·p₀, KE %8 duruyor → bitmedi
    sc = {**sc, "kinetic_energy_final": 386.2, "internal_energy_final": 4320.0, "rwall_impulse_final": 755.2,
          "hourglass_ratio": 0.08}
    what, _ = physical_reading(sc, BASE)
    assert what.startswith("Çarpma bitmedi")
    # tam durma
    what, _ = physical_reading({**sc, "kinetic_energy_final": 5.0, "rwall_impulse_final": 1015.0}, BASE)
    assert what.startswith("Durdu")
    # yay varsa impuls–momentum kontrolü yok
    r = copy.deepcopy(BASE)
    r["springs"] = [{"name": "yay_1", "k_n_per_mm": 500.0}]
    what, chk = physical_reading(sc, r)
    assert "impuls–momentum kontrolü yapılmadı" in what and not any("p₀" in c for c in chk)


def test_duvardan_ayrilma_ve_yanal_yer_degistirme():
    from scripts.crash_training_report import contact_end_ms, lateral_peak_mm, physical_reading

    t = [i * 0.5 for i in range(41)]  # 0–20 ms
    assert contact_end_ms(t, [100.0 if x <= 13.5 else 0.0 for x in t]) == 13.5
    assert contact_end_ms(t, [100.0] * 41) is None
    anim = {"frames": [{"positions": [0.0, 0.0, 0.0, 300.0, 0.0, 0.0]},
                       {"positions": [25.0, 0.0, -140.0, 220.0, 0.0, 0.0]}]}
    assert abs(lateral_peak_mm(anim, [1.0, 0.0, 0.0]) - 140.0) < 1e-9
    # T5 (#392): kuvvet 13.6 ms'de biter, IE sabit, impuls 0.84·p₀
    sc = {"mass_model": 101.2, "kinetic_energy_final": 154.0, "internal_energy_final": 4572.5,
          "internal_energy_max": 4572.5, "rwall_impulse_final": 851.0}
    what, chk = physical_reading(sc, BASE, 5058.9, 13.6, 158.6)
    assert what.startswith("Duvardan ayrıldı") and "elastik sekme değil" in what and "158.6 mm" in what
    assert any("13.6 ms" in c for c in chk)
