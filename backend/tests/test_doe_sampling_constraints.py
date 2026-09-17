"""LHS örnekleme: geçersiz örneklerin elenmesi, sabit parametreler, yük ölçeği.

Kullanıcı kendi aralığını verebildiği için (0.5.4 arayüzü) parametreler
şablonun geometrik kısıtlarını ihlal eden kombinasyonlar üretebilir. Böyle
bir örnek çalıştırılırsa geometri kurulurken patlar ve hem run hem LHS dengesi
kaybolur — bu yüzden örnekleme aşamasında elenip yerine yenisi çekilir.
"""

from __future__ import annotations

import pytest

from app.doe.sampling import DoeSpec, sample_spec

CANTILEVER_BCS = [
    {
        "name": "tip_-y",
        "bcs": [
            {"type": "fixed", "region": "ankastre_uc"},
            {"type": "cload", "region": "yuk_yuzeyi", "fx": 0.0, "fy": -500.0, "fz": 0.0},
        ],
    }
]


def _spec(**kw) -> DoeSpec:
    base = dict(
        template_id="cantilever_beam",
        n_samples=24,
        seed=7,
        geometry={"length": (300.0, 700.0)},
        material_ids=[1],
        bc_scenarios=CANTILEVER_BCS,
    )
    base.update(kw)
    return DoeSpec(**base)


def test_invalid_combinations_are_rejected_and_replaced():
    """L ≥ 5T kısıtı: T aralığı geniş tutulunca LHS ihlal üretir."""
    samples = sample_spec(_spec(geometry={"length": (300.0, 700.0), "thickness": (8.0, 90.0)}))
    assert len(samples) == 24
    for s in samples:
        assert s.geometry_params["length"] >= 5 * s.geometry_params["thickness"]


def test_sampling_is_reproducible_with_seed():
    a = sample_spec(_spec(seed=5))
    b = sample_spec(_spec(seed=5))
    c = sample_spec(_spec(seed=6))
    assert [s.geometry_params for s in a] == [s.geometry_params for s in b]
    assert [s.geometry_params for s in a] != [s.geometry_params for s in c]


def test_ranges_are_respected():
    for s in sample_spec(_spec(element_size=(4.0, 9.0))):
        assert 300.0 <= s.geometry_params["length"] <= 700.0
        assert 4.0 <= s.element_size <= 9.0


def test_impossible_constraints_return_fewer_samples_instead_of_hanging():
    """Hiçbir kombinasyon geçerli değilse sonsuza kadar denemez."""
    samples = sample_spec(
        _spec(geometry={"length": (100.0, 120.0), "thickness": (40.0, 60.0)}, max_resample_passes=3)
    )
    assert samples == []


# --- sabit parametreler ---------------------------------------------------------


def test_fixed_params_are_applied_to_every_sample():
    samples = sample_spec(_spec(fixed_params={"width": 42.0}))
    assert all(s.geometry_params["width"] == 42.0 for s in samples)


def test_fixed_enum_param():
    samples = sample_spec(
        DoeSpec(
            template_id="notched_bar",
            n_samples=4,
            seed=3,
            geometry={"width": (30.0, 50.0)},
            fixed_params={"notch_kind": "v"},
            material_ids=[1],
            bc_scenarios=[
                {
                    "name": "cekme",
                    "bcs": [
                        {"type": "fixed", "region": "tutulan_uc"},
                        {"type": "cload", "region": "yuk_cekme", "fx": 32000.0, "fy": 0.0, "fz": 0.0},
                    ],
                }
            ],
        )
    )
    assert samples and all(s.geometry_params["notch_kind"] == "v" for s in samples)


def test_same_param_fixed_and_swept_is_rejected():
    with pytest.raises(ValueError, match="hem sabit"):
        _spec(fixed_params={"length": 400.0})


# --- yük ölçeği -----------------------------------------------------------------


def test_load_scale_scales_all_components_and_keeps_direction():
    samples = sample_spec(_spec(n_samples=30, load_scale=(0.5, 2.0)))
    fy = [bc["fy"] for s in samples for bc in s.scenario.bcs if bc["type"] == "cload"]
    assert all(v < 0 for v in fy), "yön korunmalı"
    assert min(fy) >= -500.0 * 2.0 - 1e-9
    assert max(fy) <= -500.0 * 0.5 + 1e-9
    assert max(fy) - min(fy) > 100.0, "aralık gerçekten taranmalı"


def test_load_scale_scales_pressure():
    samples = sample_spec(
        DoeSpec(
            template_id="thick_walled_tube",
            n_samples=8,
            seed=1,
            geometry={"length": (80.0, 120.0)},
            material_ids=[1],
            bc_scenarios=[
                {
                    "name": "ic_basinc",
                    "bcs": [
                        {"type": "fixed", "region": "tutulan_uc"},
                        {"type": "pressure", "region": "ic_cidar", "magnitude": 10.0},
                    ],
                }
            ],
            load_scale=(1.0, 3.0),
        )
    )
    mags = [bc["magnitude"] for s in samples for bc in s.scenario.bcs if bc["type"] == "pressure"]
    assert all(10.0 <= m <= 30.0 + 1e-9 for m in mags)
    assert max(mags) - min(mags) > 1.0


@pytest.mark.parametrize("bad", [(2.0, 1.0), (0.0, 2.0), (-1.0, 1.0)])
def test_invalid_load_scale_rejected(bad):
    with pytest.raises(ValueError):
        _spec(load_scale=bad)


# --- oranlı mesh boyutu ---------------------------------------------------------


def test_element_ratio_keeps_resolution_constant_across_geometry():
    """Mutlak mm'de oran geometriyle sürükleniyor; oranlı modda sabit kalıyor."""
    geometry = {"length": (450.0, 700.0), "thickness": (8.0, 12.0)}

    absolute = sample_spec(_spec(n_samples=40, geometry=geometry, element_size=(6.0, 14.0)))
    abs_ratios = [s.element_size / s.geometry_params["thickness"] for s in absolute]
    assert max(abs_ratios) / min(abs_ratios) > 2.0, "mutlak modda çözünürlük çok oynuyor (beklenen)"

    relative = sample_spec(_spec(n_samples=40, geometry=geometry, element_ratio=(0.5, 1.2)))
    rel_ratios = [s.element_size / s.geometry_params["thickness"] for s in relative]
    assert min(rel_ratios) >= 0.5 - 1e-9
    assert max(rel_ratios) <= 1.2 + 1e-9


def test_element_ratio_uses_template_characteristic_length():
    """Delikli plakada karakteristik uzunluk delik çapı — kalınlık değil."""
    samples = sample_spec(
        DoeSpec(
            template_id="plate_with_hole",
            n_samples=6,
            seed=2,
            geometry={"diameter": (10.0, 30.0)},
            element_ratio=(0.15, 0.25),
            material_ids=[1],
            bc_scenarios=[
                {
                    "name": "cekme",
                    "bcs": [
                        {"type": "fixed", "region": "tutulan_uc"},
                        {"type": "cload", "region": "yuk_ucu", "fx": 1000.0, "fy": 0.0, "fz": 0.0},
                    ],
                }
            ],
        )
    )
    for s in samples:
        ratio = s.element_size / s.geometry_params["diameter"]
        assert 0.15 - 1e-9 <= ratio <= 0.25 + 1e-9, ratio
    # Çap taranıyor, oran sabit aralıkta: eleman boyutu çapla birlikte değişmeli.
    sizes = sorted((s.geometry_params["diameter"], s.element_size) for s in samples)
    assert sizes[0][1] < sizes[-1][1]


def test_element_ratio_falls_back_to_absolute_for_unknown_template():
    spec = DoeSpec(
        template_id="yok_boyle_sablon",
        n_samples=3,
        seed=1,
        geometry={"length": (100.0, 200.0)},
        element_size=(5.0, 9.0),
        element_ratio=(0.4, 0.6),
        material_ids=[1],
        bc_scenarios=CANTILEVER_BCS,
    )
    for s in sample_spec(spec):
        assert 5.0 <= s.element_size <= 9.0


@pytest.mark.parametrize("bad", [(0.0, 1.0), (-0.5, 1.0), (1.0, 0.5)])
def test_invalid_element_ratio_rejected(bad):
    with pytest.raises(ValueError):
        _spec(element_ratio=bad)


# --- çoklu malzeme --------------------------------------------------------------


def test_two_materials_split_evenly():
    from collections import Counter

    samples = sample_spec(_spec(n_samples=200, material_ids=[7, 9]))
    counts = Counter(s.material_id for s in samples)
    assert counts == {7: 100, 9: 100}


def test_three_materials_are_balanced():
    from collections import Counter

    counts = Counter(s.material_id for s in sample_spec(_spec(n_samples=90, material_ids=[1, 2, 3])))
    assert set(counts) == {1, 2, 3}
    assert max(counts.values()) - min(counts.values()) <= 1
