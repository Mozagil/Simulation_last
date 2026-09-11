"""Şablondan üretilen geometriyi mevcut `Geometry` kaydına bağlar (0.4.1).

Yüklenen STEP ile aynı yolu izler: DB kaydı -> `uploads/{id}.step` ->
tessellation. Fark: dosya kullanıcıdan değil `build_template`'ten gelir ve
şablonun isimli bölgeleri `PhysicalGroup` satırları olarak yazılır — böylece
mevcut BC/mesh/çözüm akışı (face_ids) hiçbir değişiklik olmadan çalışır.

Bu modül `app.api.geometry`'den yardımcı fonksiyon alıyor (tessellation
üretimi, dizinler). Ters yönde bağımlılık yok; 0.4.3'te API katmanı bu
servisi çağıracak.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.api.geometry import UPLOAD_DIR, _ensure_dirs, _regenerate_tessellation
from app.mesh.gmsh_adapter import GmshImportError
from app.models.geometry import Geometry, PhysicalGroup
from app.templates import build_template, get_template

logger = logging.getLogger(__name__)


def create_geometry_from_template(
    db: Session, template_id: str, raw_params: dict[str, Any]
) -> tuple[Geometry, dict[str, list[int]]]:
    """Şablonu kurar, kalıcı Geometry + PhysicalGroup kayıtlarını oluşturur.

    Döner: (geometry, bölge_adı -> yüzey etiketleri).
    Hatalar: `UnknownTemplateError`, `pydantic.ValidationError`,
    `TemplateError`, `GmshImportError` — API katmanı bunları 404/422'ye çevirir.
    Kurulum bir adımda patlarsa yarım kayıt bırakılmaz.
    """
    template = get_template(template_id)
    params = template.parse_params(raw_params)

    _ensure_dirs()
    geo = Geometry(original_filename=f"{template.id}.step", current_filename="")
    db.add(geo)
    db.commit()
    db.refresh(geo)

    stored_name = f"{geo.id}.step"
    step_path = UPLOAD_DIR / stored_name
    try:
        result = build_template(template, params, step_path)
        geo.current_filename = stored_name
        db.commit()
        _regenerate_tessellation(geo.id, step_path)
    except Exception:
        step_path.unlink(missing_ok=True)
        db.delete(geo)
        db.commit()
        raise

    for region in template.regions:
        db.add(
            PhysicalGroup(
                geometry_id=geo.id,
                name=region.name,
                dim=region.dim,
                entity_tags=result.regions[region.name],
            )
        )
    db.commit()

    logger.info(
        "Sablondan geometri uretildi: template=%s geometry_id=%d params=%s bolgeler=%s",
        template.id,
        geo.id,
        params.model_dump(),
        result.regions,
    )
    return geo, result.regions


__all__ = ["create_geometry_from_template", "GmshImportError"]
