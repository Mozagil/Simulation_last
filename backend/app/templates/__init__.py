"""Parametrik geometri şablon kütüphanesi (Faz 0.4).

Kayıt mekanizması: her şablon kendi modülünde bir `GeometryTemplate` örneği
tanımlar ve aşağıdaki `_ALL` listesine eklenir. Yeni şablon = yeni dosya +
bir satır. Şablon id'leri benzersiz olmalı (import anında kontrol edilir).
"""

from __future__ import annotations

from app.templates.base import (
    AnalyticInput,
    BuildResult,
    GeometryTemplate,
    Region,
    TemplateError,
    build_template,
)
from app.templates.cantilever_beam import CANTILEVER_BEAM
from app.templates.dogbone import DOGBONE
from app.templates.plate_with_hole import PLATE_WITH_HOLE
from app.templates.simply_supported_beam import SIMPLY_SUPPORTED_BEAM
from app.templates.thick_walled_tube import THICK_WALLED_TUBE
from app.templates.torsion_shaft import TORSION_SHAFT

_ALL: tuple[GeometryTemplate, ...] = (
    CANTILEVER_BEAM,
    SIMPLY_SUPPORTED_BEAM,
    PLATE_WITH_HOLE,
    DOGBONE,
    THICK_WALLED_TUBE,
    TORSION_SHAFT,
)

TEMPLATES: dict[str, GeometryTemplate] = {}
for _t in _ALL:
    if _t.id in TEMPLATES:
        raise RuntimeError(f"Şablon id'si tekrar ediyor: {_t.id}")
    TEMPLATES[_t.id] = _t


class UnknownTemplateError(KeyError):
    pass


def get_template(template_id: str) -> GeometryTemplate:
    try:
        return TEMPLATES[template_id]
    except KeyError as exc:
        raise UnknownTemplateError(
            f"Bilinmeyen şablon: '{template_id}'. Mevcut: {sorted(TEMPLATES)}"
        ) from exc


def list_templates() -> list[GeometryTemplate]:
    return list(TEMPLATES.values())


__all__ = [
    "AnalyticInput",
    "BuildResult",
    "GeometryTemplate",
    "Region",
    "TemplateError",
    "UnknownTemplateError",
    "build_template",
    "get_template",
    "list_templates",
    "TEMPLATES",
]
