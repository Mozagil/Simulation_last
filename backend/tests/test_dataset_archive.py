"""Veri seti dışa/içe aktarma testleri.

Gerçek kayıp: Codespace silinince hem Postgres volume'ü hem `uploads/`
gitti, tüm analiz geçmişi kayboldu. Surrogate eğitim verisi için hem
satırlar hem `.frd` alan verisi gerektiğinden arşiv ikisini de taşır.
"""

import json
import tarfile
from pathlib import Path

import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.dataset.archive import DATASET_FORMAT_VERSION, export_dataset, import_dataset
from app.models.base import Base
from app.models.geometry import Geometry
from app.models.material import Material
from app.models.run import AnalysisRun


@pytest.fixture()
def db_session(tmp_path):
    """Dosya tabanlı geçici SQLite oturumu.

    Projede paylaşılan bir `db_session` fixture'ı yok ve bu testlerin
    Postgres'e ihtiyacı yok: arşivleme mantığı ORM üzerinden çalışır,
    veritabanı motorundan bağımsızdır. Paylaşılan test altyapısına
    dokunmamak için fixture dosya içinde tutuluyor.
    """
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _seed(db, uploads: Path) -> int:
    """Bir geometri + bir malzeme + bir çözülmüş run kurar, run dosyası yazar."""
    g = Geometry(
        original_filename="plaka.step",
        current_filename="plaka.step",
        template_id="cantilever_beam",
        template_params={"length": 500.0},
    )
    db.add(g)
    db.flush()
    (uploads / "plaka.step").write_text("ISO-10303-21;", encoding="utf-8")

    m = Material(
        name="TEST-S235",
        category="steel",
        density=7850.0,
        youngs_modulus=210e9,
        poisson_ratio=0.3,
        yield_strength=235e6,
        ultimate_strength=360e6,
    )
    db.add(m)
    db.flush()

    r = AnalysisRun(
        geometry_id=g.id,
        name="-y_500N",
        dimension=3,
        element_size=8.0,
        element_scheme="tet",
        bcs=[{"type": "fixed", "face_ids": [1]}],
        materials_snapshot=[{"part_id": 0, "name": "TEST-S235"}],
        status="solved",
        scalars={"max_von_mises": 330.71, "max_displacement": 23.92},
    )
    db.add(r)
    db.flush()

    run_dir = uploads / "runs" / str(r.id)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "job.frd.gz").write_bytes(b"\x1f\x8b fake-gz")
    (run_dir / "job.train.npz").write_bytes(b"PK\x03\x04")
    r.frd_path = str(run_dir / "job.frd.gz")
    db.commit()
    return r.id


def test_export_writes_manifest_and_rows(db_session, tmp_path):
    uploads = tmp_path / "uploads"
    (uploads / "runs").mkdir(parents=True)
    _seed(db_session, uploads)

    out = tmp_path / "ds.tar.gz"
    manifest = export_dataset(db_session, uploads, out)

    assert out.is_file()
    assert manifest["format_version"] == DATASET_FORMAT_VERSION
    assert manifest["counts"]["analysis_runs"] == 1

    with tarfile.open(out, "r:gz") as tar:
        names = tar.getnames()
    assert "manifest.json" in names
    assert "db/analysis_runs.json" in names


def test_export_includes_frd_field_data(db_session, tmp_path):
    """KRİTİK: surrogate için asıl değerli veri `.frd` alan verisidir;
    yalnız skalerleri almak yetmez."""
    uploads = tmp_path / "uploads"
    (uploads / "runs").mkdir(parents=True)
    _seed(db_session, uploads)

    out = tmp_path / "ds.tar.gz"
    export_dataset(db_session, uploads, out)

    with tarfile.open(out, "r:gz") as tar:
        names = tar.getnames()
        frd = [n for n in names if n.endswith(".frd") or n.endswith(".frd.gz")]
        assert frd, "arşivde .frd/.frd.gz yok"
        npz = [n for n in names if n.endswith(".train.npz")]
        assert npz, "arşivde .train.npz yok"


def test_export_without_files_skips_artifacts(db_session, tmp_path):
    uploads = tmp_path / "uploads"
    (uploads / "runs").mkdir(parents=True)
    _seed(db_session, uploads)

    out = tmp_path / "meta.tar.gz"
    manifest = export_dataset(db_session, uploads, out, include_files=False)
    assert manifest["includes_files"] is False
    with tarfile.open(out, "r:gz") as tar:
        assert not [n for n in tar.getnames() if n.endswith(".frd")]


def test_import_rejects_wrong_format_version(db_session, tmp_path):
    """Uyumsuz sürümü sessizce yanlış eşlemektense reddetmek gerekir."""
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    bad = tmp_path / "bad.tar.gz"
    stage = tmp_path / "stage"
    (stage / "db").mkdir(parents=True)
    (stage / "manifest.json").write_text(
        json.dumps({"format_version": 999}), encoding="utf-8"
    )
    with tarfile.open(bad, "w:gz") as tar:
        for item in stage.iterdir():
            tar.add(item, arcname=item.name)

    with pytest.raises(ValueError, match="biçim sürümü"):
        import_dataset(db_session, uploads, bad)


def test_import_rejects_path_traversal(db_session, tmp_path):
    """Arşiv dışına yazmaya çalışan yol reddedilmeli."""
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    evil = tmp_path / "evil.tar.gz"
    payload = tmp_path / "x.txt"
    payload.write_text("x", encoding="utf-8")
    with tarfile.open(evil, "w:gz") as tar:
        tar.add(payload, arcname="../escaped.txt")

    with pytest.raises(ValueError, match="güvensiz yol"):
        import_dataset(db_session, uploads, evil)


def test_import_restores_template_origin(db_session, tmp_path):
    uploads = tmp_path / "uploads"
    (uploads / "runs").mkdir(parents=True)
    _seed(db_session, uploads)
    out = tmp_path / "ds.tar.gz"
    export_dataset(db_session, uploads, out)

    engine = db_session.get_bind()
    Session = sessionmaker(bind=engine)
    dest = Session()
    try:
        dest.query(AnalysisRun).delete()
        dest.query(Geometry).delete()
        dest.commit()
        import_dataset(dest, uploads, out)
        geo = dest.query(Geometry).one()
        assert geo.template_id == "cantilever_beam"
        assert geo.template_params["length"] == 500.0
    finally:
        dest.close()


# --- korpusa göre arşiv (TODO 2.1) -------------------------------------------
#
# Eskiden temiz eğitim setini indirmenin yolu yoktu: yalnız "çözülmüş run"
# süzgeci vardı, o da elle dışlananları ve korpus süzgecinden düşenleri de
# alıyordu. Artık donmuş setin run'ları ve TANIMI birlikte taşınır.


def _corpus_runs(db, uploads: Path, n: int = 3) -> list[int]:
    ids = []
    for i in range(n):
        g = Geometry(
            original_filename=f"g{i}.step", current_filename=f"g{i}.step",
            template_id="cantilever_beam",
            template_params={"length": 500.0 + i, "thickness": 10.0, "width": 50.0},
        )
        db.add(g)
        db.flush()
        r = AnalysisRun(
            geometry_id=g.id, dimension=3, element_size=8.0, element_scheme="tet",
            bcs=[{"type": "cload", "fy": -500.0}],
            materials_snapshot=[{"youngs_modulus": 210e9, "poisson_ratio": 0.3}],
            status="solved",
            scalars={"max_displacement": 20.0 + i, "max_von_mises": 300.0},
        )
        db.add(r)
        db.flush()
        ids.append(r.id)
    db.commit()
    return ids


def _write_manifest(root: Path, name: str, run_ids: list[int]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / f"corpus_{name}.json").write_text(
        json.dumps({"name": name, "run_ids": run_ids, "template_id": "cantilever_beam"}),
        encoding="utf-8",
    )


def test_korpus_adiyla_yalniz_setin_runlari_alinir(db_session, tmp_path, monkeypatch):
    import app.ml.manifest as manifest_mod

    uploads = tmp_path / "uploads"
    uploads.mkdir()
    _seed(db_session, uploads)  # sete GİRMEYEN bir run
    ids = _corpus_runs(db_session, uploads)
    mdir = tmp_path / "models"
    _write_manifest(mdir, "kiris-v9", ids[:2])
    monkeypatch.setattr(manifest_mod, "MANIFEST_DIR", mdir)

    out = tmp_path / "set.tar.gz"
    man = export_dataset(db_session, uploads, out, include_files=False,
                         corpus_name="kiris-v9")

    assert man["counts"]["analysis_runs"] == 2
    assert man["filters"]["corpus_name"] == "kiris-v9"
    with tarfile.open(out) as tar:
        names = tar.getnames()
        runs = json.loads(tar.extractfile("db/analysis_runs.json").read())
    assert {r["id"] for r in runs} == set(ids[:2])
    assert "corpus/corpus_kiris-v9.json" in names, "setin tanımı da arşivde olmalı"


def test_korpus_ve_run_ids_birlikte_kesisim(db_session, tmp_path, monkeypatch):
    import app.ml.manifest as manifest_mod

    uploads = tmp_path / "uploads"
    uploads.mkdir()
    ids = _corpus_runs(db_session, uploads, n=4)
    mdir = tmp_path / "models"
    _write_manifest(mdir, "kiris-v9", ids[:3])
    monkeypatch.setattr(manifest_mod, "MANIFEST_DIR", mdir)

    out = tmp_path / "kesisim.tar.gz"
    man = export_dataset(db_session, uploads, out, include_files=False,
                         corpus_name="kiris-v9", run_ids=[ids[2], ids[3]])
    assert man["counts"]["analysis_runs"] == 1  # yalnız ikisinde de olan


def test_bilinmeyen_korpus_hata(db_session, tmp_path, monkeypatch):
    import app.ml.manifest as manifest_mod
    from app.ml.manifest import ManifestError

    monkeypatch.setattr(manifest_mod, "MANIFEST_DIR", tmp_path / "models")
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    with pytest.raises(ManifestError):
        export_dataset(db_session, uploads, tmp_path / "x.tar.gz",
                       include_files=False, corpus_name="yok")


def test_ice_aktarmada_set_tanimi_geri_yazilir(db_session, tmp_path, monkeypatch):
    import app.ml.manifest as manifest_mod

    uploads = tmp_path / "uploads"
    uploads.mkdir()
    ids = _corpus_runs(db_session, uploads)
    src_dir = tmp_path / "models_src"
    _write_manifest(src_dir, "kiris-v9", ids)
    monkeypatch.setattr(manifest_mod, "MANIFEST_DIR", src_dir)
    out = tmp_path / "set.tar.gz"
    export_dataset(db_session, uploads, out, include_files=False, corpus_name="kiris-v9")

    # Başka bir ortam: boş manifest klasörü + boş DB
    dst_dir = tmp_path / "models_dst"
    monkeypatch.setattr(manifest_mod, "MANIFEST_DIR", dst_dir)
    engine2 = create_engine(f"sqlite:///{tmp_path / 'other.db'}")
    Base.metadata.create_all(engine2)
    other = sessionmaker(bind=engine2)()
    try:
        res = import_dataset(other, tmp_path / "uploads2", out)
    finally:
        other.close()
        engine2.dispose()

    assert res["restored_corpora"] == ["kiris-v9"]
    assert (dst_dir / "corpus_kiris-v9.json").is_file()


def test_var_olan_set_tanimi_ezilmez(db_session, tmp_path, monkeypatch):
    """Yereldeki set kullanıcının kendi kürasyonunu taşıyor olabilir."""
    import app.ml.manifest as manifest_mod

    uploads = tmp_path / "uploads"
    uploads.mkdir()
    ids = _corpus_runs(db_session, uploads)
    src_dir = tmp_path / "models_src"
    _write_manifest(src_dir, "kiris-v9", ids)
    monkeypatch.setattr(manifest_mod, "MANIFEST_DIR", src_dir)
    out = tmp_path / "set.tar.gz"
    export_dataset(db_session, uploads, out, include_files=False, corpus_name="kiris-v9")

    dst_dir = tmp_path / "models_dst"
    _write_manifest(dst_dir, "kiris-v9", [999])  # yereldeki farklı tanım
    monkeypatch.setattr(manifest_mod, "MANIFEST_DIR", dst_dir)
    engine2 = create_engine(f"sqlite:///{tmp_path / 'other2.db'}")
    Base.metadata.create_all(engine2)
    other = sessionmaker(bind=engine2)()
    try:
        res = import_dataset(other, tmp_path / "uploads3", out)
    finally:
        other.close()
        engine2.dispose()

    assert res["restored_corpora"] == []
    kept = json.loads((dst_dir / "corpus_kiris-v9.json").read_text(encoding="utf-8"))
    assert kept["run_ids"] == [999]
