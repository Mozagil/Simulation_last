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
    bind_region_bcs,
    build_template,
)
from app.templates.cantilever_beam import CANTILEVER_BEAM
from app.templates.circular_tube import CIRCULAR_TUBE
from app.templates.dogbone import DOGBONE
from app.templates.i_beam import I_BEAM
from app.templates.keyway_shaft import KEYWAY_SHAFT
from app.templates.l_angle import L_ANGLE
from app.templates.notched_bar import NOTCHED_BAR
from app.templates.plate_with_hole import PLATE_WITH_HOLE
from app.templates.simply_supported_beam import SIMPLY_SUPPORTED_BEAM
from app.templates.thick_walled_tube import THICK_WALLED_TUBE
from app.templates.torsion_shaft import TORSION_SHAFT
from app.templates.box_tube import BOX_TUBE
from app.templates.t_bracket import T_BRACKET
from app.templates.l_bracket_bolted import L_BRACKET_BOLTED
from app.templates.flange import FLANGE
from app.templates.stepped_shaft import STEPPED_SHAFT
from app.templates.crash_box_plate import CRASH_BOX_PLATE
from app.templates.crash_box_shell import CRASH_BOX_SHELL
from app.templates.plate_ball_shell import PLATE_BALL_SHELL
from app.templates.taylor_bar import TAYLOR_BAR
from app.templates.drop_box_shell import DROP_BOX_SHELL
from app.templates.pole_beam_shell import POLE_BEAM_SHELL
from app.templates.rops_frame_shell import ROPS_FRAME_SHELL
from app.templates.s_rail_shell import S_RAIL_SHELL
from app.templates.door_beam_shell import DOOR_BEAM_SHELL
from app.templates.hopkinson_bar import HOPKINSON_BAR
from app.templates.blast_plate_shell import BLAST_PLATE_SHELL
from app.templates.bucket_rock_shell import BUCKET_ROCK_SHELL

_ALL: tuple[GeometryTemplate, ...] = (
    CANTILEVER_BEAM,
    SIMPLY_SUPPORTED_BEAM,
    PLATE_WITH_HOLE,
    DOGBONE,
    THICK_WALLED_TUBE,
    TORSION_SHAFT,
    I_BEAM,
    BOX_TUBE,
    CIRCULAR_TUBE,
    L_ANGLE,
    NOTCHED_BAR,
    KEYWAY_SHAFT,
    T_BRACKET,
    L_BRACKET_BOLTED,
    FLANGE,
    STEPPED_SHAFT,
    CRASH_BOX_PLATE,
    CRASH_BOX_SHELL,
    PLATE_BALL_SHELL,
    TAYLOR_BAR,
    DROP_BOX_SHELL,
    POLE_BEAM_SHELL,
    ROPS_FRAME_SHELL,
    S_RAIL_SHELL,
    DOOR_BEAM_SHELL,
    HOPKINSON_BAR,
    BLAST_PLATE_SHELL,
    BUCKET_ROCK_SHELL,
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
    "bind_region_bcs",
    "build_template",
    "get_template",
    "list_templates",
    "TEMPLATES",
]
