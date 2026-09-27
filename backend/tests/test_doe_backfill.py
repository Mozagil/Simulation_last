"""Eski run'ların `doe_study_id` alanını DoeCase'ten doldurma (TODO 8.3).

NEDEN: sütunu ekleyen migration mevcut satırları doldurmadı; ~800 run
"DOE dışı" görünüyor ve geçmiş setler `?doe_study_id=` ile süzülemiyor.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.doe.backfill import backfill_doe_study_ids, conflicting_rows, pending_counts
from app.models.base import Base
from app.models.doe import DoeCase, DoeStudy
from app.models.geometry import Geometry
from app.models.run import AnalysisRun


@pytest.fixture()
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'b.db'}")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _run(db, *, study_id=None):
    g = Geometry(original_filename="k.step", current_filename="k.step",
                 template_id="cantilever_beam", template_params={"length": 500.0})
    db.add(g)
    db.flush()
    r = AnalysisRun(
        geometry_id=g.id, dimension=3, element_size=8.0, element_scheme="tet",
        bcs=[{"type": "fixed", "face_ids": [1]}],
        materials_snapshot=[{"youngs_modulus": 210e9, "poisson_ratio": 0.3}],
        status="solved", doe_study_id=study_id,
    )
    db.add(r)
    db.flush()
    return r


def _study(db, name):
    st = DoeStudy(name=name, template_id="cantilever_beam", seed=0, spec={})
    db.add(st)
    db.flush()
    return st


def _case(db, study, run, index=0):
    c = DoeCase(study_id=study.id, index=index, geometry_params={}, element_size=8.0,
                material_id=1, scenario_name="uc_yuku",
                geometry_id=run.geometry_id if run else None,
                run_id=run.id if run else None, status="solved")
    db.add(c)
    db.flush()
    return c


def _sid(db, run):
    db.expire(run)
    return run.doe_study_id


# --- ana yol ------------------------------------------------------------------


def test_bos_alan_doe_casten_doldurulur(db):
    st = _study(db, "kiris-egitim-v2")
    runs = [_run(db) for _ in range(3)]
    for i, r in enumerate(runs):
        _case(db, st, r, index=i)
    db.commit()

    report = backfill_doe_study_ids(db.connection())
    db.commit()

    assert report["filled"] == 3
    assert report["per_study"] == {st.id: 3}
    assert [_sid(db, r) for r in runs] == [st.id] * 3


def test_dolu_alan_ezilmez(db):
    st_a, st_b = _study(db, "a"), _study(db, "b")
    run = _run(db, study_id=st_a.id)
    _case(db, st_b, run)
    db.commit()

    report = backfill_doe_study_ids(db.connection())
    db.commit()

    assert report["filled"] == 0
    assert _sid(db, run) == st_a.id, "elle/önceden yazılmış değer korunur"
    assert report["conflicts"] == [
        {"run_id": run.id, "run_study_id": st_a.id, "case_study_id": st_b.id}
    ]


def test_ikinci_kosu_bos_gecer(db):
    """Migration yeniden çalıştırılabilir olmalı."""
    st = _study(db, "s")
    run = _run(db)
    _case(db, st, run)
    db.commit()

    backfill_doe_study_ids(db.connection())
    db.commit()
    again = backfill_doe_study_ids(db.connection())
    db.commit()

    assert again["filled"] == 0
    assert _sid(db, run) == st.id


def test_doe_disi_run_bos_kalir(db):
    """Elle açılmış koşular gerçekten DOE dışı — uydurma çalışma atanmaz."""
    st = _study(db, "s")
    in_doe, manual = _run(db), _run(db)
    _case(db, st, in_doe)
    db.commit()

    backfill_doe_study_ids(db.connection())
    db.commit()

    assert _sid(db, in_doe) == st.id
    assert _sid(db, manual) is None


def test_belirsiz_run_dokunulmaz(db):
    """İki çalışma aynı run'a bakıyorsa hangisi olduğu bilinemez."""
    st_a, st_b = _study(db, "a"), _study(db, "b")
    shared, clean = _run(db), _run(db)
    _case(db, st_a, shared)
    _case(db, st_b, shared, index=1)
    _case(db, st_a, clean, index=2)
    db.commit()

    report = backfill_doe_study_ids(db.connection())
    db.commit()

    assert report["ambiguous_run_ids"] == [shared.id]
    assert _sid(db, shared) is None
    assert _sid(db, clean) == st_a.id, "belirsiz olan diğerlerini engellemez"


def test_kosulmamis_case_run_id_yok(db):
    """`run_id` boş case'ler (pending/failed) sorguyu bozmamalı."""
    st = _study(db, "s")
    _case(db, st, None)
    run = _run(db)
    _case(db, st, run, index=1)
    db.commit()

    report = backfill_doe_study_ids(db.connection())
    db.commit()

    assert report["filled"] == 1
    assert _sid(db, run) == st.id


# --- yazmadan bakma ------------------------------------------------------------


def test_dry_run_yazmaz(db):
    st = _study(db, "s")
    run = _run(db)
    _case(db, st, run)
    db.commit()

    report = backfill_doe_study_ids(db.connection(), dry_run=True)
    db.commit()

    assert report["fillable"] == 1 and report["filled"] == 0
    assert _sid(db, run) is None


def test_pending_counts_calisma_bazinda(db):
    st_a, st_b = _study(db, "a"), _study(db, "b")
    for i in range(2):
        _case(db, st_a, _run(db), index=i)
    _case(db, st_b, _run(db))
    _case(db, st_b, _run(db, study_id=st_b.id), index=1)  # zaten dolu
    db.commit()

    assert pending_counts(db.connection()) == {st_a.id: 2, st_b.id: 1}
    assert conflicting_rows(db.connection()) == []
