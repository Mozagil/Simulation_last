"""Geometri (STEP/IGES) dosyası yükleme + web önizleme için tessellation.

Akış:
1. Dosya doğrulanır, diske kaydedilir (uploads/).
2. Gmsh ile içe aktarılır (GmshMesherAdapter.import_geometry).
3. Hızlı/düşük çözünürlüklü bir STL tessellation üretilir (uploads/tessellations/),
   web önizleme için — bu FEA mesh'i DEĞİL, sadece görsel önizleme.

Gerçek FEA mesh üretimi (eleman tipi, boyut vb.) ayrı bir sonraki adımda
(ROADMAP.md "2. Mesh üretimi") eklenecek.
"""

import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile

from app.mesh.gmsh_adapter import GmshImportError, GmshMesherAdapter

router = APIRouter(prefix="/geometry", tags=["geometry"])

ALLOWED_EXTENSIONS = {".step", ".stp", ".igs", ".iges"}
UPLOAD_DIR = Path("uploads")
TESSELLATION_DIR = UPLOAD_DIR / "tessellations"


def _ensure_dirs() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    TESSELLATION_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/upload")
async def upload_geometry(file: UploadFile) -> dict[str, str]:
    """STEP/IGES dosyasını alır, diske kaydeder, Gmsh ile web önizleme
    tessellation'ı (STL) üretir.
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

    _ensure_dirs()

    # Çakışmayı önlemek için benzersiz bir dosya adı üret, orijinal adı koru.
    file_id = uuid.uuid4().hex
    stored_name = f"{file_id}{suffix}"
    destination = UPLOAD_DIR / stored_name

    contents = await file.read()
    destination.write_bytes(contents)

    tessellation_path = TESSELLATION_DIR / f"{file_id}.stl"
    adapter = GmshMesherAdapter()
    try:
        geom = adapter.import_geometry(destination)
        adapter.preview_tessellation(geom, tessellation_path)
    except GmshImportError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Geometri okunamadı: {exc}",
        ) from exc

    return {
        "original_filename": file.filename,
        "stored_filename": stored_name,
        "path": str(destination),
        "size_bytes": str(len(contents)),
        "tessellation_path": str(tessellation_path),
    }
