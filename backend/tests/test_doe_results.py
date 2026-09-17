"""DOE skaler sonuç tablosu (0.5.5 okuma tarafı)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.doe.results import _stats, study_results


class FakeQuery:
    def __init__(self, runs):
        self._runs = runs

    def filter(self, *_args, **_kw):
        return self._runs


class FakeDb:
    def __init__(self, runs):
        self._runs = runs

    def query(self, *_args):
        return FakeQuery(self._runs)


def _case(index, params, *, run_id=None, status="solved", element_size=8.0):
    return SimpleNamespace(
        index=index,
        geometry_params=params,
        element_size=element_size,
        material_id=1,
        scenario_name="tip_-y",
        geometry_id=100 + index,
        run_id=run_id,
        status=status,
        message=None,
    )


def _run(run_id, scalars):
    return SimpleNamespace(id=run_id, scalars=scalars)


def _study(cases):
    return SimpleNamespace(id=1, template_id="cantilever_beam", cases=cases)


def _cmp(disp=None, vm=None, *, skipped=None):
    """`templates/compare.py`'ın ürettiği yapı."""
    if skipped:
        return {"skipped": True, "reason": skipped, "warned": False, "metrics": []}
    metrics = []
    for key, pair in (("max_displacement", disp), ("max_von_mises", vm)):
        if pair is None:
            continue
        analytic, fea = pair
        metrics.append(
            {
                "key": key,
                "analytic": analytic,
                "fea": fea,
                "rel_error": abs(fea - analytic) / abs(analytic),
                "warn": False,
            }
        )
    return {"skipped": False, "reason": None, "warned": False, "metrics": metrics}


def test_rows_carry_params_scalars_and_deviation():
    cases = [
        _case(0, {"length": 500.0, "thickness": 10.0, "width": 50.0}, run_id=11),
        _case(1, {"length": 600.0, "thickness": 10.0, "width": 60.0}, run_id=12),
    ]
    runs = [
        _run(11, {"max_displacement": 23.9, "max_von_mises": 330.0, "node_count": 7000,
                  "_analytic_comparison": _cmp(disp=(23.81, 23.9))}),
        _run(12, {"max_displacement": 41.0, "max_von_mises": 400.0, "node_count": 9000,
                  "_analytic_comparison": _cmp(disp=(41.84, 41.0))}),
    ]
    out = study_results(FakeDb(runs), _study(cases))

    # thickness her iki örnekte de aynı: sabit sütun, satırları şişirmiyor
    assert out["param_columns"] == ["length", "width"]
    assert out["constant_params"] == {"thickness": 10.0}
    assert [r["index"] for r in out["rows"]] == [0, 1]
    assert out["rows"][0]["params"] == {"length": 500.0, "width": 50.0}
    assert out["rows"][0]["scalars"]["max_displacement"] == 23.9
    assert out["rows"][0]["dev_displacement_pct"] == pytest.approx(0.378, abs=0.01)
    assert out["rows"][1]["dev_displacement_pct"] == pytest.approx(-2.008, abs=0.01)


def test_deviation_is_signed_not_absolute():
    """`rel_error` işaretsiz; tabloda yön görünmeli (FEA analitiğin altında mı üstünde mi)."""
    cases = [_case(0, {"length": 500.0}, run_id=1), _case(1, {"length": 600.0}, run_id=2)]
    runs = [
        _run(1, {"max_displacement": 24.0, "_analytic_comparison": _cmp(disp=(20.0, 24.0))}),
        _run(2, {"max_displacement": 16.0, "_analytic_comparison": _cmp(disp=(20.0, 16.0))}),
    ]
    rows = study_results(FakeDb(runs), _study(cases))["rows"]
    assert rows[0]["dev_displacement_pct"] == pytest.approx(20.0)
    assert rows[1]["dev_displacement_pct"] == pytest.approx(-20.0)


def test_both_metrics_read_from_comparison():
    cases = [_case(0, {"length": 500.0}, run_id=1)]
    runs = [
        _run(1, {
            "max_displacement": 23.92, "max_von_mises": 330.7,
            "_analytic_comparison": _cmp(disp=(23.81, 23.92), vm=(300.0, 330.7)),
        })
    ]
    row = study_results(FakeDb(runs), _study(cases))["rows"][0]
    assert row["dev_displacement_pct"] == pytest.approx(0.462, abs=0.01)
    assert row["dev_von_mises_pct"] == pytest.approx(10.233, abs=0.01)
    assert row["analytic_skipped"] is None


def test_skipped_comparison_reported_not_silent():
    cases = [_case(0, {"length": 500.0}, run_id=1)]
    runs = [_run(1, {"max_displacement": 24.0, "_analytic_comparison": _cmp(skipped="CLOAD yok")})]
    row = study_results(FakeDb(runs), _study(cases))["rows"][0]
    assert row["dev_displacement_pct"] is None
    assert row["analytic_skipped"] == "CLOAD yok"


def test_unsolved_case_has_null_scalars_not_zero():
    """inp_only örnekte 0 göstermek 'çözüldü ve sıfır çıktı' demek olurdu."""
    # ccx çalıştırılmadığında run kaydı açılır ama skaler yoktur.
    cases = [_case(0, {"length": 500.0}, run_id=1, status="inp_only")]
    row = study_results(FakeDb([_run(1, {})]), _study(cases))["rows"][0]
    assert row["scalars"]["max_displacement"] is None
    assert row["quality"] == "inp_only"

    # Run hiç oluşmamışsa ayrı etiket — sessizce "çözülmedi" sanılmasın.
    orphan = [_case(0, {"length": 500.0}, status="solved")]
    assert study_results(FakeDb([]), _study(orphan))["rows"][0]["quality"] == "missing_run"


def test_non_finite_scalars_are_dropped():
    cases = [_case(0, {"length": 500.0}, run_id=1)]
    runs = [_run(1, {"max_displacement": float("nan"), "max_von_mises": "abc"})]
    row = study_results(FakeDb(runs), _study(cases))["rows"][0]
    assert row["scalars"]["max_displacement"] is None
    assert row["scalars"]["max_von_mises"] is None


def test_quality_flags_rigid_body():
    cases = [_case(0, {"length": 500.0}, run_id=1)]
    runs = [_run(1, {"max_displacement": 1.0e9})]
    assert study_results(FakeDb(runs), _study(cases))["rows"][0]["quality"] == "rigid_body"


# --- istatistik ----------------------------------------------------------------


def test_stats_ignore_missing_values():
    rows = [
        {"scalars": {"max_displacement": 10.0}, "dev_displacement_pct": 1.0},
        {"scalars": {"max_displacement": 20.0}, "dev_displacement_pct": None},
        {"scalars": {"max_displacement": None}, "dev_displacement_pct": 3.0},
    ]
    stats = _stats(rows)
    assert stats["max_displacement"] == {"min": 10.0, "mean": 15.0, "max": 20.0, "n": 2.0}
    assert stats["dev_displacement_pct"]["n"] == 2.0


def test_stats_empty_when_no_values():
    assert _stats([{"scalars": {"max_displacement": None}, "dev_displacement_pct": None}]) == {}


def test_empty_study():
    out = study_results(FakeDb([]), _study([]))
    assert out["rows"] == []
    assert out["param_columns"] == []
    assert out["stats"] == {}
