"""Malzeme kütüphanesi + parça atama API (Faz 0 — 2b)."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db
from app.models.geometry import Geometry
from app.models.material import Material, MaterialAssignment

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/materials", tags=["materials"])


def _material_payload(m: Material) -> dict[str, Any]:
    return {
        "id": m.id,
        "name": m.name,
        "category": m.category,
        "standard": m.standard,
        "density": m.density,
        "youngs_modulus": m.youngs_modulus,
        "poisson_ratio": m.poisson_ratio,
        "yield_strength": m.yield_strength,
        "ultimate_strength": m.ultimate_strength,
        "elongation": m.elongation,
        "sn_curve": m.sn_curve,
        "source": m.source,
        "is_editable": m.is_editable,
    }


def _assignment_payload(a: MaterialAssignment) -> dict[str, Any]:
    return {
        "id": a.id,
        "geometry_id": a.geometry_id,
        "part_id": a.part_id,
        "material_id": a.material_id,
        "material_name": a.material.name if a.material else None,
        "material_category": a.material.category if a.material else None,
    }


@router.get("")
def list_materials(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Kütüphane malzemelerini listeler (tipik/nominal değerler)."""
    rows = db.query(Material).order_by(Material.name).all()
    return {
        "count": len(rows),
        "materials": [_material_payload(m) for m in rows],
    }


class AssignMaterialRequest(BaseModel):
    geometry_id: int = Field(..., ge=1)
    part_id: int = Field(..., ge=0, description="Viewer part_id (volume indeksi)")
    material_id: int = Field(..., ge=1)


class CreateMaterialRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    category: str = Field(default="custom")
    density: float = Field(..., gt=0, description="kg/m³")
    youngs_modulus: float = Field(..., gt=0, description="Pa")
    poisson_ratio: float = Field(..., gt=0, lt=0.5)
    yield_strength: float = Field(..., gt=0, description="Pa")
    ultimate_strength: float = Field(..., gt=0, description="Pa")
    elongation: float | None = Field(default=None, ge=0)
    sn_mode: str = Field(
        default="none",
        description="none | estimated | tested",
    )
    sn_curve: dict[str, Any] | None = Field(
        default=None,
        description="sn_mode=tested ise kullanıcı S-N verisi",
    )


class SnCurveRequest(BaseModel):
    source: str = Field(..., description="estimated | tested")
    points: list[dict[str, float]] | None = None


def estimate_sn_from_rm(rm: float) -> dict[str, Any]:
    """Rm'den kaba ampirik S-N (test yerine geçmez)."""
    return {
        "source": "estimated",
        "method": "Rm_correlation",
        "Rm": rm,
        "points": [
            {"N": 1.0e3, "sigma": 0.90 * rm},
            {"N": 1.0e6, "sigma": 0.45 * rm},
            {"N": 1.0e7, "sigma": 0.40 * rm},
        ],
        "note": "Ampirik tahmin; yorulma testinin yerini tutmaz.",
    }


@router.post("")
def create_material(
    body: CreateMaterialRequest, db: Session = Depends(get_db)
) -> dict[str, Any]:
    """Kullanıcı tanımlı malzeme ekler."""
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Malzeme adı boş olamaz.")
    existing = db.query(Material).filter(Material.name == name).one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"Malzeme adı kullanımda: {name}")

    sn_mode = body.sn_mode.lower()
    if sn_mode not in ("none", "estimated", "tested"):
        raise HTTPException(status_code=400, detail="sn_mode none|estimated|tested olmalı.")

    sn_curve: dict[str, Any] | None = None
    if sn_mode == "estimated":
        sn_curve = estimate_sn_from_rm(body.ultimate_strength)
    elif sn_mode == "tested":
        if not body.sn_curve or not body.sn_curve.get("points"):
            raise HTTPException(
                status_code=400,
                detail="sn_mode=tested için sn_curve.points gerekli.",
            )
        sn_curve = {
            "source": "tested",
            "points": body.sn_curve["points"],
            "note": body.sn_curve.get("note", "Kullanıcı test verisi"),
        }

    mat = Material(
        name=name,
        category=body.category.strip() or "custom",
        standard=None,
        density=body.density,
        youngs_modulus=body.youngs_modulus,
        poisson_ratio=body.poisson_ratio,
        yield_strength=body.yield_strength,
        ultimate_strength=body.ultimate_strength,
        elongation=body.elongation,
        sn_curve=sn_curve,
        source="user_defined",
        is_editable=True,
    )
    db.add(mat)
    db.commit()
    db.refresh(mat)
    logger.info("Kullanıcı malzemesi eklendi: id=%d name=%s", mat.id, mat.name)
    return {"material": _material_payload(mat)}


@router.put("/{material_id}/sn-curve")
def set_sn_curve(
    material_id: int, body: SnCurveRequest, db: Session = Depends(get_db)
) -> dict[str, Any]:
    """S-N eğrisi: estimated (Rm'den) veya tested (kullanıcı noktaları)."""
    mat = db.get(Material, material_id)
    if mat is None:
        raise HTTPException(status_code=404, detail="Malzeme bulunamadı.")

    source = body.source.lower()
    if source == "estimated":
        mat.sn_curve = estimate_sn_from_rm(mat.ultimate_strength)
    elif source == "tested":
        if not body.points:
            raise HTTPException(status_code=400, detail="tested için points gerekli.")
        mat.sn_curve = {
            "source": "tested",
            "points": body.points,
            "note": "Kullanıcı test verisi",
        }
    else:
        raise HTTPException(status_code=400, detail="source estimated|tested olmalı.")

    db.commit()
    db.refresh(mat)
    return {"material": _material_payload(mat)}


@router.post("/assignments")
def assign_material(
    body: AssignMaterialRequest, db: Session = Depends(get_db)
) -> dict[str, Any]:
    """Seçili parçaya malzeme atar (aynı parça için günceller)."""
    geo = db.get(Geometry, body.geometry_id)
    if geo is None:
        raise HTTPException(status_code=404, detail="Geometri bulunamadı.")

    mat = db.get(Material, body.material_id)
    if mat is None:
        raise HTTPException(status_code=404, detail="Malzeme bulunamadı.")

    existing = (
        db.query(MaterialAssignment)
        .filter(
            MaterialAssignment.geometry_id == body.geometry_id,
            MaterialAssignment.part_id == body.part_id,
        )
        .one_or_none()
    )
    if existing is None:
        existing = MaterialAssignment(
            geometry_id=body.geometry_id,
            part_id=body.part_id,
            material_id=body.material_id,
        )
        db.add(existing)
    else:
        existing.material_id = body.material_id

    db.commit()
    db.refresh(existing)
    existing = (
        db.query(MaterialAssignment)
        .options(joinedload(MaterialAssignment.material))
        .filter(MaterialAssignment.id == existing.id)
        .one()
    )

    logger.info(
        "Malzeme atandı: geometry_id=%d part_id=%d material_id=%d (%s)",
        body.geometry_id,
        body.part_id,
        body.material_id,
        mat.name,
    )

    return {
        "assignment": _assignment_payload(existing),
    }


@router.get("/assignments")
def list_assignments(
    geometry_id: int, db: Session = Depends(get_db)
) -> dict[str, Any]:
    """Bir geometri için malzeme atamalarını listeler."""
    geo = db.get(Geometry, geometry_id)
    if geo is None:
        raise HTTPException(status_code=404, detail="Geometri bulunamadı.")

    rows = (
        db.query(MaterialAssignment)
        .options(joinedload(MaterialAssignment.material))
        .filter(MaterialAssignment.geometry_id == geometry_id)
        .order_by(MaterialAssignment.part_id)
        .all()
    )
    return {
        "geometry_id": geometry_id,
        "count": len(rows),
        "assignments": [_assignment_payload(a) for a in rows],
    }
