"""Veri seti dışa/içe aktarma — surrogate eğitim verisinin taşınabilir arşivi.

NEDEN VAR: Analiz geçmişi Codespace'in Postgres volume'ünde, çözüm dosyaları
(`.inp`/`.frd`/önizlemeler) ise `uploads/` altında yaşıyor. `uploads/`
`.gitignore`'da. Codespace silinince İKİSİ DE gidiyor — gerçekten yaşandı,
tüm analiz geçmişi kayboldu.

NEDEN CANLI BİR DIŞ VERİTABANI DEĞİL: Surrogate modelin ihtiyacı değişken bir
geliştirme veritabanı değil, TEKRARLANABİLİR ve SÜRÜMLENMİŞ anlık
görüntülerdir — bir modeli hangi veriyle eğittiğini sonradan kanıtlayabilmek
gerekir. Ayrıca dış bir Postgres yalnız satırları kurtarır; asıl değerli olan
`.frd` alan verisi (her düğümdeki gerilme/deplasman) dosya tarafındadır ve
onu kapsamaz. Bu yüzden arşiv HEM satırları HEM dosyaları taşır.

ARŞİV YAPISI (tar.gz):
    manifest.json          — sürüm, tarih, sayımlar
    db/geometries.json
    db/physical_groups.json
    db/materials.json
    db/material_assignments.json
    db/analysis_runs.json
    files/geometries/...   — STEP/IGES kaynak dosyaları
    files/runs/{run_id}/... — .inp, .frd, sonuç/mesh önizlemeleri

JSON tercih edildi (pg_dump değil): Postgres sürümleri arası taşınabilir,
insan okuyabilir, git'te diff'lenebilir ve surrogate eğitim betiği doğrudan
okuyabilir.
"""

from __future__ import annotations

import json
import logging
import shutil
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models.geometry import Geometry, PhysicalGroup
from app.models.material import Material, MaterialAssignment
from app.models.run import AnalysisRun

logger = logging.getLogger(__name__)

#: Arşiv biçimi sürümü. İçe aktarırken uyumsuz sürümler reddedilir —
#: sessizce yanlış eşlenmiş veri, kayıp veriden daha kötüdür.
DATASET_FORMAT_VERSION = 1

#: Run klasöründeki dosya alanları: (model alanı, arşivdeki alt yol).
_RUN_FILE_FIELDS = (
    "inp_path",
    "frd_path",
    "results_preview_path",
    "mesh_preview_path",
    "tessellation_snapshot_path",
)


def _row_to_dict(obj: Any, columns: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for c in columns:
        v = getattr(obj, c, None)
        if isinstance(v, datetime):
            v = v.isoformat()
        out[c] = v
    return out


_GEOMETRY_COLS = [
    "id",
    "original_filename",
    "current_filename",
    "previous_filename",
    "created_at",
    "updated_at",
]
_PHYSICAL_GROUP_COLS = ["id", "geometry_id", "name", "dim", "entity_tags", "created_at"]
_MATERIAL_COLS = [
    "id",
    "name",
    "category",
    "standard",
    "density",
    "youngs_modulus",
    "poisson_ratio",
    "yield_strength",
    "ultimate_strength",
    "elongation",
    "sn_curve",
    "source",
    "is_editable",
    "created_at",
]
_MATERIAL_ASSIGNMENT_COLS = [
    "id",
    "geometry_id",
    "part_id",
    "material_id",
    "created_at",
    "updated_at",
]
_RUN_COLS = [
    "id",
    "geometry_id",
    "name",
    "created_at",
    "dimension",
    "element_size",
    "element_scheme",
    "shell_thickness",
    "bcs",
    "materials_snapshot",
    "status",
    "message",
    "scalars",
    *_RUN_FILE_FIELDS,
]


def export_dataset(
    db: Session,
    uploads_dir: Path,
    out_path: Path,
    *,
    include_files: bool = True,
) -> dict[str, Any]:
    """Tüm analiz geçmişini ve ilgili dosyaları tek bir tar.gz'e yazar.

    `include_files=False` yalnız satırları alır — hızlı bir metaveri
    yedeği için; surrogate eğitimi için YETERSİZDİR (alan verisi gitmez).
    """
    geometries = db.query(Geometry).order_by(Geometry.id).all()
    groups = db.query(PhysicalGroup).order_by(PhysicalGroup.id).all()
    materials = db.query(Material).order_by(Material.id).all()
    assignments = db.query(MaterialAssignment).order_by(MaterialAssignment.id).all()
    runs = db.query(AnalysisRun).order_by(AnalysisRun.id).all()

    counts = {
        "geometries": len(geometries),
        "physical_groups": len(groups),
        "materials": len(materials),
        "material_assignments": len(assignments),
        "analysis_runs": len(runs),
    }

    with tempfile.TemporaryDirectory() as td:
        stage = Path(td)
        (stage / "db").mkdir()

        def dump(name: str, rows: list[Any], cols: list[str]) -> None:
            (stage / "db" / f"{name}.json").write_text(
                json.dumps([_row_to_dict(r, cols) for r in rows], ensure_ascii=False, indent=1),
                encoding="utf-8",
            )

        dump("geometries", geometries, _GEOMETRY_COLS)
        dump("physical_groups", groups, _PHYSICAL_GROUP_COLS)
        dump("materials", materials, _MATERIAL_COLS)
        dump("material_assignments", assignments, _MATERIAL_ASSIGNMENT_COLS)
        dump("analysis_runs", runs, _RUN_COLS)

        copied_files = 0
        if include_files:
            # --- Geometri kaynak dosyaları ---
            gdst = stage / "files" / "geometries"
            gdst.mkdir(parents=True, exist_ok=True)
            wanted: set[str] = set()
            for g in geometries:
                for fn in (g.current_filename, g.previous_filename, g.original_filename):
                    if fn:
                        wanted.add(fn)
            for fn in wanted:
                src = uploads_dir / fn
                if src.is_file():
                    shutil.copy2(src, gdst / fn)
                    copied_files += 1

            # --- Run çıktıları ---
            runs_src = uploads_dir / "runs"
            for r in runs:
                d = runs_src / str(r.id)
                if d.is_dir():
                    dst = stage / "files" / "runs" / str(r.id)
                    shutil.copytree(d, dst)
                    copied_files += sum(1 for _ in dst.rglob("*") if _.is_file())

        manifest = {
            "format_version": DATASET_FORMAT_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "counts": counts,
            "includes_files": include_files,
            "copied_files": copied_files,
        }
        (stage / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8"
        )

        out_path.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(out_path, "w:gz") as tar:
            for item in sorted(stage.iterdir()):
                tar.add(item, arcname=item.name)

    manifest["bytes"] = out_path.stat().st_size
    logger.info("Veri seti dışa aktarıldı: %s (%s)", out_path, manifest["counts"])
    return manifest


def _parse_dt(v: Any) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(v)
    except (TypeError, ValueError):
        return None


def import_dataset(
    db: Session,
    uploads_dir: Path,
    archive_path: Path,
) -> dict[str, Any]:
    """Arşivi mevcut veritabanına EKLER (hiçbir şeyi silmez).

    KİMLİK YENİDEN EŞLEME: Arşivdeki id'ler hedef veritabanında dolu
    olabilir. Bu yüzden her satır YENİ id ile eklenir ve yabancı anahtarlar
    (geometry_id, material_id) eşleme tablosundan çevrilir. Dosya yolları da
    yeni run id'sine göre yeniden yazılır — eski mutlak yollar başka bir
    makinede anlamsızdır.

    MALZEME TEKİLLEŞTİRME: `materials.name` benzersizdir. Aynı isimli bir
    malzeme zaten varsa YENİSİ EKLENMEZ, mevcut olana eşlenir; aksi halde
    her içe aktarmada kütüphane çoğalırdı.
    """
    with tempfile.TemporaryDirectory() as td:
        stage = Path(td)
        with tarfile.open(archive_path, "r:gz") as tar:
            # Arşiv dışına yazan yolları reddet (tar traversal).
            for m in tar.getmembers():
                p = Path(m.name)
                if p.is_absolute() or ".." in p.parts:
                    raise ValueError(f"Arşivde güvensiz yol: {m.name}")
            # `filter="data"`: Python 3.14'te varsayılan olacak güvenli mod.
            # Açıkça vermek hem DeprecationWarning'i susturur hem de sürüm
            # geçişinde davranışın sessizce değişmemesini garantiler.
            # Yukarıdaki yol kontrolü yine de korunuyor — iki katmanlı savunma.
            try:
                tar.extractall(stage, filter="data")
            except TypeError:
                # Python < 3.12: `filter` parametresi yok.
                tar.extractall(stage)

        manifest = json.loads((stage / "manifest.json").read_text(encoding="utf-8"))
        ver = manifest.get("format_version")
        if ver != DATASET_FORMAT_VERSION:
            raise ValueError(
                f"Arşiv biçim sürümü {ver}, beklenen {DATASET_FORMAT_VERSION}."
            )

        def load(name: str) -> list[dict[str, Any]]:
            p = stage / "db" / f"{name}.json"
            return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else []

        geo_map: dict[int, int] = {}
        mat_map: dict[int, int] = {}
        run_map: dict[int, int] = {}
        added = {k: 0 for k in ("geometries", "materials", "material_assignments", "physical_groups", "analysis_runs")}

        # --- Geometriler + kaynak dosyaları ---
        for row in load("geometries"):
            g = Geometry(
                original_filename=row["original_filename"],
                current_filename=row["current_filename"],
                previous_filename=row.get("previous_filename"),
            )
            db.add(g)
            db.flush()
            geo_map[row["id"]] = g.id
            added["geometries"] += 1
        for f in (stage / "files" / "geometries").glob("*"):
            if f.is_file():
                dst = uploads_dir / f.name
                if not dst.exists():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, dst)

        # --- Malzemeler (isme göre tekilleştirilir) ---
        for row in load("materials"):
            existing = db.query(Material).filter(Material.name == row["name"]).first()
            if existing:
                mat_map[row["id"]] = existing.id
                continue
            m = Material(
                **{
                    k: row.get(k)
                    for k in _MATERIAL_COLS
                    if k not in ("id", "created_at")
                }
            )
            db.add(m)
            db.flush()
            mat_map[row["id"]] = m.id
            added["materials"] += 1

        for row in load("material_assignments"):
            gid = geo_map.get(row["geometry_id"])
            mid = mat_map.get(row["material_id"])
            if gid is None or mid is None:
                continue
            db.add(MaterialAssignment(geometry_id=gid, part_id=row["part_id"], material_id=mid))
            added["material_assignments"] += 1

        for row in load("physical_groups"):
            gid = geo_map.get(row["geometry_id"])
            if gid is None:
                continue
            db.add(
                PhysicalGroup(
                    geometry_id=gid,
                    name=row["name"],
                    dim=row["dim"],
                    entity_tags=row["entity_tags"],
                )
            )
            added["physical_groups"] += 1

        # --- Run'lar ---
        runs_root = uploads_dir / "runs"
        for row in load("analysis_runs"):
            gid = geo_map.get(row["geometry_id"])
            if gid is None:
                # Geometrisi olmayan run yetim kalır; atlanır.
                continue
            r = AnalysisRun(
                geometry_id=gid,
                name=row.get("name"),
                dimension=row["dimension"],
                element_size=row.get("element_size"),
                element_scheme=row.get("element_scheme"),
                shell_thickness=row.get("shell_thickness"),
                bcs=row.get("bcs") or [],
                materials_snapshot=row.get("materials_snapshot") or [],
                status=row.get("status") or "solved",
                message=row.get("message"),
                scalars=row.get("scalars") or {},
            )
            created = _parse_dt(row.get("created_at"))
            if created:
                r.created_at = created
            db.add(r)
            db.flush()
            run_map[row["id"]] = r.id
            added["analysis_runs"] += 1

            # Dosyaları YENİ run id'sinin klasörüne kopyala ve yolları
            # buna göre yeniden yaz — arşivdeki mutlak yollar başka bir
            # makinede geçersizdir.
            src_dir = stage / "files" / "runs" / str(row["id"])
            if src_dir.is_dir():
                dst_dir = runs_root / str(r.id)
                dst_dir.mkdir(parents=True, exist_ok=True)
                for f in src_dir.rglob("*"):
                    if f.is_file():
                        rel = f.relative_to(src_dir)
                        target = dst_dir / rel
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(f, target)
                for field in _RUN_FILE_FIELDS:
                    old = row.get(field)
                    if not old:
                        continue
                    setattr(r, field, str(dst_dir / Path(old).name))

        db.commit()

    result = {
        "format_version": manifest.get("format_version"),
        "source_created_at": manifest.get("created_at"),
        "added": added,
    }
    logger.info("Veri seti içe aktarıldı: %s", result)
    return result
