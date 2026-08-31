"""Component + property atama ve ürün ağacı API."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db
from app.models.component import Component
from app.models.geometry import Geometry
from app.models.material import Material, MaterialAssignment

logger = logging.getLogger(__name__)

router = APIRouter(tags=["components"])

_ALLOWED_SOURCES = {"mesh", "cad"}
_ALLOWED_KINDS = {"shell", "solid"}


class UpsertComponentRequest(BaseModel):
    part_id: int = Field(..., ge=0)
    name: str | None = Field(default=None, max_length=120)
    source: str = Field(default="mesh")
    material_id: int | None = Field(default=None, ge=1)
    property_kind: str = Field(default="shell")
    thickness: float | None = Field(default=None, gt=0)


class PatchComponentRequest(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    material_id: int | None = Field(default=None)
    property_kind: str | None = None
    thickness: float | None = Field(default=None, gt=0)


def _component_payload(c: Component) -> dict[str, Any]:
    mat = c.material
    return {
        "id": c.id,
        "geometry_id": c.geometry_id,
        "part_id": c.part_id,
        "name": c.name,
        "source": c.source,
        "material_id": c.material_id,
        "material_name": mat.name if mat else None,
        "material_category": mat.category if mat else None,
        "property_kind": c.property_kind,
        "thickness": c.thickness,
    }


def _sync_material_assignment(
    db: Session, geometry_id: int, part_id: int, material_id: int | None
) -> None:
    """Solve hâlâ MaterialAssignment okuduğu için component malzemesini yansıtır."""
    existing = (
        db.query(MaterialAssignment)
        .filter(
            MaterialAssignment.geometry_id == geometry_id,
            MaterialAssignment.part_id == part_id,
        )
        .one_or_none()
    )
    if material_id is None:
        if existing is not None:
            db.delete(existing)
        return
    if existing is None:
        db.add(
            MaterialAssignment(
                geometry_id=geometry_id,
                part_id=part_id,
                material_id=material_id,
            )
        )
    else:
        existing.material_id = material_id


@router.post("/geometry/{geometry_id}/components")
def upsert_component(
    geometry_id: int,
    body: UpsertComponentRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Seçili parçayı (genelde mesh PART_n) component olarak kaydeder / günceller."""
    geo = db.get(Geometry, geometry_id)
    if geo is None:
        raise HTTPException(status_code=404, detail="Geometri bulunamadı.")

    source = body.source.strip().lower()
    if source not in _ALLOWED_SOURCES:
        raise HTTPException(status_code=400, detail="source mesh veya cad olmalı.")

    kind = body.property_kind.strip().lower()
    if kind not in _ALLOWED_KINDS:
        raise HTTPException(status_code=400, detail="property_kind shell veya solid olmalı.")

    if kind == "shell" and body.thickness is None:
        raise HTTPException(
            status_code=400,
            detail="Shell property için thickness (kalınlık) gerekli.",
        )

    if body.material_id is not None:
        mat = db.get(Material, body.material_id)
        if mat is None:
            raise HTTPException(status_code=404, detail="Malzeme bulunamadı.")

    name = (body.name or "").strip() or f"COMP_PART_{body.part_id}"

    existing = (
        db.query(Component)
        .filter(Component.geometry_id == geometry_id, Component.part_id == body.part_id)
        .one_or_none()
    )
    if existing is None:
        existing = Component(
            geometry_id=geometry_id,
            part_id=body.part_id,
            name=name,
            source=source,
            material_id=body.material_id,
            property_kind=kind,
            thickness=body.thickness if kind == "shell" else None,
        )
        db.add(existing)
    else:
        existing.name = name
        existing.source = source
        existing.material_id = body.material_id
        existing.property_kind = kind
        existing.thickness = body.thickness if kind == "shell" else None

    _sync_material_assignment(db, geometry_id, body.part_id, body.material_id)
    db.commit()
    db.refresh(existing)
    existing = (
        db.query(Component)
        .options(joinedload(Component.material))
        .filter(Component.id == existing.id)
        .one()
    )
    logger.info(
        "Component kaydedildi: geometry_id=%d part_id=%d name=%s kind=%s t=%s mat=%s",
        geometry_id,
        body.part_id,
        existing.name,
        existing.property_kind,
        existing.thickness,
        existing.material_id,
    )
    return {"component": _component_payload(existing)}


@router.patch("/components/{component_id}")
def patch_component(
    component_id: int,
    body: PatchComponentRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Component adı / malzeme / property alanlarını ayrı günceller."""
    existing = (
        db.query(Component)
        .options(joinedload(Component.material))
        .filter(Component.id == component_id)
        .one_or_none()
    )
    if existing is None:
        raise HTTPException(status_code=404, detail="Component bulunamadı.")

    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Component adı boş olamaz.")
        existing.name = name

    if body.property_kind is not None:
        kind = body.property_kind.strip().lower()
        if kind not in _ALLOWED_KINDS:
            raise HTTPException(
                status_code=400, detail="property_kind shell veya solid olmalı."
            )
        existing.property_kind = kind
        if kind == "solid":
            existing.thickness = None

    if body.thickness is not None:
        existing.thickness = body.thickness

    if existing.property_kind == "shell" and existing.thickness is None:
        raise HTTPException(
            status_code=400,
            detail="Shell property için thickness (kalınlık) gerekli.",
        )

    if body.material_id is not None:
        if body.material_id == 0:
            existing.material_id = None
            _sync_material_assignment(db, existing.geometry_id, existing.part_id, None)
        else:
            mat = db.get(Material, body.material_id)
            if mat is None:
                raise HTTPException(status_code=404, detail="Malzeme bulunamadı.")
            existing.material_id = body.material_id
            _sync_material_assignment(
                db, existing.geometry_id, existing.part_id, body.material_id
            )

    db.commit()
    db.refresh(existing)
    existing = (
        db.query(Component)
        .options(joinedload(Component.material))
        .filter(Component.id == existing.id)
        .one()
    )
    return {"component": _component_payload(existing)}


@router.get("/geometry/{geometry_id}/product-tree")
def product_tree(
    geometry_id: int,
    part_count: int = 0,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Ürün ağacı: parçalar + atanmış component / malzeme / property."""
    geo = db.get(Geometry, geometry_id)
    if geo is None:
        raise HTTPException(status_code=404, detail="Geometri bulunamadı.")

    components = (
        db.query(Component)
        .options(joinedload(Component.material))
        .filter(Component.geometry_id == geometry_id)
        .order_by(Component.part_id)
        .all()
    )
    assignments = (
        db.query(MaterialAssignment)
        .options(joinedload(MaterialAssignment.material))
        .filter(MaterialAssignment.geometry_id == geometry_id)
        .all()
    )

    by_part = {c.part_id: c for c in components}
    assign_by_part = {a.part_id: a for a in assignments}

    part_ids = set(range(max(part_count, 0)))
    part_ids.update(by_part.keys())
    part_ids.update(assign_by_part.keys())

    items: list[dict[str, Any]] = []
    for part_id in sorted(part_ids):
        comp = by_part.get(part_id)
        assign = assign_by_part.get(part_id)
        items.append(
            {
                "part_id": part_id,
                "label": f"PART_{part_id}",
                "component": _component_payload(comp) if comp else None,
                "material_name": (
                    (comp.material.name if comp and comp.material else None)
                    or (assign.material.name if assign and assign.material else None)
                ),
                "property_kind": comp.property_kind if comp else None,
                "thickness": comp.thickness if comp else None,
            }
        )

    return {
        "geometry_id": geometry_id,
        "original_filename": geo.original_filename,
        "item_count": len(items),
        "items": items,
    }
