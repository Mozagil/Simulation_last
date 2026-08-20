"""Geometri (STEP/IGES) dosyası yükleme + web önizleme + düzenleme işlemleri.

MİMARİ (kalıcılık): her yüklenen dosya için PostgreSQL'de kalıcı bir `Geometry`
kaydı oluşturulur — kanonik kimlik artık geçici bir `stored_filename` değil,
veritabanındaki `geometry_id` (int). `Geometry.current_filename`, geometrinin
o anki güncel halini gösterir; `copy_surface` gibi mutasyon işlemleri bu
dosyayı yerinde günceller (overwrite) — böylece bir sonraki istek de
mutasyonu görür (gerçek bir testte doğrulandı: ayrı bir süreçte dosya tekrar
açıldığında değişiklik hâlâ oradaydı).

Physical Group'lar (isimli yüzey grupları) STEP dosyasının bir parçası
olmadığı için (bu Gmsh'e özgü bir modelleme kavramı) ayrı bir `PhysicalGroup`
tablosunda saklanıyor.

Akış:
1. Dosya doğrulanır, `Geometry` DB kaydı oluşturulur, dosya `{geometry_id}{uzantı}`
   olarak diske kaydedilir.
2. Gmsh ile içe aktarılır, STL tessellation + üçgen->yüzey/parça eşlemeleri
   üretilir (uploads/tessellations/{geometry_id}.*).
3. Mutasyon işlemlerinden (yüzey kopyalama) sonra tessellation yeniden üretilir
   - viewer her zaman güncel geometriyi görsün diye.

Gerçek FEA mesh üretimi ayrı bir sonraki adımda (ROADMAP.md "2. Mesh üretimi")
eklenecek.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.mesh.base import TessellationResult
from app.mesh.gmsh_adapter import (
    GmshImportError,
    GmshMesherAdapter,
    MidsurfaceError,
    SurfaceNotFoundError,
)
from app.models.geometry import Geometry, PhysicalGroup

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/geometry", tags=["geometry"])

ALLOWED_EXTENSIONS = {".step", ".stp", ".igs", ".iges"}
UPLOAD_DIR = Path("uploads")
TESSELLATION_DIR = UPLOAD_DIR / "tessellations"


def _ensure_dirs() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    TESSELLATION_DIR.mkdir(parents=True, exist_ok=True)


def _get_geometry_or_404(db: Session, geometry_id: int) -> Geometry:
    geo = db.get(Geometry, geometry_id)
    if geo is None:
        raise HTTPException(
            status_code=404,
            detail=f"Geometri bulunamadı: id={geometry_id}. Önce /geometry/upload ile yükleyin.",
        )
    return geo


def _regenerate_tessellation(geometry_id: int, file_path: Path) -> TessellationResult:
    """Tessellation + üçgen eşlemelerini (yeniden) üretir ve diske yazar.

    Upload sırasında ve her mutasyon (örn. copy_surface) sonrasında çağrılır
    - viewer'ın her zaman geometrinin güncel halini görmesi için.
    """
    adapter = GmshMesherAdapter()
    geom = adapter.import_geometry(file_path)
    result = adapter.preview_tessellation(geom, TESSELLATION_DIR / f"{geometry_id}.stl")

    face_map_path = TESSELLATION_DIR / f"{geometry_id}.faces.json"
    face_map_path.write_text(json.dumps(result.triangle_to_face))
    part_map_path = TESSELLATION_DIR / f"{geometry_id}.parts.json"
    part_map_path.write_text(json.dumps(result.triangle_to_part))

    return result


def _tessellation_response_fields(geometry_id: int, result: TessellationResult) -> dict[str, Any]:
    face_count = len(set(result.triangle_to_face))
    triangle_count = len(result.triangle_to_face)
    return {
        "tessellation_url": f"/files/tessellations/{geometry_id}.stl",
        "triangle_count": triangle_count,
        "face_count": face_count,
        "triangle_to_face": result.triangle_to_face,
        "triangle_to_face_url": f"/files/tessellations/{geometry_id}.faces.json",
        "part_count": result.part_count,
        "triangle_to_part": result.triangle_to_part,
        "triangle_to_part_url": f"/files/tessellations/{geometry_id}.parts.json",
    }


@router.post("/upload")
async def upload_geometry(file: UploadFile, db: Session = Depends(get_db)) -> dict[str, Any]:
    """STEP/IGES dosyasını alır, kalıcı bir Geometry kaydı oluşturur, Gmsh ile
    web önizleme tessellation'ı + üçgen eşlemelerini üretir.
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
    contents = await file.read()

    # Önce DB kaydını oluştur (autoincrement id'yi al), sonra dosyayı bu id ile adlandır.
    db_geometry = Geometry(original_filename=file.filename, current_filename="")
    db.add(db_geometry)
    db.commit()
    db.refresh(db_geometry)

    stored_name = f"{db_geometry.id}{suffix}"
    destination = UPLOAD_DIR / stored_name
    destination.write_bytes(contents)
    db_geometry.current_filename = stored_name
    db.commit()

    try:
        result = _regenerate_tessellation(db_geometry.id, destination)
    except GmshImportError as exc:
        destination.unlink(missing_ok=True)
        db.delete(db_geometry)
        db.commit()
        raise HTTPException(
            status_code=422,
            detail=f"Geometri okunamadı: {exc}",
        ) from exc

    logger.info(
        "Geometri yuklendi: geometry_id=%d, dosya=%s, ucgen_sayisi=%d, yuzey_sayisi=%d, parca_sayisi=%d",
        db_geometry.id,
        file.filename,
        len(result.triangle_to_face),
        len(set(result.triangle_to_face)),
        result.part_count,
    )

    return {
        "geometry_id": db_geometry.id,
        "original_filename": db_geometry.original_filename,
        "current_filename": db_geometry.current_filename,
        "size_bytes": str(len(contents)),
        "tessellation_path": str(TESSELLATION_DIR / f"{db_geometry.id}.stl"),
        **_tessellation_response_fields(db_geometry.id, result),
    }


@router.get("/{geometry_id}/surfaces")
def list_surfaces(geometry_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Kalıcı bir geometrinin tüm yüzeylerini (id, alan, normal, parça) listeler."""
    geo = _get_geometry_or_404(db, geometry_id)
    file_path = UPLOAD_DIR / geo.current_filename

    adapter = GmshMesherAdapter()
    try:
        geom = adapter.import_geometry(file_path)
        surfaces = adapter.list_surfaces(geom)
    except GmshImportError as exc:
        raise HTTPException(status_code=422, detail=f"Geometri okunamadı: {exc}") from exc

    logger.info(
        "Yuzey listesi uretildi: geometry_id=%d, yuzey_sayisi=%d", geometry_id, len(surfaces)
    )

    return {
        "geometry_id": geometry_id,
        "surface_count": len(surfaces),
        "surfaces": [
            {"id": s.id, "area": s.area, "normal": list(s.normal), "part_id": s.part_id}
            for s in surfaces
        ],
    }


@router.get("/{geometry_id}/edges")
def list_edges(geometry_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Kalıcı bir geometrinin tüm kenarlarını (id, uzunluk, parça, uç noktaları) listeler."""
    geo = _get_geometry_or_404(db, geometry_id)
    file_path = UPLOAD_DIR / geo.current_filename

    adapter = GmshMesherAdapter()
    try:
        geom = adapter.import_geometry(file_path)
        edges = adapter.list_edges(geom)
    except GmshImportError as exc:
        raise HTTPException(status_code=422, detail=f"Geometri okunamadı: {exc}") from exc

    logger.info("Kenar listesi uretildi: geometry_id=%d, kenar_sayisi=%d", geometry_id, len(edges))

    return {
        "geometry_id": geometry_id,
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


@router.get("/{geometry_id}/points")
def list_points(geometry_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Kalıcı bir geometrinin tüm köşe noktalarını (id, koordinat, parça) listeler."""
    geo = _get_geometry_or_404(db, geometry_id)
    file_path = UPLOAD_DIR / geo.current_filename

    adapter = GmshMesherAdapter()
    try:
        geom = adapter.import_geometry(file_path)
        points = adapter.list_points(geom)
    except GmshImportError as exc:
        raise HTTPException(status_code=422, detail=f"Geometri okunamadı: {exc}") from exc

    logger.info("Nokta listesi uretildi: geometry_id=%d, nokta_sayisi=%d", geometry_id, len(points))

    return {
        "geometry_id": geometry_id,
        "point_count": len(points),
        "points": [
            {"id": p.id, "coordinate": list(p.coordinate), "part_id": p.part_id} for p in points
        ],
    }


@router.post("/{geometry_id}/surfaces/{face_id}/copy")
def copy_surface(geometry_id: int, face_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Verilen yüzeyi çoğaltır. Kalıcı: sonuç `current_filename`'e geri yazılır
    ve tessellation yeniden üretilir - viewer güncel geometriyi görür.
    """
    geo = _get_geometry_or_404(db, geometry_id)
    file_path = UPLOAD_DIR / geo.current_filename

    adapter = GmshMesherAdapter()
    try:
        geom = adapter.import_geometry(file_path)
        new_face_id = adapter.copy_surface(geom, face_id)
    except GmshImportError as exc:
        raise HTTPException(status_code=422, detail=f"Geometri okunamadı: {exc}") from exc
    except SurfaceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    # Mutasyon sonrası tessellation'ı tazele (yeni yüzey de görünsün).
    result = _regenerate_tessellation(geometry_id, file_path)

    geo.updated_at = datetime.now(timezone.utc)
    db.commit()

    logger.info(
        "Yuzey kopyalandi: geometry_id=%d, orijinal_id=%d, yeni_id=%d",
        geometry_id,
        face_id,
        new_face_id,
    )

    return {
        "geometry_id": geometry_id,
        "original_face_id": face_id,
        "new_face_id": new_face_id,
        **_tessellation_response_fields(geometry_id, result),
    }


class CreatePhysicalGroupRequest(BaseModel):
    name: str = Field(min_length=1)
    face_ids: list[int] = Field(min_length=1)


@router.post("/{geometry_id}/physical-groups")
def create_physical_group(
    geometry_id: int, body: CreatePhysicalGroupRequest, db: Session = Depends(get_db)
) -> dict[str, Any]:
    """Verilen yüzeyleri isimli bir Physical Group'a atar (örn. "inlet").

    Kalıcılık DB'de (STEP dosyası değişmez, sadece bu tabloya bir satır eklenir).
    """
    geo = _get_geometry_or_404(db, geometry_id)
    file_path = UPLOAD_DIR / geo.current_filename

    adapter = GmshMesherAdapter()
    try:
        geom = adapter.import_geometry(file_path)
        adapter.create_physical_group(geom, body.face_ids, body.name)
    except GmshImportError as exc:
        raise HTTPException(status_code=422, detail=f"Geometri okunamadı: {exc}") from exc
    except SurfaceNotFoundError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    db_group = PhysicalGroup(
        geometry_id=geometry_id, name=body.name, dim=2, entity_tags=body.face_ids
    )
    db.add(db_group)
    db.commit()
    db.refresh(db_group)

    logger.info(
        "Physical Group olusturuldu: geometry_id=%d, isim=%s, yuzeyler=%s",
        geometry_id,
        body.name,
        body.face_ids,
    )

    return {
        "id": db_group.id,
        "geometry_id": geometry_id,
        "name": db_group.name,
        "dim": db_group.dim,
        "entity_tags": db_group.entity_tags,
        "face_count": len(db_group.entity_tags),
    }


@router.get("/{geometry_id}/physical-groups")
def list_physical_groups(geometry_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Bir geometriye atanmış tüm Physical Group'ları listeler (DB'den)."""
    _get_geometry_or_404(db, geometry_id)

    groups = (
        db.query(PhysicalGroup)
        .filter(PhysicalGroup.geometry_id == geometry_id)
        .order_by(PhysicalGroup.id)
        .all()
    )

    return {
        "geometry_id": geometry_id,
        "group_count": len(groups),
        "groups": [
            {
                "id": g.id,
                "name": g.name,
                "dim": g.dim,
                "entity_tags": g.entity_tags,
                "face_count": len(g.entity_tags),
            }
            for g in groups
        ],
    }


@router.post("/{geometry_id}/heal")
def heal_geometry(geometry_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Küçük boşluk/tolerans hatalarını düzeltir (`occ.healShapes`).

    Kalıcı: sonuç `current_filename`'e geri yazılır, tessellation tazelenir.
    """
    geo = _get_geometry_or_404(db, geometry_id)
    file_path = UPLOAD_DIR / geo.current_filename

    adapter = GmshMesherAdapter()
    try:
        geom = adapter.import_geometry(file_path)
        heal_result = adapter.heal_geometry(geom)
    except GmshImportError as exc:
        raise HTTPException(status_code=422, detail=f"Geometri okunamadı: {exc}") from exc

    result = _regenerate_tessellation(geometry_id, file_path)
    geo.updated_at = datetime.now(timezone.utc)
    db.commit()

    logger.info(
        "Geometry healing uygulandı: geometry_id=%d, volume_once=%d, volume_sonra=%d, "
        "yuzey_once=%d, yuzey_sonra=%d",
        geometry_id,
        heal_result.volumes_before,
        heal_result.volumes_after,
        heal_result.surfaces_before,
        heal_result.surfaces_after,
    )

    return {
        "geometry_id": geometry_id,
        "volumes_before": heal_result.volumes_before,
        "surfaces_before": heal_result.surfaces_before,
        "volumes_after": heal_result.volumes_after,
        "surfaces_after": heal_result.surfaces_after,
        **_tessellation_response_fields(geometry_id, result),
    }


@router.get("/{geometry_id}/defeature-candidates")
def find_defeature_candidates(
    geometry_id: int, max_diameter: float, db: Session = Depends(get_db)
) -> dict[str, Any]:
    """Verilen eşik altındaki dairesel/döngü kenarları tespit eder.

    Sadece TESPİT — hiçbir şey kaldırılmaz/değiştirilmez (dosyaya geri yazma
    yok). ROADMAP: "o eşiğin altındaki dairesel yüzeyler işaretlenir (henüz
    kaldırmadan)".
    """
    geo = _get_geometry_or_404(db, geometry_id)
    file_path = UPLOAD_DIR / geo.current_filename

    if max_diameter <= 0:
        raise HTTPException(status_code=400, detail="max_diameter pozitif olmalı.")

    adapter = GmshMesherAdapter()
    try:
        geom = adapter.import_geometry(file_path)
        candidates = adapter.find_defeature_candidates(geom, max_diameter)
    except GmshImportError as exc:
        raise HTTPException(status_code=422, detail=f"Geometri okunamadı: {exc}") from exc

    logger.info(
        "Defeature adayları tespit edildi: geometry_id=%d, esik=%.4f, aday_sayisi=%d",
        geometry_id,
        max_diameter,
        len(candidates),
    )

    return {
        "geometry_id": geometry_id,
        "max_diameter": max_diameter,
        "candidate_count": len(candidates),
        "candidates": [
            {"edge_id": c.edge_id, "approx_diameter": c.approx_diameter, "part_id": c.part_id}
            for c in candidates
        ],
    }


class CreateMidsurfaceRequest(BaseModel):
    face_id_a: int
    face_id_b: int


@router.post("/{geometry_id}/midsurface")
def create_midsurface(
    geometry_id: int, body: CreateMidsurfaceRequest, db: Session = Depends(get_db)
) -> dict[str, Any]:
    """İki paralel, düzlemsel yüzey arasında orta yüzeyi hesaplar.

    Kapsam: sadece düzlemsel + paralel yüzey çiftleri (ROADMAP: "sabit
    kalınlıklı düz plaka"). Kalıcı: sonuç `current_filename`'e geri yazılır.
    """
    geo = _get_geometry_or_404(db, geometry_id)
    file_path = UPLOAD_DIR / geo.current_filename

    adapter = GmshMesherAdapter()
    try:
        geom = adapter.import_geometry(file_path)
        new_face_id = adapter.create_midsurface(geom, body.face_id_a, body.face_id_b)
    except GmshImportError as exc:
        raise HTTPException(status_code=422, detail=f"Geometri okunamadı: {exc}") from exc
    except SurfaceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MidsurfaceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    result = _regenerate_tessellation(geometry_id, file_path)
    geo.updated_at = datetime.now(timezone.utc)
    db.commit()

    logger.info(
        "Midsurface oluşturuldu: geometry_id=%d, yuzey_a=%d, yuzey_b=%d, yeni_id=%d",
        geometry_id,
        body.face_id_a,
        body.face_id_b,
        new_face_id,
    )

    return {
        "geometry_id": geometry_id,
        "face_id_a": body.face_id_a,
        "face_id_b": body.face_id_b,
        "new_face_id": new_face_id,
        **_tessellation_response_fields(geometry_id, result),
    }


@router.post("/{geometry_id}/parts/{part_id}/midsurface")
def create_midsurface_for_part(
    geometry_id: int, part_id: int, db: Session = Depends(get_db)
) -> dict[str, Any]:
    """Verilen parçanın en uygun paralel/düzlemsel yüzey çiftini OTOMATİK
    tespit edip midsurface hesaplar — kullanıcının manuel olarak iki yüzey
    seçmesi gerekmez, sadece parçayı seçmesi yeterli.

    Kalıcı: sonuç `current_filename`'e geri yazılır.
    """
    geo = _get_geometry_or_404(db, geometry_id)
    file_path = UPLOAD_DIR / geo.current_filename

    adapter = GmshMesherAdapter()
    try:
        geom = adapter.import_geometry(file_path)
        new_face_id, chosen_face_a, chosen_face_b = adapter.create_midsurface_for_part(
            geom, part_id
        )
    except GmshImportError as exc:
        raise HTTPException(status_code=422, detail=f"Geometri okunamadı: {exc}") from exc
    except SurfaceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MidsurfaceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    result = _regenerate_tessellation(geometry_id, file_path)
    geo.updated_at = datetime.now(timezone.utc)
    db.commit()

    logger.info(
        "Midsurface (otomatik) oluşturuldu: geometry_id=%d, part_id=%d, "
        "secilen_a=%d, secilen_b=%d, yeni_id=%d",
        geometry_id,
        part_id,
        chosen_face_a,
        chosen_face_b,
        new_face_id,
    )

    return {
        "geometry_id": geometry_id,
        "part_id": part_id,
        "chosen_face_id_a": chosen_face_a,
        "chosen_face_id_b": chosen_face_b,
        "new_face_id": new_face_id,
        **_tessellation_response_fields(geometry_id, result),
    }
