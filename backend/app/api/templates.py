"""Şablon API — listele, parametrelerle üret, STEP indir (0.4.3)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from app.api.geometry import UPLOAD_DIR, _get_geometry_or_404, _tessellation_response_fields
from app.db.session import get_db
from app.mesh.gmsh_adapter import GmshImportError
from app.templates import (
    GeometryTemplate,
    TemplateError,
    UnknownTemplateError,
    list_templates,
)
from app.templates.service import create_geometry_from_template

logger = logging.getLogger(__name__)

router = APIRouter(tags=["templates"])


class CreateFromTemplateRequest(BaseModel):
    params: dict[str, Any] = Field(default_factory=dict)


def _template_payload(t: GeometryTemplate) -> dict[str, Any]:
    return {
        "id": t.id,
        "name": t.name,
        "description": t.description,
        "tags": list(t.tags),
        "params_schema": t.params_schema(),
        "regions": [
            {"name": r.name, "description": r.description, "dim": r.dim}
            for r in t.regions
        ],
        "has_analytic": t.analytic is not None,
    }


@router.get("/templates")
def get_templates() -> dict[str, Any]:
    """Kayıtlı şablonlar + parametre JSON şeması (form/DOE)."""
    items = [_template_payload(t) for t in list_templates()]
    return {"count": len(items), "templates": items}


@router.post("/templates/{template_id}/create")
def create_from_template(
    template_id: str,
    body: CreateFromTemplateRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Şablon parametreleriyle Geometry + isimli bölgeler üretir."""
    try:
        geo, regions, tess = create_geometry_from_template(
            db, template_id, body.params
        )
    except UnknownTemplateError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (TemplateError, GmshImportError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    step_path = UPLOAD_DIR / geo.current_filename
    return {
        "geometry_id": geo.id,
        "original_filename": geo.original_filename,
        "current_filename": geo.current_filename,
        "template_id": geo.template_id,
        "template_params": geo.template_params,
        "regions": regions,
        "size_bytes": str(step_path.stat().st_size) if step_path.exists() else "0",
        "tessellation_path": str(
            Path("uploads") / "tessellations" / f"{geo.id}.stl"
        ),
        **_tessellation_response_fields(geo.id, tess),
    }


@router.get("/geometry/{geometry_id}/step")
def download_geometry_step(geometry_id: int, db: Session = Depends(get_db)) -> FileResponse:
    """Üretilen/yüklenen STEP dosyasını indirir."""
    geo = _get_geometry_or_404(db, geometry_id)
    path = UPLOAD_DIR / geo.current_filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="STEP dosyası diskte yok.")
    name = geo.original_filename or path.name
    if not name.lower().endswith((".step", ".stp")):
        name = f"{path.stem}.step"
    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=name,
    )
