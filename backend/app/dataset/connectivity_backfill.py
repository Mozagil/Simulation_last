"""Eski eğitim dosyalarına mesh bağlantısını geriye doldurur (TODO 1.1c).

NEDEN: `connectivity` hiç yazılmadığı için diskteki tüm `.train.npz`
dosyalarında `shape == (0, 0)`. Graf koordinat k-NN'i ile kuruluyordu —
ölçüldü: kenarlarının yalnız %33.6'sı mesh'te gerçekten var. Bağlantı yazımı
düzeltildi ama YALNIZ YENİ koşular için; mevcut eğitim seti düzeltmeden
yararlanamaz.

Çözülmüş run'ların `.inp`'i siliniyor (`discard_solver_input`), ama mesh
dosyası duruyor ve girdi DB anlığından yeniden üretilebiliyor. Bağlantıyı
mesh'ten yeniden ÇIKARMAK yerine üretim yolunu (`rebuild_input_for_run` →
`CalculiXAdapter.build_input`) çağırırız: ikinci bir bağlantı çıkarma kodu
yazmak, iki yol arasında sessiz tutarsızlık riski demek.

GÜVENLİK KİLİDİ: mesh dosyaları geometri+boyuta göre adlandırılır
(`{stem}_d3.msh`), yani aynı geometri BAŞKA bir eleman boyutuyla yeniden
mesh'lendiyse dosya ÜZERİNE YAZILMIŞTIR. O mesh'in bağlantısı eski run'ın
düğümlerine uymaz. Bu yüzden düğüm KOORDİNATLARI birebir karşılaştırılır;
uymazsa dosyaya dokunulmaz. Hizasız bir graf, eksik graftan çok daha
kötüdür: model yanlış düğümün komşusunu öğrenir ve bu hiçbir metrikte
görünmez.

Kullanım:
    python -m app.dataset.connectivity_backfill --dry-run
    python -m app.dataset.connectivity_backfill
"""

from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

import numpy as np
from sqlalchemy.orm import Session

from app.dataset.rebuild import rebuild_input_for_run
from app.models.geometry import Geometry
from app.models.run import AnalysisRun

logger = logging.getLogger(__name__)

#: Koordinat eşleşme toleransı (mm). `.inp` koordinatları %.8g yazılır ve
#: `node_inputs` float32 saklanır; 500 mm'lik bir parçada float32
#: çözünürlüğü ~3e-5 mm. Farklı eleman boyutuyla üretilmiş bir mesh bunun
#: kat kat üstünde sapar.
COORD_TOL_MM = 1e-3

#: Durum kodları — rapor bunlara göre gruplanır.
OK = "dolduruldu"
ALREADY = "zaten_vardi"
NO_MESH = "mesh_dosyasi_yok"
MISMATCH = "mesh_uyusmuyor"
NO_FILE = "egitim_dosyasi_yok"
ERROR = "hata"


@dataclass
class BackfillReport:
    counts: dict[str, int] = field(default_factory=dict)
    files_written: int = 0
    details: list[dict[str, Any]] = field(default_factory=list)

    def add(self, run_id: int, status: str, note: str = "") -> None:
        self.counts[status] = self.counts.get(status, 0) + 1
        self.details.append({"run_id": run_id, "status": status, "note": note})


def training_files(run_dir: Path) -> list[Path]:
    """Bir run klasöründe bağlantı taşıyan dosyalar."""
    return sorted(run_dir.glob("*.train.npz")) + sorted(run_dir.glob("*.inputs.npz"))


def has_connectivity(path: Path) -> bool:
    with np.load(path, allow_pickle=False) as z:
        if "connectivity" not in z.files:
            return False
        return int(np.asarray(z["connectivity"]).size) > 0


def _coords_of(path: Path) -> np.ndarray:
    with np.load(path, allow_pickle=False) as z:
        return np.asarray(z["node_inputs"], dtype=np.float64)[:, :3]


def _write_connectivity(path: Path, conn: np.ndarray, etypes: np.ndarray) -> None:
    """Var olan `.npz`'ye bağlantıyı ekler; diğer diziler korunur."""
    with np.load(path, allow_pickle=False) as z:
        data = {k: z[k] for k in z.files}
    data["connectivity"] = conn
    data["element_types"] = etypes
    tmp = path.with_suffix(".tmp.npz")
    np.savez_compressed(tmp, **data)
    tmp.replace(path)


def mesh_path_for(run: AnalysisRun, geo: Geometry, meshes_root: Path) -> Path:
    """`uploads/meshes/{stem}_d{2|3}.msh` — `_mesh_path_for_geometry` ile aynı."""
    stem = Path(geo.current_filename).stem
    return meshes_root / f"{stem}_d{run.dimension}.msh"


def connectivity_from_mesh(
    run: AnalysisRun, mesh_path: Path, workdir: Path
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(bağlantı, eleman tipleri, düğüm koordinatları) — üretim yolundan."""
    try:
        artifact = rebuild_input_for_run(run, mesh_path, workdir, job_name="backfill")
    except Exception:
        # BC anlığı bozuksa bağlantı yine de çıkarılabilir: mesh bloğu
        # sınır koşullarına bakmaz.
        stripped = AnalysisRun(
            geometry_id=run.geometry_id,
            dimension=run.dimension,
            element_size=run.element_size,
            element_scheme=run.element_scheme,
            shell_thickness=run.shell_thickness,
            bcs=[],
            materials_snapshot=list(run.materials_snapshot or []),
            scalars=dict(run.scalars or {}),
        )
        artifact = rebuild_input_for_run(
            stripped, mesh_path, workdir, job_name="backfill"
        )

    npz = artifact.path.with_suffix(".inputs.npz")
    with np.load(npz, allow_pickle=False) as z:
        conn = np.asarray(z["connectivity"], dtype=np.int32)
        etypes = (
            np.asarray(z["element_types"])
            if "element_types" in z.files
            else np.zeros(0, "<U8")
        )
        coords = np.asarray(z["node_inputs"], dtype=np.float64)[:, :3]
    return conn, etypes, coords


def backfill_run(
    run: AnalysisRun,
    geo: Geometry,
    *,
    runs_root: Path,
    meshes_root: Path,
    dry_run: bool = False,
) -> tuple[str, str, int]:
    """Tek run: (durum, not, yazılan dosya sayısı)."""
    run_dir = runs_root / str(run.id)
    files = training_files(run_dir)
    if not files:
        return NO_FILE, "", 0

    todo = [p for p in files if not has_connectivity(p)]
    if not todo:
        return ALREADY, "", 0

    mesh_path = mesh_path_for(run, geo, meshes_root)
    if not mesh_path.is_file():
        return NO_MESH, mesh_path.name, 0

    written = 0
    with tempfile.TemporaryDirectory(prefix="conn-backfill-") as tmp:
        conn, etypes, coords = connectivity_from_mesh(run, mesh_path, Path(tmp))

        for path in todo:
            target = _coords_of(path)
            if target.shape != coords.shape:
                return (
                    MISMATCH,
                    f"dugum {target.shape[0]} != mesh {coords.shape[0]}",
                    written,
                )
            diff = float(np.abs(target - coords).max()) if target.size else 0.0
            if diff > COORD_TOL_MM:
                return MISMATCH, f"koordinat farki {diff:.4g} mm", written
            if not dry_run:
                _write_connectivity(path, conn, etypes)
            written += 1

    return OK, f"{conn.shape[0]} eleman", written


def backfill_all(
    db: Session,
    *,
    runs_root: Path,
    meshes_root: Path,
    dry_run: bool = False,
    run_ids: Iterable[int] | None = None,
    progress: Callable[[int, int, int, str], None] | None = None,
) -> BackfillReport:
    """Eğitim dosyası olan tüm run'ları gezer."""
    q = db.query(AnalysisRun, Geometry).join(
        Geometry, Geometry.id == AnalysisRun.geometry_id
    )
    if run_ids is not None:
        q = q.filter(AnalysisRun.id.in_(list(run_ids)))
    rows = q.order_by(AnalysisRun.id).all()

    report = BackfillReport()
    total = len(rows)
    for i, (run, geo) in enumerate(rows, start=1):
        try:
            status, note, written = backfill_run(
                run, geo, runs_root=runs_root, meshes_root=meshes_root, dry_run=dry_run
            )
        except Exception as exc:  # noqa: BLE001 — tek run düşerse tarama sürsün
            logger.warning("run %s baglanti doldurma hatasi: %s", run.id, exc)
            status, note, written = ERROR, str(exc)[:120], 0
        if status != NO_FILE:
            report.add(run.id, status, note)
            report.files_written += written
        if progress is not None:
            progress(i, total, run.id, status)
    return report


def _main() -> None:  # pragma: no cover - elle çalıştırma yolu
    import sys

    from app.api.geometry import MESH_DIR, UPLOAD_DIR
    from app.db.session import SessionLocal

    dry = "--dry-run" in sys.argv
    logging.basicConfig(level=logging.ERROR)

    def show(i: int, total: int, run_id: int, status: str) -> None:
        if status not in (NO_FILE, ALREADY):
            print(f"  [{i}/{total}] run {run_id}: {status}", flush=True)

    db = SessionLocal()
    try:
        report = backfill_all(
            db,
            runs_root=UPLOAD_DIR / "runs",
            meshes_root=MESH_DIR,
            dry_run=dry,
            progress=show,
        )
    finally:
        db.close()

    print("\n--- ozet ---")
    for status, n in sorted(report.counts.items(), key=lambda kv: -kv[1]):
        print(f"  {status:<20} {n}")
    print(f"{'yazilabilir' if dry else 'yazilan'} dosya: {report.files_written}")
    for row in report.details:
        if row["status"] in (MISMATCH, ERROR, NO_MESH):
            print(f"  ! run {row['run_id']}: {row['status']} - {row['note']}")


if __name__ == "__main__":  # pragma: no cover
    _main()
