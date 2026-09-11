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
    g = Geometry(original_filename="plaka.step", current_filename="plaka.step")
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
    (run_dir / "job.inp").write_text("*HEADING\ntest\n", encoding="utf-8")
    # .frd alan verisinin taşındığını doğrulamak için ayırt edici içerik.
    (run_dir / "job.frd").write_text("FRD-FIELD-DATA-MARKER\n", encoding="utf-8")
    r.inp_path = str(run_dir / "job.inp")
    r.frd_path = str(run_dir / "job.frd")
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
        frd = [n for n in tar.getnames() if n.endswith(".frd")]
        assert frd, "arşivde .frd yok"
        content = tar.extractfile(frd[0]).read().decode("utf-8")
    assert "FRD-FIELD-DATA-MARKER" in content


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
