"""1.19b — crash korpusu: düzleştirme, şablon / senaryo süzgeci, sabit sütun."""

from __future__ import annotations

import math

import numpy as np

from app.ml.crash.corpus import CrashRecord, build_corpus, flatten_numeric
from app.postprocess.crash_targets import TARGET_KEYS


def _rec(run_id: int, speed: float, wall: float, template: str = "crash_box", scenario: str = "rigid_wall",
         scalars: dict | None = None) -> CrashRecord:
    return CrashRecord(
        run_id=run_id,
        job_id=f"job{run_id}",
        template_id=template,
        template_params={"wall_mm": wall, "length_mm": 200.0},
        request={
            "scenario": scenario,
            "use_rigid_wall": True,
            "barrier": {"speed_m_s": speed, "angle_deg": 0.0},
            "parts": [{"part_id": 0, "role": "moving", "thickness_mm": wall}],
        },
        scalars={"rwall_force_max": 10.0 * speed, "internal_energy_final": speed**2}
        if scalars is None else scalars,
    )


def test_flatten_numeric():
    f = flatten_numeric({"a": 1, "b": {"c": True, "d": "x"}, "e": [2.5, {"g": float("nan")}]}, "req")
    assert f == {"req.a": 1.0, "req.b.c": 1.0, "req.e.0": 2.5}


def test_build_corpus_filters_and_tables():
    recs = [
        _rec(1, 5.0, 1.0),
        _rec(2, 10.0, 1.5),
        _rec(3, 7.5, 2.0),
        _rec(4, 10.0, 1.0, template="plate_ball_shell"),
        _rec(5, 10.0, 1.0, scenario="drop"),
        _rec(6, 10.0, 1.0, scalars={}),
    ]
    c = build_corpus(recs, "crash_box", "rigid_wall", curves_loader=lambda _job: {})
    assert c.run_ids == [1, 2, 3]
    assert c.dropped == {"other_template": 1, "other_scenario": 1, "no_target": 1}
    # değişen sütunlar girdi; sabitler ayrı
    assert c.feature_names == ["geom.wall_mm", "req.barrier.speed_m_s", "req.parts.0.thickness_mm"]
    assert c.constant_features["geom.length_mm"] == 200.0
    assert c.constant_features["req.use_rigid_wall"] == 1.0
    assert c.X.shape == (3, 3)
    assert c.X[:, 1].tolist() == [5.0, 10.0, 7.5]
    # hedefler: eğri yok → ortalama kuvvet / ezilme NaN
    assert c.target_names == list(TARGET_KEYS)
    j = c.target_names.index("peak_force_kn")
    assert c.Y[:, j].tolist() == [50.0, 100.0, 75.0]
    assert np.all(np.isnan(c.Y[:, c.target_names.index("crush_mm")]))
    s = c.summary()
    assert s["n_runs"] == 3 and s["targets"]["peak_force_kn"] == 3 and s["targets"]["crush_mm"] == 0


def test_empty_corpus():
    c = build_corpus([], "crash_box", "rigid_wall", curves_loader=lambda _job: {})
    assert c.X.shape == (0, 0) and c.Y.shape == (0, len(TARGET_KEYS))
    assert math.isfinite(len(c.summary()["targets"]))
