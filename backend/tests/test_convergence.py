"""0.6.1 mesh yakınsama: basamak çözümü, sıralama, sapma sütunları.

Solver çağrılmaz — bu testler tanımın ve rapor aritmetiğinin testi.
Gerçek ccx taraması ayrı bir doğrulama adımı (bkz. PR açıklaması).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.doe.convergence import (
    CONVERGENCE_TARGETS,
    ConvergenceSpec,
    build_report,
    resolve_steps,
)


def _spec(**kw) -> ConvergenceSpec:
    base = dict(
        template_id="cantilever_beam",
        params={"length": 500.0, "thickness": 10.0, "width": 50.0},
        material_id=1,
        element_ratios=[1.2, 0.5, 0.8],
    )
    base.update(kw)
    return ConvergenceSpec.model_validate(base)


def _row(index: int, size: float, disp: float | None, vm: float | None, status="solved"):
    scalars = {}
    if disp is not None:
        scalars["max_displacement"] = disp
    if vm is not None:
        scalars["max_von_mises"] = vm
    return {
        "index": index,
        "element_size": size,
        "ratio": None,
        "run_id": 100 + index,
        "status": status,
        "node_count": int(10000 / size),
        "scalars": scalars,
    }


# --- tanım ---------------------------------------------------------------


def test_ratios_become_sizes_via_characteristic_length():
    # Ankastre kirişte karakteristik uzunluk = kalınlık (T=10) → es = oran × 10
    steps = resolve_steps(_spec(element_ratios=[1.2, 0.5, 0.8]))
    assert [s["element_size"] for s in steps] == [12.0, 8.0, 5.0]
    assert [s["ratio"] for s in steps] == [1.2, 0.8, 0.5]


def test_steps_are_sorted_coarse_to_fine():
    steps = resolve_steps(_spec(element_ratios=None, element_sizes=[4.0, 12.0, 8.0]))
    sizes = [s["element_size"] for s in steps]
    assert sizes == sorted(sizes, reverse=True)
    assert all(s["ratio"] is None for s in steps)


@pytest.mark.parametrize(
    "kw",
    [
        {"element_sizes": [4.0, 8.0], "element_ratios": [0.5, 1.0]},  # ikisi birden
        {"element_sizes": None, "element_ratios": None},  # hiçbiri
        {"element_ratios": [0.5]},  # tek basamak yakınsama göstermez
        {"element_ratios": [0.5, 0.5]},  # yinelenen
        {"element_ratios": [0.5, -1.0]},  # pozitif olmalı
        {"element_ratios": [0.5, 1.0], "dimension": 1},
        {"element_ratios": [0.5, 1.0], "element_scheme": "wedge"},
    ],
)
def test_invalid_specs_are_rejected(kw):
    with pytest.raises(ValidationError):
        _spec(**kw)


# --- rapor aritmetiği ----------------------------------------------------


def test_deltas_are_relative_to_previous_and_finest():
    rows = [
        _row(0, 12.0, 20.0, 100.0),
        _row(1, 8.0, 22.0, 120.0),
        _row(2, 5.0, 22.0, 150.0),  # en ince
    ]
    report = build_report(rows)
    disp = [r["targets"]["max_displacement"] for r in report["rows"]]

    assert disp[0]["delta_prev_pct"] is None  # ilk satırın öncesi yok
    assert disp[1]["delta_prev_pct"] == pytest.approx(10.0)  # 20 → 22
    assert disp[2]["delta_prev_pct"] == pytest.approx(0.0)  # 22 → 22 yakınsadı
    assert disp[0]["delta_finest_pct"] == pytest.approx(-100.0 * 2 / 22)
    assert disp[2]["delta_finest_pct"] == pytest.approx(0.0)

    # von Mises yakınsamıyor: en ince iki adım arasında hâlâ %25 oynuyor.
    # (Ankastre köşe tekilliğinin beklenen davranışı; rapor bunu gizlemez.)
    assert report["summary"]["max_von_mises"]["last_step_delta_pct"] == pytest.approx(25.0)
    assert report["summary"]["max_displacement"]["last_step_delta_pct"] == pytest.approx(0.0)


def test_summary_reports_finest_mesh():
    rows = [_row(0, 12.0, 20.0, 100.0), _row(1, 5.0, 22.0, 150.0)]
    report = build_report(rows)
    assert report["n_steps"] == 2
    assert report["n_solved"] == 2
    assert list(report["targets"]) == list(CONVERGENCE_TARGETS)
    assert report["summary"]["max_displacement"]["finest"] == pytest.approx(22.0)
    assert report["summary"]["max_displacement"]["finest_element_size"] == 5.0


def test_failed_step_stays_as_row_but_is_skipped_in_deltas():
    rows = [
        _row(0, 12.0, 20.0, 100.0),
        _row(1, 8.0, None, None, status="failed"),
        _row(2, 5.0, 21.0, 110.0),
    ]
    report = build_report(rows)
    disp = [r["targets"]["max_displacement"] for r in report["rows"]]

    assert report["n_steps"] == 3
    assert report["n_solved"] == 2
    assert disp[1]["value"] is None
    assert disp[1]["delta_prev_pct"] is None
    # Patlayan basamak atlanır: 5 mm, 12 mm ile kıyaslanır (8 mm ile değil).
    assert disp[2]["delta_prev_pct"] == pytest.approx(5.0)
    # En ince = son ÇÖZÜLEN satır.
    assert report["summary"]["max_displacement"]["finest"] == pytest.approx(21.0)


def test_no_solved_step_yields_empty_summary_not_crash():
    rows = [_row(0, 12.0, None, None, status="failed")]
    report = build_report(rows)
    assert report["n_solved"] == 0
    assert report["summary"]["max_displacement"]["finest"] is None
    assert report["rows"][0]["targets"]["max_displacement"]["delta_finest_pct"] is None
