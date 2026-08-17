"""Geometri (STEP/IGES) dosyası yükleme.

Bu adımda dosya SADECE diske kaydedilir — Gmsh ile tessellation/işleme
sonraki bir mikro-adımda eklenecek (bkz. ROADMAP.md, Faz 0 / 1. Geometri
import + önizleme).
"""

import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile

router = APIRouter(prefix="/geometry", tags=["geometry"])

ALLOWED_EXTENSIONS = {".step", ".stp", ".igs", ".iges"}
UPLOAD_DIR = Path("uploads")


def _ensure_upload_dir() -> Path:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return UPLOAD_DIR


@router.post("/upload")
async def upload_geometry(file: UploadFile) -> dict[str, str]:
    """STEP/IGES dosyasını alır, doğrular, diske kaydeder.

    Henüz mesh/tessellation üretmez — sadece "dosya güvenle sunucuda"
    adımını kanıtlar.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Dosya adı boş olamaz.")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Desteklenmeyen dosya uzantısı: '{suffix}'. "
                f"İzin verilenler: {sorted(ALLOWED_EXTENSIONS)}"
            ),
        )

    upload_dir = _ensure_upload_dir()

    # Çakışmayı önlemek için benzersiz bir dosya adı üret, orijinal adı koru.
    stored_name = f"{uuid.uuid4().hex}{suffix}"
    destination = upload_dir / stored_name

    contents = await file.read()
    destination.write_bytes(contents)

    return {
        "original_filename": file.filename,
        "stored_filename": stored_name,
        "path": str(destination),
        "size_bytes": str(len(contents)),
    }
