"""1.17e — SAE J211 CFC filtresi + post-process'e bağlanması; HIC hızlandırma eşdeğerliği."""

from __future__ import annotations

import json
import math
import random

import pytest
from pydantic import ValidationError

from app.postprocess.cfc import cfc_filter, cfc_filter_uniform, sample_ratio
from app.postprocess.hic import hic
from app.postprocess.openradioss_th import parse_openradioss_dir
from app.solvers.crash_params import CrashFilterParams


def _gain(cfc: int, f_hz: float, dt_s: float = 1e-5, n: int = 20000) -> float:
    x = [math.sin(2 * math.pi * f_hz * i * dt_s) for i in range(n)]
    y = cfc_filter_uniform(x, dt_s, cfc)
    return max(abs(v) for v in y[n // 4 : 3 * n // 4])


@pytest.mark.parametrize("cfc", [60, 600, 1000])
def test_frequency_response_in_j211_band(cfc):
    db = lambda g: 20 * math.log10(g)  # noqa: E731
    assert -1.0 <= db(_gain(cfc, 0.5 * cfc)) <= 0.5
    assert -1.0 <= db(_gain(cfc, cfc)) <= 0.5  # geçiş bandı +0.5 / −1 dB
    assert db(_gain(cfc, 1.65 * cfc)) == pytest.approx(-3.0, abs=0.3)
    assert db(_gain(cfc, 10 * cfc)) < -50


def test_nonuniform_time_and_ratio():
    t = [i * 0.002 + (0.0003 if i % 7 == 0 else 0.0) for i in range(500)]  # ms, hafif düzensiz
    v = [1.0] * 500
    assert cfc_filter(t, v, 600) == pytest.approx(v, abs=1e-9)  # sabit sinyal değişmez
    assert sample_ratio([0.0, 0.002], 1000) == pytest.approx(500.0)
    with pytest.raises(ValueError):
        cfc_filter_uniform([0.0, 1.0, 2.0], 1e-5, 100)


def test_filter_params_validated():
    with pytest.raises(ValidationError):
        CrashFilterParams.model_validate({"force_cfc": 100})
    assert CrashFilterParams.model_validate({"acc_cfc": 1000}).acc_cfc == 1000


def test_hic_prefix_sum_matches_direct_definition():
    def direct(t, a, w):
        best = 0.0
        for i in range(len(t) - 1):
            for j in range(i + 1, len(t)):
                dt = t[j] - t[i]
                if dt <= 1e-9 or dt > w + 1e-15:
                    continue
                s = sum(0.5 * (a[k] + a[k + 1]) * (t[k + 1] - t[k]) for k in range(i, j))
                best = max(best, abs(s / dt) ** 2.5 * dt)
        return best

    random.seed(3)
    t = [i * 0.0004 for i in range(60)]
    a = [random.uniform(-50, 300) for _ in t]
    for w in (0.015, 0.004):
        assert hic(t, a, w) == pytest.approx(direct(t, a, w), rel=1e-12)


def test_parser_adds_filtered_curves_keeps_raw(tmp_path):
    # Duvar impulsu: 0.05 ms'de basamak benzeri, gürültülü; düğüm ivmesi tepe.
    n = 400
    t = [i * 0.002 for i in range(n)]
    imp = [min(1.0, max(0.0, (x - 0.1) / 0.05)) * 10.0 for x in t]
    ax = [5000.0 if i == 200 else 0.0 for i in range(n)]
    header = ['"time"', '"barrier_th 1 barrier var 25"', '"barrier_th 1 barrier var 26"',
              '"barrier_th 1 barrier var 27"', '"th_nodes 1 n1 var 28"', '"th_nodes 1 n1 var 29"',
              '"th_nodes 1 n1 var 30"']
    rows = [",".join(str(v) for v in (t[i], imp[i], 0, 0, ax[i], 0, 0)) for i in range(n)]
    (tmp_path / "crashT01.csv").write_text("\n".join([",".join(header), *rows]) + "\n", encoding="utf-8")
    (tmp_path / "th_spec.json").write_text(json.dumps({"groups": [
        {"kind": "rwall", "title": "barrier_th", "objects": [1], "vars": ["FNX", "FNY", "FNZ"]},
        {"kind": "node", "title": "th_nodes", "objects": [1], "vars": ["AX", "AY", "AZ"]},
    ]}), encoding="utf-8")
    (tmp_path / "postprocess.json").write_text(json.dumps({"filters": {"force_cfc": 600, "acc_cfc": 1000}}),
                                                encoding="utf-8")
    rs = parse_openradioss_dir(tmp_path)
    s, c = rs.scalars, rs.curves
    assert "rwall_force" in c and "rwall_force_cfc600" in c  # ham korunur
    assert 0 < s["rwall_force_max_cfc600"] < s["rwall_force_max"]
    assert "th_node_1_AX_cfc1000" in c and "acc_g_cfc1000" in c
    assert s["acc_peak_g_cfc1000"] < s["acc_peak_g"]  # tek örnek tepe süzülünce düşer
    assert s["hic15_cfc1000"] <= s["hic15"]
    assert s["sample_ratio_cfc600"] == pytest.approx(1 / 0.002e-3 / 600)
