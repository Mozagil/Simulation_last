"""Roket analitik referansı — Faz 2, R2 (Barrowman CP ve CNα).

POST /cfd/rocket/barrowman  {params | geometry_id, cg_mm?} → bileşen tablosu + toplam

``geometry_id`` verilirse roket şablonundan üretilmiş geometrinin kayıtlı
parametreleri kullanılır. Sonuç veri olarak döner; CFD ile karşılaştırma R3'te.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ValidationError, model_validator
from sqlalchemy.orm import Session

from app.api.geometry import _get_geometry_or_404
from app.db.session import get_db
from app.postprocess.barrowman import barrowman
from app.templates.rocket import RocketParams

router = APIRouter(prefix="/cfd/rocket", tags=["cfd"])


class BarrowmanRequest(BaseModel):
    #: Roket şablonu parametreleri (mm) — ya bu ya geometry_id.
    params: dict[str, Any] | None = None
    geometry_id: int | None = None
    #: Ağırlık merkezi, burun ucundan (mm) — verilirse kararlılık payı (kalibre).
    cg_mm: float | None = Field(None, ge=0)

    @model_validator(mode="after")
    def _one(self) -> "BarrowmanRequest":
        if (self.params is None) == (self.geometry_id is None):
            raise ValueError("'params' ya da 'geometry_id' alanlarından tam biri verilmeli.")
        return self


@router.post("/barrowman")
def rocket_barrowman(body: BarrowmanRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    raw = body.params
    if body.geometry_id is not None:
        geo = _get_geometry_or_404(db, body.geometry_id)
        if geo.template_id != "rocket":
            raise HTTPException(status_code=422, detail="Geometri roket şablonundan üretilmemiş.")
        raw = geo.template_params or {}
    try:
        params = RocketParams.model_validate(raw or {})
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"params": params.model_dump(), **barrowman(params, body.cg_mm)}
