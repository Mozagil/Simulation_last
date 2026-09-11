"""Veri seti dışa/içe aktarma endpoint'leri.

Surrogate eğitim verisinin Codespace/makine değişimlerinde kaybolmaması
için: `GET /dataset/export` tek bir tar.gz indirir, `POST /dataset/import`
onu başka bir ortamda geri yükler. Ayrıntılı gerekçe için
`app/dataset/archive.py` modül docstring'ine bakın.
"""

from __future__ import annotations

import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.geometry import UPLOAD_DIR
from app.db.session import get_db
from app.dataset.archive import export_dataset, import_dataset

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dataset", tags=["dataset"])


@router.get("/export")
def export_dataset_endpoint(
    include_files: bool = True,
    run_ids: str | None = None,
    geometry_id: int | None = None,
    only_solved: bool = False,
    db: Session = Depends(get_db),
):
    """Analiz geçmişini + çözüm dosyalarını tek arşiv olarak indirir.

    `include_files=false` yalnız metaveri alır — hızlıdır ama surrogate
    eğitimi için yetersizdir, `.frd` alan verisi gitmez.

    Filtreler: `run_ids` (virgülle ayrılmış), `geometry_id`, `only_solved`.
    Hiçbiri verilmezse tüm geçmiş alınır.
    """
    parsed_ids: list[int] | None = None
    if run_ids:
        try:
            parsed_ids = [int(x) for x in run_ids.split(",") if x.strip()]
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail="run_ids virgülle ayrılmış tam sayı olmalı."
            ) from exc

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    suffix = "-secili" if parsed_ids else ("-cozulmus" if only_solved else "")
    out = Path(tempfile.gettempdir()) / f"dataset{suffix}-{stamp}.tar.gz"
    try:
        manifest = export_dataset(
            db,
            UPLOAD_DIR,
            out,
            include_files=include_files,
            run_ids=parsed_ids,
            geometry_id=geometry_id,
            only_solved=only_solved,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Veri seti dışa aktarılamadı")
        raise HTTPException(status_code=500, detail=f"Dışa aktarma başarısız: {exc}") from exc

    logger.info("Veri seti indiriliyor: %s", manifest)
    return FileResponse(
        out,
        media_type="application/gzip",
        filename=out.name,
        headers={"X-Dataset-Counts": str(manifest.get("counts"))},
    )


@router.get("/summary")
def dataset_summary(db: Session = Depends(get_db)) -> dict:
    """Dışa aktarmadan önce ne kadar veri olduğunu gösterir."""
    from app.models.geometry import Geometry
    from app.models.material import Material
    from app.models.run import AnalysisRun

    return {
        "geometries": db.query(Geometry).count(),
        "materials": db.query(Material).count(),
        "analysis_runs": db.query(AnalysisRun).count(),
        "solved_runs": db.query(AnalysisRun).filter(AnalysisRun.status == "solved").count(),
    }


@router.post("/import")
async def import_dataset_endpoint(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict:
    """Arşivi mevcut veritabanına EKLER — hiçbir kaydı silmez/üzerine yazmaz.

    Kimlikler yeniden eşlenir, aynı arşivi iki kez almak kayıtları
    ÇOĞALTIR (silme yapmadığımız için bu bilinçli; tekilleştirme kararı
    kullanıcının).
    """
    if not file.filename or not file.filename.endswith((".tar.gz", ".tgz")):
        raise HTTPException(status_code=400, detail="Beklenen dosya: .tar.gz")

    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = Path(tmp.name)

    try:
        result = import_dataset(db, UPLOAD_DIR, tmp_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Veri seti içe aktarılamadı")
        raise HTTPException(status_code=500, detail=f"İçe aktarma başarısız: {exc}") from exc
    finally:
        tmp_path.unlink(missing_ok=True)

    return result
