"""Faz 2.6a — küre doğrulama şablonu ve Schiller–Naumann referansı."""

from __future__ import annotations

import pytest

from app.postprocess.sphere_drag import schiller_naumann
from app.templates import TEMPLATES, build_template


@pytest.mark.parametrize("re, cd", [(20, 2.610), (40, 1.735), (100, 1.092)])
def test_schiller_naumann_values(re, cd):
    assert schiller_naumann(re) == pytest.approx(cd, abs=2e-3)


def test_schiller_naumann_stokes_limit_and_validation():
    assert schiller_naumann(0.01) == pytest.approx(24 / 0.01, rel=1e-2)  # Stokes: 24/Re
    with pytest.raises(ValueError):
        schiller_naumann(0)


def test_cfd_sphere_template(tmp_path):
    t = TEMPLATES["cfd_sphere"]
    assert "cfd" in t.tags and t.default_bcs == ()
    built = build_template(t, t.parse_params({"diameter": 80}), tmp_path / "s.step")
    assert built.regions == {"kure": [1]}
    xmin, _, _, xmax, _, _ = built.bounding_box
    assert xmax - xmin == pytest.approx(80, abs=1e-3)


@pytest.mark.parametrize("re, cd", [(20, 2.715), (40, 1.790), (100, 1.088)])
def test_clift_grace_weber_values(re, cd):
    from app.postprocess.sphere_drag import clift_grace_weber

    assert clift_grace_weber(re) == pytest.approx(cd, abs=3e-3)


def test_clift_grace_weber_range():
    from app.postprocess.sphere_drag import clift_grace_weber

    with pytest.raises(ValueError):
        clift_grace_weber(300)
