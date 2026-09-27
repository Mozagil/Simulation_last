"""GNN şablon başına saklanır (TODO 1.3b — kapsam).

NEDEN: `/gnn/train` şablona göre süzüyor ama sonucu hep tek global
`field_gnn.npz`'ye yazıyordu — plaka eğitimi kiriş modelini eziyordu.
Skaler modellerde (`ml/model_store`) kapattığımız hatanın aynısı.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.api.surrogate as api
import app.ml.model_store as store
from app.ml.gnn import save_gnn, train_gnn
from app.ml.model_store import gnn_path, load_template_gnn
from app.models.base import Base
from app.models.geometry import Geometry
from app.models.run import AnalysisRun
from tests.test_surrogate import _line_sample

PLATE = "plate_with_hole"
BEAM = "cantilever_beam"


@pytest.fixture()
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'gnn.db'}")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


@pytest.fixture()
def store_root(tmp_path, monkeypatch):
    """Model deposu geçici klasöre — gerçek uploads/ kirlenmesin."""
    root = tmp_path / "models"
    monkeypatch.setattr(store, "MODELS_ROOT", root)
    return root


@pytest.fixture()
def fake_graphs(monkeypatch):
    """Diskte `.train.npz` yok: her run için küçük sentetik graf; eğitim hızlı."""
    monkeypatch.setattr(
        api, "load_graph", lambda path, run_id=None: _line_sample(1.0 + 0.01 * (run_id or 0))
    )
    real = train_gnn
    monkeypatch.setattr(
        api, "train_gnn", lambda samples, **kw: real(samples, seed=0, hidden=8, engine="numpy")
    )


def _bundle(scale: float = 1.0) -> dict:
    return train_gnn([_line_sample(scale), _line_sample(scale * 1.05)],
                     seed=0, hidden=8, engine="numpy")


def _runs(db, template_ids: list[str | None]) -> list[int]:
    ids = []
    for tpl in template_ids:
        g = Geometry(original_filename="g.step", current_filename="g.step", template_id=tpl)
        db.add(g)
        db.flush()
        r = AnalysisRun(geometry_id=g.id, dimension=3, element_size=5.0, status="solved")
        db.add(r)
        db.flush()
        ids.append(r.id)
    db.commit()
    return ids


def _use_run_ids(monkeypatch, ids: list[int]) -> None:
    """Korpus süzgecini atla — konu kapsam, süzgeç değil."""
    monkeypatch.setattr(
        api, "_corpus_run_ids", lambda db, name, tpl: (ids, None, {"run_ids": ids})
    )
    monkeypatch.setattr(
        api, "_frozen_summary", lambda data, n: {"n_kept": n, "dropped": {}}
    )


def test_egitim_sablon_klasorune_yazar_digerini_ezmez(db, store_root, fake_graphs, monkeypatch):
    beam = _bundle()
    beam["template_id"] = BEAM
    save_gnn(beam, gnn_path(BEAM))
    beam_bytes = gnn_path(BEAM).read_bytes()
    _use_run_ids(monkeypatch, _runs(db, [PLATE, PLATE, PLATE]))

    out = api.train_field_gnn(db=db, template_id=PLATE, corpus_name="x")

    assert out["template_id"] == PLATE
    assert out["path"] == str(store_root / PLATE / "field_gnn.npz")
    assert load_template_gnn(PLATE)["template_id"] == PLATE
    # Kiriş modeli olduğu gibi duruyor; global dosya hiç yazılmadı.
    assert gnn_path(BEAM).read_bytes() == beam_bytes
    assert not (store_root / "field_gnn.npz").exists()


def test_karisik_sablonlu_korpus_reddedilir(db, store_root, fake_graphs, monkeypatch):
    _use_run_ids(monkeypatch, _runs(db, [PLATE, BEAM, PLATE]))
    with pytest.raises(HTTPException) as exc:
        api.train_field_gnn(db=db, template_id=None, corpus_name="x")
    assert exc.value.status_code == 422
    assert "birden çok şablon" in exc.value.detail
    assert not store_root.exists() or not any(store_root.rglob("*.npz"))


def test_sablonsuz_run_atilir_ve_raporlanir(db, store_root, fake_graphs, monkeypatch):
    _use_run_ids(monkeypatch, _runs(db, [PLATE, None, PLATE, PLATE]))
    out = api.train_field_gnn(db=db, template_id=PLATE, corpus_name="x")
    assert out["n_samples"] == 3
    assert out["corpus"]["dropped"]["no_template"] == 1


def test_sablonsuz_korpus_egitilemez(db, store_root, fake_graphs, monkeypatch):
    _use_run_ids(monkeypatch, _runs(db, [None, None]))
    with pytest.raises(HTTPException) as exc:
        api.train_field_gnn(db=db, template_id=None, corpus_name="x")
    assert exc.value.status_code == 422


def test_eski_global_dosya_yalniz_kendi_sablonuna_verilir(store_root):
    legacy = store_root / "field_gnn.npz"
    save_gnn(_bundle(), legacy)  # şablon kaydı yok — bugünkü diskteki dosya gibi
    assert load_template_gnn(BEAM) is None

    tagged = _bundle()
    tagged["template_id"] = BEAM
    save_gnn(tagged, legacy)
    assert load_template_gnn(BEAM)["legacy_path"] == str(legacy)
    assert load_template_gnn(PLATE) is None


def test_status_sablonun_gnnini_doner(store_root):
    plate = _bundle()
    plate["template_id"] = PLATE
    save_gnn(plate, gnn_path(PLATE))

    assert api.surrogate_status(template_id=PLATE)["field_gnn"]["template_id"] == PLATE
    assert api.surrogate_status(template_id=BEAM)["field_gnn"] is None


def test_gecersiz_sablon_adi_reddedilir(store_root):
    with pytest.raises(store.ModelStoreError):
        gnn_path("../kiris")
