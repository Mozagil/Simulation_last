"""1.19c-1 — crash DOE örnekleme: LHS, tohum, yol denetimi, yeniden çekme."""

from __future__ import annotations

import pytest

from app.api.crash_scenario import CRASH_TEMPLATES
from app.doe.crash_sampling import CrashDoeError, CrashDoeSpec, sample_crash_cases


def _spec(**kw) -> CrashDoeSpec:
    body = {
        "base": {"template_id": "crash_box_shell", "t_end_ms": 6.0},
        "vary": {"speed_m_s": (5.0, 15.0), "geometry.wall": (1.0, 3.0), "model.sigma_y_pa": (2.0e8, 4.0e8)},
        "n_samples": 10,
        "seed": 7,
    }
    body.update(kw)
    return CrashDoeSpec.model_validate(body)


def test_lhs_ranges_strata_and_seed():
    cases = sample_crash_cases(_spec())
    assert len(cases) == 10
    speeds = sorted(c["values"]["speed_m_s"] for c in cases)
    # LHS: her 1 m/s dilimde tam bir örnek
    assert [int(s - 5.0) for s in speeds] == list(range(10))
    for c in cases:
        r = c["request"]
        assert r["template_id"] == "crash_box_shell" and r["t_end_ms"] == 6.0
        assert r["speed_m_s"] == c["values"]["speed_m_s"]
        assert r["geometry"]["wall"] == c["values"]["geometry.wall"]
        assert r["model"]["sigma_y_pa"] == c["values"]["model.sigma_y_pa"]
        assert 1.0 <= r["geometry"]["wall"] <= 3.0
    assert sample_crash_cases(_spec()) == cases
    assert sample_crash_cases(_spec(seed=8)) != cases


def test_invalid_samples_are_redrawn():
    # wall ≤ 0 şablon doğrulamasına takılır; kalan örneklerin hepsi geçerli
    cases = sample_crash_cases(_spec(vary={"geometry.wall": (-1.0, 3.0)}, n_samples=6))
    assert len(cases) == 6
    assert all(c["values"]["geometry.wall"] > 0 for c in cases)


@pytest.mark.parametrize("path", ["geometry.nope", "nope_m_s", "model.law", "geometry"])
def test_unknown_or_non_numeric_path(path):
    with pytest.raises(CrashDoeError):
        sample_crash_cases(_spec(vary={path: (1.0, 2.0)}))


def test_bad_bounds():
    with pytest.raises(ValueError):
        _spec(vary={"speed_m_s": (5.0, 5.0)})


@pytest.mark.parametrize("template_id", sorted(CRASH_TEMPLATES))
def test_every_crash_template_samples(template_id):
    spec = CrashDoeSpec(base={"template_id": template_id}, vary={"t_end_ms": (1.0, 2.0)}, n_samples=3)
    cases = sample_crash_cases(spec)
    assert len(cases) == 3 and all(c["request"]["template_id"] == template_id for c in cases)


def test_list_index_path_sled_mass():
    """Kızak kütlesi listede: `rigid_bodies.0.mass_kg` taranır."""
    spec = _spec(
        base={"template_id": "crash_box_shell", "t_end_ms": 6.0,
              "rigid_bodies": [{"name": "kizak", "region": "kutu_arka", "mass_kg": 40.0}]},
        vary={"rigid_bodies.0.mass_kg": (30.0, 50.0)},
    )
    cases = sample_crash_cases(spec)
    assert len(cases) == 10
    for c in cases:
        m = c["request"]["rigid_bodies"][0]["mass_kg"]
        assert 30.0 <= m <= 50.0 and m == c["values"]["rigid_bodies.0.mass_kg"]
    with pytest.raises(CrashDoeError):
        sample_crash_cases(_spec(base=spec.base, vary={"rigid_bodies.3.mass_kg": (1.0, 2.0)}))
