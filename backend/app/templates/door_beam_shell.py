"""Şablon: kapı intrüzyonu — kapı darbe kirişi + rijit silindir impaktör, kabuk (Faz 1, K8).

Parça 0: kapı darbe kirişi, orta yüzey dikdörtgen tüp, ekseni y (boy L), kesit
derinliği h (x, itme yönü) × b (z), cidar t; dış ön yüz x = 0 (K3 kirişiyle
aynı çerçeve). Parça 1: impaktör — ekseni z olan Ø D silindirin kirişe bakan
yarısı (iki çeyrek yay yüzeyi; tam silindirin periyodik yan yüzü dikişli
açılışta meshlenmiyor, 1.18a), yüksekliği b + 2·ek, kirişin ortasında
(y = L/2), yüzeyi ön dış yüzden g geride.

Crash (K8): kiriş uçları ankastre (/BCS), impaktör rijit gövde + zorlanmış
+x hız (yavaş itme), impaktör → kiriş TYPE7. Kuvvet temas kuvvetinden,
intrüzyon v·t. Referans (veri): iki ucu ankastre kirişin plastik çökme yükü
P = 8·Mp/L (taban + orta mafsallar), Mp = σy·Zp, Zp ≈ t·(h'b' + h'²/2).
FMVSS 214 statik ezme mantığı (Ø305 silindir) — kriterler mühendisin.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from app.templates.base import GeometryTemplate, Region, plane_at

REGION_END_1 = "uc_1"
REGION_END_2 = "uc_2"
REGION_IMPACTOR = "impaktor"

_TOL = 1e-3


class DoorBeamShellParams(BaseModel):
    """Tüm boyutlar mm."""

    length: float = Field(800.0, gt=0, description="Kiriş boyu L (y, ankastre uçlar arası)", json_schema_extra={"unit": "mm", "symbol": "L"})
    depth: float = Field(40.0, gt=0, description="Kesit derinliği h (x, itme yönü)", json_schema_extra={"unit": "mm", "symbol": "h"})
    width: float = Field(30.0, gt=0, description="Kesit genişliği b (z)", json_schema_extra={"unit": "mm", "symbol": "b"})
    wall: float = Field(1.5, gt=0, description="Cidar kalınlığı t (kabuk kalınlığı)", json_schema_extra={"unit": "mm", "symbol": "t"})
    impactor_diameter: float = Field(305.0, gt=0, description="İmpaktör silindir çapı D", json_schema_extra={"unit": "mm", "symbol": "D"})
    gap: float = Field(1.0, ge=0, description="Kiriş ön yüzü – impaktör boşluğu g", json_schema_extra={"unit": "mm", "symbol": "g"})

    @model_validator(mode="after")
    def _ok(self) -> "DoorBeamShellParams":
        if self.depth <= 2.0 * self.wall or self.width <= 2.0 * self.wall:
            raise ValueError("depth ve width, 2 × wall değerinden büyük olmalı.")
        if self.length < 4.0 * self.depth:
            raise ValueError("length en az 4 × depth olmalı.")
        if self.impactor_diameter >= self.length:
            raise ValueError("impactor_diameter length'ten küçük olmalı.")
        return self

    @property
    def impactor_centre_x(self) -> float:
        return -self.gap - self.impactor_diameter / 2.0


def plastic_modulus_mm3(p: DoorBeamShellParams) -> float:
    h, b = p.depth - p.wall, p.width - p.wall
    return p.wall * (h * b + h * h / 2.0)


def _build(p: DoorBeamShellParams) -> None:
    import gmsh

    occ = gmsh.model.occ
    h2 = p.wall / 2.0
    # Parça 0 (önce kurulur): kiriş orta yüzeyi
    corners = ((h2, h2), (p.depth - h2, h2), (p.depth - h2, p.width - h2), (h2, p.width - h2))
    pts = [occ.addPoint(x, 0.0, z) for x, z in corners]
    lines = [occ.addLine(pts[i], pts[(i + 1) % 4]) for i in range(4)]
    occ.extrude([(1, ln) for ln in lines], 0.0, p.length, 0.0)
    # Parça 1: kirişe bakan yarım silindir (iki çeyrek yay), z boyunca b + 2·ek
    r = p.impactor_diameter / 2.0
    cx, cy = p.impactor_centre_x, p.length / 2.0
    ext = max(10.0, p.width / 2.0)
    z0 = -ext
    c = occ.addPoint(cx, cy, z0)
    a = occ.addPoint(cx, cy - r, z0)
    m = occ.addPoint(cx + r, cy, z0)
    b = occ.addPoint(cx, cy + r, z0)
    arcs = [occ.addCircleArc(a, c, m), occ.addCircleArc(m, c, b)]
    occ.extrude([(1, arc) for arc in arcs], 0.0, 0.0, p.width + 2.0 * ext)
    occ.remove([(0, c)])


def _impactor(bbox, p: BaseModel) -> bool:
    return bbox[0] < -_TOL  # x < 0: yalnız impaktör (kiriş x ≥ t/2)


DOOR_BEAM_SHELL = GeometryTemplate(
    id="door_beam_shell",
    name="Kapı intrüzyonu — darbe kirişi + silindir impaktör (kabuk)",
    description=(
        "Kapı darbe kirişi (dikdörtgen tüp, uçlar ankastre) ve ortasında Ø D rijit silindir impaktör "
        "(yarım silindir yüzeyi). Crash'te impaktör zorlanmış +x hızla iter; kuvvet–intrüzyon. "
        "Referans 8·Mp/L."
    ),
    params_model=DoorBeamShellParams,
    build=_build,
    regions=(
        Region(name=REGION_END_1, description="y = 0 uç halkası (ankastre)", select=plane_at("y", 0.0), dim=1,
               expected_faces=4),
        Region(name=REGION_END_2, description="y = L uç halkası (ankastre)", select=plane_at("y", lambda p: p.length),
               dim=1, expected_faces=4),
        Region(name=REGION_IMPACTOR, description="İmpaktör silindir yüzleri", select=_impactor, dim=2, expected_faces=2),
    ),
    analytic=None,
    characteristic_length=lambda p: min(p.depth, p.width),
    default_element_ratio=(0.15, 0.3),
    default_bcs=(
        {"type": "fixed", "region": REGION_END_1},
        {"type": "fixed", "region": REGION_END_2},
        {"type": "fixed", "region": REGION_IMPACTOR},
        {"type": "pressure", "region": REGION_IMPACTOR, "magnitude": 0.1},
    ),
    tags=("crash", "kabuk", "kapi"),
    surface_only=True,
)
