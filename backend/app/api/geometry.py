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
from app.mesh.base import MeshError, MeshParams, TessellationResult
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
MESH_DIR = UPLOAD_DIR / "meshes"


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


def _backup_before_mutation(db: Session, geo: Geometry, file_path: Path) -> None:
    """Bir mutasyon işleminden (copy/heal/midsurface) HEMEN ÖNCE, o anki
    dosyanın bir yedeğini alır — "Geri al" için. Tek seviyeli: yeni bir
    mutasyon önceki yedeği değiştirir (tam bir geçmiş/undo-stack tutulmuyor).

    Eski bir yedek varsa (kullanılmamış), üzerine yazmadan önce diskten
    silinir — yetim dosya birikmesin diye.
    """
    if geo.previous_filename:
        old_backup = UPLOAD_DIR / geo.previous_filename
        old_backup.unlink(missing_ok=True)

    suffix = Path(geo.current_filename).suffix
    backup_name = f"{geo.id}_backup{suffix}"
    backup_path = UPLOAD_DIR / backup_name
    backup_path.write_bytes((UPLOAD_DIR / geo.current_filename).read_bytes())

    geo.previous_filename = backup_name
    db.commit()


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
        "volume_part_ids": result.volume_part_ids,
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
    _backup_before_mutation(db, geo, file_path)

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
    """Tolerans onarımı + silindirik delikleri kapatma (`healShapes` + plug fuse).

    Kalıcı: sonuç `current_filename`'e geri yazılır, tessellation tazelenir.
    """
    geo = _get_geometry_or_404(db, geometry_id)
    file_path = UPLOAD_DIR / geo.current_filename
    _backup_before_mutation(db, geo, file_path)

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
    geometry_id: int, max_radius: float, db: Session = Depends(get_db)
) -> dict[str, Any]:
    """Yarıçapı eşik altındaki fillet yüzeylerini tespit eder (kaldırmadan)."""
    geo = _get_geometry_or_404(db, geometry_id)
    file_path = UPLOAD_DIR / geo.current_filename

    if max_radius <= 0:
        raise HTTPException(status_code=400, detail="max_radius pozitif olmalı.")

    adapter = GmshMesherAdapter()
    try:
        geom = adapter.import_geometry(file_path)
        candidates = adapter.find_defeature_candidates(geom, max_radius)
    except GmshImportError as exc:
        raise HTTPException(status_code=422, detail=f"Geometri okunamadı: {exc}") from exc

    logger.info(
        "Defeature adayları tespit edildi: geometry_id=%d, esik=%.4f, aday_sayisi=%d",
        geometry_id,
        max_radius,
        len(candidates),
    )

    return {
        "geometry_id": geometry_id,
        "max_radius": max_radius,
        "candidate_count": len(candidates),
        "candidates": [
            {
                "face_id": c.face_id,
                "approx_radius": c.approx_radius,
                "surface_type": c.surface_type,
                "part_id": c.part_id,
            }
            for c in candidates
        ],
    }


class ApplyDefeatureRequest(BaseModel):
    face_ids: list[int] = []
    max_radius: float | None = None


@router.post("/{geometry_id}/defeature")
def apply_defeature(
    geometry_id: int, body: ApplyDefeatureRequest, db: Session = Depends(get_db)
) -> dict[str, Any]:
    """Seçilen radyus yüzeylerini kaldırır (veya max_radius ile otomatik).

    Tipik akış: midsurface sonrası radyus mid'leri seç → keskin köşe shell.
    """
    if not body.face_ids and (body.max_radius is None or body.max_radius <= 0):
        raise HTTPException(
            status_code=400,
            detail="face_ids (seçim) veya pozitif max_radius gerekli.",
        )

    geo = _get_geometry_or_404(db, geometry_id)
    file_path = UPLOAD_DIR / geo.current_filename
    _backup_before_mutation(db, geo, file_path)

    adapter = GmshMesherAdapter()
    try:
        geom = adapter.import_geometry(file_path)
        defeature_result = adapter.apply_defeature(
            geom, max_radius=body.max_radius, face_ids=body.face_ids or None
        )
    except GmshImportError as exc:
        raise HTTPException(status_code=422, detail=f"Geometri okunamadı: {exc}") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    result = _regenerate_tessellation(geometry_id, file_path)
    geo.updated_at = datetime.now(timezone.utc)
    db.commit()

    logger.info(
        "Defeature uygulandı: geometry_id=%d, surface_once=%d, surface_sonra=%d",
        geometry_id,
        defeature_result.surfaces_before,
        defeature_result.surfaces_after,
    )

    return {
        "geometry_id": geometry_id,
        "face_ids": body.face_ids,
        "max_radius": body.max_radius,
        "volumes_before": defeature_result.volumes_before,
        "surfaces_before": defeature_result.surfaces_before,
        "volumes_after": defeature_result.volumes_after,
        "surfaces_after": defeature_result.surfaces_after,
        **_tessellation_response_fields(geometry_id, result),
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
    _backup_before_mutation(db, geo, file_path)

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
    """Parçadaki tüm ince-cidar yüzey çiftleri için midsurface üretir.

    Kutu profil gibi ince cidarlı parçalarda her cidar için ayrı orta yüzey
    (örn. 40×40×2 mm → ~38×38 mid-shell, 4 yüzey). Kalıcı: sonuç
    `current_filename`'e geri yazılır.
    """
    geo = _get_geometry_or_404(db, geometry_id)
    file_path = UPLOAD_DIR / geo.current_filename
    _backup_before_mutation(db, geo, file_path)

    adapter = GmshMesherAdapter()
    try:
        geom = adapter.import_geometry(file_path)
        midsurface_results = adapter.create_midsurface_for_part(geom, part_id)
    except GmshImportError as exc:
        raise HTTPException(status_code=422, detail=f"Geometri okunamadı: {exc}") from exc
    except SurfaceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MidsurfaceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    result = _regenerate_tessellation(geometry_id, file_path)
    geo.updated_at = datetime.now(timezone.utc)
    db.commit()

    midsurfaces = [
        {
            "face_id_a": face_a,
            "face_id_b": face_b,
            "new_face_id": new_id,
        }
        for new_id, face_a, face_b in midsurface_results
    ]
    new_face_ids = [item["new_face_id"] for item in midsurfaces]

    logger.info(
        "Midsurface (otomatik) oluşturuldu: geometry_id=%d, part_id=%d, "
        "adet=%d, yeni_idler=%s",
        geometry_id,
        part_id,
        len(midsurfaces),
        new_face_ids,
    )

    return {
        "geometry_id": geometry_id,
        "part_id": part_id,
        "midsurface_count": len(midsurfaces),
        "midsurfaces": midsurfaces,
        "new_face_ids": new_face_ids,
        # Geriye dönük: ilk çift (plaka gibi tek sonuçta UI mesajı için)
        "chosen_face_id_a": midsurfaces[0]["face_id_a"],
        "chosen_face_id_b": midsurfaces[0]["face_id_b"],
        "new_face_id": midsurfaces[0]["new_face_id"],
        **_tessellation_response_fields(geometry_id, result),
    }


@router.post("/{geometry_id}/undo")
def undo_last_mutation(geometry_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Son mutasyon işlemini (copy/heal/midsurface) geri alır — bir önceki
    duruma döner. Tek seviyeli: sadece EN SON mutasyon geri alınabilir, daha
    öncesine gidilemez. Geri alınacak bir işlem yoksa 400 döner.
    """
    geo = _get_geometry_or_404(db, geometry_id)

    if not geo.previous_filename:
        raise HTTPException(
            status_code=400,
            detail="Geri alınacak bir işlem yok (henüz mutasyon yapılmamış ya da zaten geri alındı).",
        )

    backup_path = UPLOAD_DIR / geo.previous_filename
    if not backup_path.exists():
        raise HTTPException(
            status_code=500,
            detail="Yedek dosya bulunamadı — geri alma yapılamıyor.",
        )

    current_path = UPLOAD_DIR / geo.current_filename
    current_path.write_bytes(backup_path.read_bytes())
    backup_path.unlink(missing_ok=True)

    geo.previous_filename = None
    geo.updated_at = datetime.now(timezone.utc)
    db.commit()

    result = _regenerate_tessellation(geometry_id, current_path)

    logger.info("Geri alma uygulandı: geometry_id=%d", geometry_id)

    return {
        "geometry_id": geometry_id,
        **_tessellation_response_fields(geometry_id, result),
    }


class GenerateMeshRequest(BaseModel):
    element_size: float = Field(..., gt=0, description="Global mesh boyutu")
    dimension: int = Field(
        ...,
        description="2 = shell, 3 = solid",
    )
    element_scheme: str = Field(
        default="tet",
        description="tet | quad | mix (2D: tet→tri, quad→quad, mix→tri+quad; 3D: tet/hex)",
    )


@router.post("/{geometry_id}/mesh")
def generate_mesh(
    geometry_id: int, body: GenerateMeshRequest, db: Session = Depends(get_db)
) -> dict[str, Any]:
    """FEA mesh üretir: dimension=2 shell, dimension=3 solid; scheme tet/quad/mix.

    Geometri dosyasını değiştirmez; `uploads/meshes/{id}_d{2|3}.msh` yazar.
    """
    if body.dimension not in (2, 3):
        raise HTTPException(
            status_code=400, detail="dimension 2 (shell) veya 3 (solid) olmalı."
        )
    scheme = body.element_scheme.lower()
    if scheme not in ("tet", "quad", "mix"):
        raise HTTPException(
            status_code=400, detail="element_scheme tet, quad veya mix olmalı."
        )

    geo = _get_geometry_or_404(db, geometry_id)
    file_path = UPLOAD_DIR / geo.current_filename
    MESH_DIR.mkdir(parents=True, exist_ok=True)

    adapter = GmshMesherAdapter()
    try:
        geom = adapter.import_geometry(file_path)
        mesh_result = adapter.generate_mesh(
            geom,
            MeshParams(
                element_size=body.element_size,
                dimension=body.dimension,
                element_scheme=scheme,
            ),
        )
    except GmshImportError as exc:
        raise HTTPException(status_code=422, detail=f"Geometri okunamadı: {exc}") from exc
    except MeshError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    logger.info(
        "Mesh üretildi: geometry_id=%d, dim=%d, scheme=%s, size=%.4f, nodes=%d, elems=%d, path=%s",
        geometry_id,
        mesh_result.dimension,
        scheme,
        body.element_size,
        mesh_result.node_count,
        mesh_result.element_count,
        mesh_result.mesh_path,
    )

    return {
        "geometry_id": geometry_id,
        "element_size": body.element_size,
        "dimension": mesh_result.dimension,
        "element_scheme": mesh_result.element_scheme,
        "node_count": mesh_result.node_count,
        "element_count": mesh_result.element_count,
        "element_type_counts": mesh_result.element_type_counts,
        "mesh_path": str(mesh_result.mesh_path).replace("\\", "/"),
        "mesh_url": f"/files/meshes/{mesh_result.mesh_path.name}",
        "preview_url": (
            f"/files/meshes/{mesh_result.preview_path.name}"
            if mesh_result.preview_path
            else None
        ),
    }


def _mesh_path_for_geometry(geo: Geometry, dimension: int) -> Path:
    """uploads/meshes/{stem}_d{2|3}.msh — stem = geometry id dosya adı kökü."""
    stem = Path(geo.current_filename).stem
    return MESH_DIR / f"{stem}_d{dimension}.msh"


def _quality_metric_payload(metric) -> dict[str, Any]:
    return {
        "name": metric.name,
        "min": metric.min,
        "max": metric.max,
        "mean": metric.mean,
        "values": metric.values,
    }


@router.get("/{geometry_id}/mesh/quality")
def get_mesh_quality(
    geometry_id: int,
    dimension: int = 2,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Kayıtlı FEA mesh için Jacobian (minSJ) + aspect ratio (maxEdge/minEdge)."""
    if dimension not in (2, 3):
        raise HTTPException(status_code=400, detail="dimension 2 veya 3 olmalı.")

    geo = _get_geometry_or_404(db, geometry_id)
    mesh_path = _mesh_path_for_geometry(geo, dimension)
    if not mesh_path.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                f"Önce dimension={dimension} mesh üretin "
                f"(beklenen: {mesh_path.name})."
            ),
        )

    adapter = GmshMesherAdapter()
    try:
        result = adapter.compute_mesh_quality(mesh_path, dimension)
    except MeshError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    logger.info(
        "Mesh kalite: geometry_id=%d dim=%d elems=%d jac[min=%.4g max=%.4g mean=%.4g] "
        "aspect[min=%.4g max=%.4g mean=%.4g]",
        geometry_id,
        dimension,
        result.element_count,
        result.jacobian.min,
        result.jacobian.max,
        result.jacobian.mean,
        result.aspect_ratio.min,
        result.aspect_ratio.max,
        result.aspect_ratio.mean,
    )

    return {
        "geometry_id": geometry_id,
        "dimension": result.dimension,
        "element_count": result.element_count,
        "mesh_path": str(result.mesh_path).replace("\\", "/"),
        "jacobian": _quality_metric_payload(result.jacobian),
        "aspect_ratio": _quality_metric_payload(result.aspect_ratio),
    }
