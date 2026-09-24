"""Geriye doldurma tepe merkezli ölçütü de yazar (TODO 6 — kalan).

NEDEN: `/backfill-stress-probe` `max_von_mises_away` zaten olan run'ı
TÜMDEN atlıyordu. Mevcut koşuların hepsinde `_away` var → tepe merkezli
`max_von_mises_near_peak` eski koşulara hiç yazılamıyordu.
"""

from __future__ import annotations

import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.api.solve as solve
from app.api.surrogate import backfill_stress_probe
from app.ml.graph_data import NODE_INPUT_CHANNELS, NODE_OUTPUT_CHANNELS
from app.models.base import Base
from app.models.geometry import Geometry
from app.models.run import AnalysisRun


@pytest.fixture()
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'bf.db'}")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _write_sample(runs_dir, run_id: int) -> float:
    """Tepe x=0'da, gerilme uzaklaştıkça doğrusal düşüyor. T=10 → kabuk 2.5–7.5 mm."""
    x = np.arange(0.0, 100.0, 0.5)
    X = np.zeros((x.size, len(NODE_INPUT_CHANNELS)))
    X[:, NODE_INPUT_CHANNELS.index("x")] = x
    Y = np.zeros((x.size, len(NODE_OUTPUT_CHANNELS)))
    Y[:, NODE_OUTPUT_CHANNELS.index("von_mises_mpa")] = 300.0 - x
    d = runs_dir / str(run_id)
    d.mkdir(parents=True)
    np.savez(d / f"run{run_id}.train.npz", node_inputs=X, node_outputs=Y)
    return 300.0 - 2.5  # kabuğun iç kenarı (bkz. stress_near_peak yanlılığı)


def _run(db, scalars: dict) -> AnalysisRun:
    g = Geometry(
        original_filename="k.step", current_filename="k.step", template_id="cantilever_beam",
        template_params={"length": 500.0, "thickness": 10.0, "width": 50.0},
    )
    db.add(g)
    db.flush()
    r = AnalysisRun(geometry_id=g.id, dimension=3, status="solved", scalars=scalars)
    db.add(r)
    db.commit()
    return r


def test_away_dolu_run_a_near_peak_eklenir_ve_ustune_yazilmaz(db, tmp_path, monkeypatch):
    runs_dir = tmp_path / "runs"
    monkeypatch.setattr(solve, "RUNS_DIR", runs_dir)
    r = _run(db, {"max_von_mises": 300.0, "max_von_mises_away": 111.0})
    expected = _write_sample(runs_dir, r.id)

    out = backfill_stress_probe(db=db)

    db.refresh(r)
    assert out["updated_near_peak"] == 1
    assert out["updated_away"] == 0
    assert r.scalars["max_von_mises_near_peak"] == pytest.approx(expected)
    assert r.scalars["peak_probe_offset_mm"] == pytest.approx(5.0)
    assert r.scalars["max_von_mises_away"] == 111.0  # mevcut değer korunur

    again = backfill_stress_probe(db=db)
    assert again["updated"] == 0
    assert again["skipped"] == 1


def test_iki_olcut_de_bossa_ikisi_de_yazilir(db, tmp_path, monkeypatch):
    runs_dir = tmp_path / "runs"
    monkeypatch.setattr(solve, "RUNS_DIR", runs_dir)
    r = _run(db, {"max_von_mises": 300.0})
    _write_sample(runs_dir, r.id)

    out = backfill_stress_probe(db=db)

    db.refresh(r)
    assert out["updated"] == 1
    assert "max_von_mises_near_peak" in r.scalars
    assert out["updated_near_peak"] == 1
