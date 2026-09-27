"""Eski eğitim dosyalarına mesh bağlantısını geriye doldurma (TODO 1.1c).

NEDEN: bağlantı yazımı düzeltildi ama yalnız YENİ koşular için; diskteki
550 `.train.npz` dosyasının grafı hâlâ k-NN. Doldurma mesh'ten yapılır,
ama mesh dosyaları geometri adına göre ÜZERİNE YAZILIYOR — bu yüzden
koordinat kilidi kritik: uymayan mesh'le doldurmak, doldurmamaktan kötü.
"""

from __future__ import annotations

import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.dataset.connectivity_backfill as cb
from app.dataset.training_data import pad_connectivity, write_inputs
from app.models.base import Base
from app.models.geometry import Geometry
from app.models.run import AnalysisRun

COORDS = np.array(
    [[0.0, 0, 0], [10.0, 0, 0], [0, 10.0, 0], [0, 0, 10.0]], dtype=np.float64
)
CONN = pad_connectivity([[1, 2, 3, 4]])
ETYPES = np.array(["C3D4"], dtype="<U8")


@pytest.fixture()
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'c.db'}")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


@pytest.fixture()
def roots(tmp_path):
    runs, meshes = tmp_path / "runs", tmp_path / "meshes"
    runs.mkdir()
    meshes.mkdir()
    return runs, meshes


def _make_run(db, roots, *, coords=COORDS, with_conn=False, mesh=True):
    runs_root, meshes_root = roots
    g = Geometry(
        original_filename="k.step",
        current_filename="7.step",
        template_id="cantilever_beam",
        template_params={"length": 10.0},
    )
    db.add(g)
    db.flush()
    r = AnalysisRun(
        geometry_id=g.id,
        dimension=3,
        element_size=5.0,
        element_scheme="tet",
        bcs=[{"type": "fixed", "face_ids": [1]}],
        materials_snapshot=[{"youngs_modulus": 210e9, "poisson_ratio": 0.3}],
        status="solved",
    )
    db.add(r)
    db.flush()

    d = runs_root / str(r.id)
    d.mkdir()
    X = np.zeros((coords.shape[0], 14), dtype=np.float32)
    X[:, :3] = coords
    p = d / "run.train.npz"
    write_inputs(p, X, CONN if with_conn else None, element_types=ETYPES if with_conn else None)
    if mesh:
        (meshes_root / "7_d3.msh").write_text("sahte mesh", encoding="utf-8")
    db.commit()
    return r, g, p


@pytest.fixture()
def fake_mesh(monkeypatch):
    """`build_input` yerine sabit bağlantı — gmsh'siz test."""
    calls: list[tuple[int, str]] = []

    def fake(run, mesh_path, workdir, coords=COORDS):
        calls.append((run.id, mesh_path.name))
        return CONN, ETYPES, coords

    monkeypatch.setattr(cb, "connectivity_from_mesh", fake)
    return calls


# --- ana yol ------------------------------------------------------------------


def test_eksik_baglanti_doldurulur(db, roots, fake_mesh):
    run, geo, path = _make_run(db, roots)
    assert not cb.has_connectivity(path)

    status, note, written = cb.backfill_run(
        run, geo, runs_root=roots[0], meshes_root=roots[1]
    )

    assert status == cb.OK and written == 1
    assert cb.has_connectivity(path)
    with np.load(path, allow_pickle=False) as z:
        assert z["connectivity"].tolist() == CONN.tolist()
        assert list(z["element_types"]) == ["C3D4"]


def test_cikti_ve_girdiler_korunur(db, roots, fake_mesh):
    """Doldurma, dosyadaki eğitim ÇIKTILARINI bozmamalı."""
    run, geo, path = _make_run(db, roots)
    with np.load(path, allow_pickle=False) as z:
        data = {k: z[k] for k in z.files}
    data["node_outputs"] = np.arange(16, dtype=np.float32).reshape(4, 4)
    np.savez_compressed(path, **data)

    cb.backfill_run(run, geo, runs_root=roots[0], meshes_root=roots[1])

    with np.load(path, allow_pickle=False) as z:
        assert z["node_outputs"].tolist() == np.arange(16).reshape(4, 4).tolist()
        assert z["node_inputs"].shape == (4, 14)
        assert z["connectivity"].size > 0


def test_zaten_dolu_dosyaya_dokunulmaz(db, roots, fake_mesh):
    run, geo, path = _make_run(db, roots, with_conn=True)
    before = path.read_bytes()

    status, _, written = cb.backfill_run(
        run, geo, runs_root=roots[0], meshes_root=roots[1]
    )

    assert (status, written) == (cb.ALREADY, 0)
    assert path.read_bytes() == before
    assert fake_mesh == [], "mesh hiç açılmamalı"


# --- güvenlik kilidi ----------------------------------------------------------


def test_koordinat_uymazsa_yazilmaz(db, roots, monkeypatch):
    """Mesh başka eleman boyutuyla ezilmişse bağlantı hizasızdır."""
    run, geo, path = _make_run(db, roots)
    kaymis = COORDS + 0.5
    monkeypatch.setattr(
        cb, "connectivity_from_mesh", lambda r, m, w: (CONN, ETYPES, kaymis)
    )

    status, note, written = cb.backfill_run(
        run, geo, runs_root=roots[0], meshes_root=roots[1]
    )

    assert status == cb.MISMATCH and written == 0
    assert "0.5" in note
    assert not cb.has_connectivity(path)


def test_dugum_sayisi_uymazsa_yazilmaz(db, roots, monkeypatch):
    run, geo, path = _make_run(db, roots)
    monkeypatch.setattr(
        cb, "connectivity_from_mesh", lambda r, m, w: (CONN, ETYPES, COORDS[:3])
    )

    status, note, _ = cb.backfill_run(run, geo, runs_root=roots[0], meshes_root=roots[1])

    assert status == cb.MISMATCH
    assert "4" in note and "3" in note
    assert not cb.has_connectivity(path)


def test_float32_yuvarlamasi_engel_degil(db, roots, monkeypatch):
    """`node_inputs` float32; mesh koordinatı çift duyarlı — fark tolerans içinde."""
    run, geo, path = _make_run(db, roots, coords=COORDS + 1e-7)
    monkeypatch.setattr(
        cb, "connectivity_from_mesh", lambda r, m, w: (CONN, ETYPES, COORDS)
    )

    status, _, _ = cb.backfill_run(run, geo, runs_root=roots[0], meshes_root=roots[1])

    assert status == cb.OK


def test_mesh_yoksa_atlanir(db, roots, fake_mesh):
    run, geo, path = _make_run(db, roots, mesh=False)
    status, note, _ = cb.backfill_run(run, geo, runs_root=roots[0], meshes_root=roots[1])
    assert status == cb.NO_MESH
    assert note == "7_d3.msh"
    assert not cb.has_connectivity(path)


def test_dry_run_yazmaz(db, roots, fake_mesh):
    run, geo, path = _make_run(db, roots)
    status, _, written = cb.backfill_run(
        run, geo, runs_root=roots[0], meshes_root=roots[1], dry_run=True
    )
    assert (status, written) == (cb.OK, 1)
    assert not cb.has_connectivity(path), "yazmadan yalnız doğrulama"


# --- toplu tarama --------------------------------------------------------------


def test_egitim_dosyasi_olmayan_run_raporda_yok(db, roots, fake_mesh):
    _make_run(db, roots)
    g = Geometry(original_filename="b.step", current_filename="9.step")
    db.add(g)
    db.flush()
    db.add(
        AnalysisRun(
            geometry_id=g.id,
            dimension=3,
            element_size=5.0,
            element_scheme="tet",
            bcs=[],
            materials_snapshot=[],
            status="pending",
        )
    )
    db.commit()

    rep = cb.backfill_all(db, runs_root=roots[0], meshes_root=roots[1])

    assert rep.counts == {cb.OK: 1}
    assert rep.files_written == 1


def test_bir_run_patlarsa_tarama_surer(db, roots, monkeypatch):
    r1, _, p1 = _make_run(db, roots)
    r2, _, p2 = _make_run(db, roots)

    def bombali(run, mesh_path, workdir):
        if run.id == r1.id:
            raise RuntimeError("gmsh coktu")
        return CONN, ETYPES, COORDS

    monkeypatch.setattr(cb, "connectivity_from_mesh", bombali)
    rep = cb.backfill_all(db, runs_root=roots[0], meshes_root=roots[1])

    assert rep.counts == {cb.ERROR: 1, cb.OK: 1}
    assert not cb.has_connectivity(p1)
    assert cb.has_connectivity(p2)


def test_run_ids_ile_sinirlanir(db, roots, fake_mesh):
    r1, _, p1 = _make_run(db, roots)
    r2, _, p2 = _make_run(db, roots)

    rep = cb.backfill_all(
        db, runs_root=roots[0], meshes_root=roots[1], run_ids=[r2.id]
    )

    assert rep.files_written == 1
    assert not cb.has_connectivity(p1)
    assert cb.has_connectivity(p2)
