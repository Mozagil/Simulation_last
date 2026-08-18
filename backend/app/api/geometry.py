"""Geometri (STEP/IGES) dosyası yükleme + web önizleme için tessellation.

Akış:
1. Dosya doğrulanır, diske kaydedilir (uploads/).
2. Gmsh ile içe aktarılır (GmshMesherAdapter.import_geometry).
3. STL tessellation + her üçgenin ait olduğu Gmsh yüzeyini (face) veren
   `triangle_to_face` eşlemesi üretilir (uploads/tessellations/) — web
   önizleme + ileride yüzey picking için temel. Bu FEA mesh'i DEĞİL, sadece
   görsel önizleme.

Gerçek FEA mesh üretimi (eleman tipi, boyut vb.) ayrı bir sonraki adımda
(ROADMAP.md "2. Mesh üretimi") eklenecek.
"""

import json
import logging
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile

from app.mesh.gmsh_adapter import GmshImportError, GmshMesherAdapter, SurfaceNotFoundError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/geometry", tags=["geometry"])

ALLOWED_EXTENSIONS = {".step", ".stp", ".igs", ".iges"}
UPLOAD_DIR = Path("uploads")
TESSELLATION_DIR = UPLOAD_DIR / "tessellations"


def _ensure_dirs() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    TESSELLATION_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/upload")
async def upload_geometry(file: UploadFile) -> dict[str, Any]:
    """STEP/IGES dosyasını alır, diske kaydeder, Gmsh ile web önizleme
    tessellation'ı (STL) + üçgen→yüzey eşlemesi üretir.
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
        result = adapter.preview_tessellation(geom, tessellation_path)
    except GmshImportError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Geometri okunamadı: {exc}",
        ) from exc

    # Üçgen→yüzey ve üçgen→parça eşlemelerini ayrı bir JSON olarak da kaydet
    # (kalıcı, indirilebilir).
    face_map_path = TESSELLATION_DIR / f"{file_id}.faces.json"
    face_map_path.write_text(json.dumps(result.triangle_to_face))
    part_map_path = TESSELLATION_DIR / f"{file_id}.parts.json"
    part_map_path.write_text(json.dumps(result.triangle_to_part))

    face_count = len(set(result.triangle_to_face))
    triangle_count = len(result.triangle_to_face)
    logger.info(
        "Tessellation üretildi: dosya=%s, üçgen_sayısı=%d, yüzey_sayısı=%d, parça_sayısı=%d",
        file.filename,
        triangle_count,
        face_count,
        result.part_count,
    )

    return {
        "original_filename": file.filename,
        "stored_filename": stored_name,
        "path": str(destination),
        "size_bytes": str(len(contents)),
        "tessellation_path": str(tessellation_path),
        "tessellation_url": f"/files/tessellations/{file_id}.stl",
        "triangle_count": triangle_count,
        "face_count": face_count,
        "triangle_to_face": result.triangle_to_face,
        "triangle_to_face_url": f"/files/tessellations/{file_id}.faces.json",
        "part_count": result.part_count,
        "triangle_to_part": result.triangle_to_part,
        "triangle_to_part_url": f"/files/tessellations/{file_id}.parts.json",
    }


@router.get("/{stored_filename}/surfaces")
def list_surfaces(stored_filename: str) -> dict[str, Any]:
    """Daha önce yüklenmiş bir STEP/IGES dosyasının tüm yüzeylerini
    (id, alan, normal, parça) listeler.

    `stored_filename`, `/geometry/upload` yanıtındaki `stored_filename`
    alanıdır (örn. `3f9a...b2.step`).
    """
    file_path = UPLOAD_DIR / stored_filename
    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Dosya bulunamadı: {stored_filename}. Önce /geometry/upload ile yükleyin.",
        )

    adapter = GmshMesherAdapter()
    try:
        geom = adapter.import_geometry(file_path)
        surfaces = adapter.list_surfaces(geom)
    except GmshImportError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Geometri okunamadı: {exc}",
        ) from exc

    logger.info(
        "Yüzey listesi üretildi: dosya=%s, yüzey_sayısı=%d",
        stored_filename,
        len(surfaces),
    )

    return {
        "stored_filename": stored_filename,
        "surface_count": len(surfaces),
        "surfaces": [
            {
                "id": s.id,
                "area": s.area,
                "normal": list(s.normal),
                "part_id": s.part_id,
            }
            for s in surfaces
        ],
    }


@router.get("/{stored_filename}/edges")
def list_edges(stored_filename: str) -> dict[str, Any]:
    """Daha önce yüklenmiş bir STEP/IGES dosyasının tüm kenarlarını
    (id, uzunluk, parça, uç noktaları) listeler.
    """
    file_path = UPLOAD_DIR / stored_filename
    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Dosya bulunamadı: {stored_filename}. Önce /geometry/upload ile yükleyin.",
        )

    adapter = GmshMesherAdapter()
    try:
        geom = adapter.import_geometry(file_path)
        edges = adapter.list_edges(geom)
    except GmshImportError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Geometri okunamadı: {exc}",
        ) from exc

    logger.info(
        "Kenar listesi üretildi: dosya=%s, kenar_sayısı=%d",
        stored_filename,
        len(edges),
    )

    return {
        "stored_filename": stored_filename,
        "edge_count": len(edges),
        "edges": [
            {
                "id": e.id,
                "length": e.length,
                "part_id": e.part_id,
                "start_point": e.start_point,
                "end_point": e.end_point,
            }
            for e in edges
        ],
    }


@router.get("/{stored_filename}/points")
def list_points(stored_filename: str) -> dict[str, Any]:
    """Daha önce yüklenmiş bir STEP/IGES dosyasının tüm köşe noktalarını
    (id, koordinat, parça) listeler.
    """
    file_path = UPLOAD_DIR / stored_filename
    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Dosya bulunamadı: {stored_filename}. Önce /geometry/upload ile yükleyin.",
        )

    adapter = GmshMesherAdapter()
    try:
        geom = adapter.import_geometry(file_path)
        points = adapter.list_points(geom)
    except GmshImportError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Geometri okunamadı: {exc}",
        ) from exc

    logger.info(
        "Nokta listesi üretildi: dosya=%s, nokta_sayısı=%d",
        stored_filename,
        len(points),
    )

    return {
        "stored_filename": stored_filename,
        "point_count": len(points),
        "points": [
            {
                "id": p.id,
                "coordinate": list(p.coordinate),
                "part_id": p.part_id,
            }
            for p in points
        ],
    }


@router.post("/{stored_filename}/surfaces/{face_id}/copy")
def copy_surface(stored_filename: str, face_id: int) -> dict[str, Any]:
    """Verilen yüzeyi (face) ayrı bir Gmsh entity'si olarak çoğaltır.

    NOT (mimari sınır): kopyalama, her istekte yeniden içe aktarılan geçici bir
    Gmsh oturumunda gerçekleşir — diğer list_* endpoint'leriyle aynı desen.
    Yani bu adım `occ.copy`'nin çalıştığını ve yeni bir tag ürettiğini
    kanıtlıyor; kopyalanan geometri şu an diske/veritabanına kalıcı olarak
    yazılmıyor. Birden fazla işlemi (kopyala, isimlendir, sil vb.) aynı
    oturumda biriktirip kalıcı hale getirmek ayrı bir mimari karar —
    ROADMAP'teki sonraki adımlarda (Physical Group, healing, defeature)
    netleştirilecek.
    """
    file_path = UPLOAD_DIR / stored_filename
    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Dosya bulunamadı: {stored_filename}. Önce /geometry/upload ile yükleyin.",
        )

    adapter = GmshMesherAdapter()
    try:
        geom = adapter.import_geometry(file_path)
        new_face_id = adapter.copy_surface(geom, face_id)
    except GmshImportError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Geometri okunamadı: {exc}",
        ) from exc
    except SurfaceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    logger.info(
        "Yüzey kopyalandı: dosya=%s, orijinal_id=%d, yeni_id=%d",
        stored_filename,
        face_id,
        new_face_id,
    )

    return {
        "stored_filename": stored_filename,
        "original_face_id": face_id,
        "new_face_id": new_face_id,
    }
