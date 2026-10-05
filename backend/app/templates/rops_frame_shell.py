"""Şablon: ROPS portal çerçeve — bükülmüş dikdörtgen tüp, kabuk (Faz 1, K4).

İki dikme + üst kiriş tek parça bükülmüş tüp: dikdörtgen kesit (orta çizgi
d × e, cidar t) yol boyunca süpürülür — dikme (0, 0, 0) → (0, 0, H − R), R
yarıçaplı köşe, kiriş y boyunca, köşe, dikme (0, W, …) → (0, W, 0). Süpürme
yüzleri kenar paylaşır: birleşimde uyumlu mesh (T-birleşimli tüpler dikişli
STEP açılışında ikiz düğüm bırakıyordu — ölçüldü 2026-10-04, 26–32 düğüm).

Crash (K4): tabanlar sabit, "yuk" köşesi (dikme 1 üst bükümü) rijit gövde +
zorlanmış yanal hız +y (yavaş itme); kuvvet iki dikmeyi z = H/2'de kesen
/SECT'ten, deplasman v·t. Referans (veri): sabit tabanlı portal sallanma
mekanizması F = 4·Mp/H, Mp = σy·Zp, Zp ≈ t·(d·e + d²/2) (çerçeve düzleminde
eğilme). ISO 3471 kriterleri mühendisin.

Bölgeler: taban_1 (y = 0, z = 0 halkası), taban_2 (y = W, z = 0), yuk (dikme 1
üst büküm yüzleri). Varsayılan BC'ler yalnız durability akışı için.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from app.templates.base import GeometryTemplate, Region

REGION_BASE_1 = "taban_1"
REGION_BASE_2 = "taban_2"
REGION_LOAD = "yuk"

_TOL = 1e-3


class RopsFrameShellParams(BaseModel):
    """Tüm boyutlar mm."""

    span: float = Field(1000.0, gt=0, description="Dikme eksenleri arası W (y)", json_schema_extra={"unit": "mm", "symbol": "W"})
    height: float = Field(1200.0, gt=0, description="Kiriş eksen yüksekliği H (z)", json_schema_extra={"unit": "mm", "symbol": "H"})
    depth: float = Field(80.0, gt=0, description="Kesit derinliği d (çerçeve düzleminde)", json_schema_extra={"unit": "mm", "symbol": "d"})
    width: float = Field(60.0, gt=0, description="Kesit genişliği e (düzlem dışı, x)", json_schema_extra={"unit": "mm", "symbol": "e"})
    wall: float = Field(4.0, gt=0, description="Cidar kalınlığı t (kabuk kalınlığı)", json_schema_extra={"unit": "mm", "symbol": "t"})
    bend_radius: float = Field(150.0, gt=0, description="Köşe büküm yarıçapı R (eksen)", json_schema_extra={"unit": "mm", "symbol": "R"})

    @model_validator(mode="after")
    def _ok(self) -> "RopsFrameShellParams":
        if self.bend_radius <= self.depth / 2.0:
            raise ValueError("bend_radius, depth / 2'den büyük olmalı (iç yüz kendini kesmesin).")
        if 2.0 * self.bend_radius >= self.span or self.bend_radius >= self.height:
            raise ValueError("bend_radius span / 2 ve height'tan küçük olmalı.")
        if self.depth <= self.wall or self.width <= self.wall:
            raise ValueError("depth ve width, wall'dan büyük olmalı.")
        return self


def plastic_modulus_mm3(p: RopsFrameShellParams) -> float:
    """Çerçeve düzleminde eğilme (derinlik d): Zp ≈ t·(d·e + d²/2) (orta çizgi)."""
    return p.wall * (p.depth * p.width + p.depth * p.depth / 2.0)


def _build(p: RopsFrameShellParams) -> None:
    import gmsh

    occ = gmsh.model.occ
    H, W, R = p.height, p.span, p.bend_radius
    pts = [
        occ.addPoint(0, 0, 0), occ.addPoint(0, 0, H - R), occ.addPoint(0, R, H - R), occ.addPoint(0, R, H),
        occ.addPoint(0, W - R, H), occ.addPoint(0, W - R, H - R), occ.addPoint(0, W, H - R), occ.addPoint(0, W, 0),
    ]
    path = occ.addWire([
        occ.addLine(pts[0], pts[1]),
        occ.addCircleArc(pts[1], pts[2], pts[3]),
        occ.addLine(pts[3], pts[4]),
        occ.addCircleArc(pts[4], pts[5], pts[6]),
        occ.addLine(pts[6], pts[7]),
    ])
    e2, d2 = p.width / 2.0, p.depth / 2.0
    q = [occ.addPoint(x, y, 0) for x, y in ((-e2, -d2), (e2, -d2), (e2, d2), (-e2, d2))]
    profile = [occ.addLine(q[i], q[(i + 1) % 4]) for i in range(4)]
    occ.addPipe([(1, c) for c in profile], path, "DiscreteTrihedron")
    occ.synchronize()
    # Süpürme yolu / profil eğrileri yüzeye ait değil — STEP'e girmesin.
    keep = {c for _d, f in gmsh.model.getEntities(2) for _dd, c in gmsh.model.getBoundary([(2, f)], oriented=False)}
    stray = [(1, c) for _d, c in gmsh.model.getEntities(1) if c not in keep]
    if stray:
        occ.remove(stray, recursive=True)


def _base(y_center: float | None):
    def _select(bbox, p: BaseModel) -> bool:
        x0, y0, z0, x1, y1, z1 = bbox
        if abs(z0) > _TOL or abs(z1) > _TOL:
            return False
        yc = p.span if y_center is None else y_center  # type: ignore[attr-defined]
        return y0 > yc - p.depth and y1 < yc + p.depth  # type: ignore[attr-defined]

    return _select


def _load(bbox, p: BaseModel) -> bool:
    # Dikme 1 büküm yüzleri: z ∈ [H − R, …], y ∈ […, R] (dört yüz, iç yüz dahil).
    _x0, _y0, z0, _x1, y1, _z1 = bbox
    return abs(z0 - (p.height - p.bend_radius)) < 1.0 and abs(y1 - p.bend_radius) < 1.0  # type: ignore[attr-defined]


ROPS_FRAME_SHELL = GeometryTemplate(
    id="rops_frame_shell",
    name="ROPS portal çerçeve — bükülmüş kabuk tüp",
    description=(
        "İki dikme + üst kiriş tek parça bükülmüş dikdörtgen tüp (kabuk). Crash'te tabanlar sabit, "
        "dikme 1 üst bükümü rijit gövde + yanal yavaş itme; kuvvet–deplasman ve enerji. "
        "Referans portal sallanma yükü 4·Mp/H."
    ),
    params_model=RopsFrameShellParams,
    build=_build,
    regions=(
        Region(name=REGION_BASE_1, description="Dikme 1 tabanı (y = 0, z = 0)", select=_base(0.0), dim=1, expected_faces=4),
        Region(name=REGION_BASE_2, description="Dikme 2 tabanı (y = W, z = 0)", select=_base(None), dim=1, expected_faces=4),
        Region(name=REGION_LOAD, description="Dikme 1 üst büküm yüzleri (yük aparatı)", select=_load, dim=2,
               expected_faces=4),
    ),
    analytic=None,
    characteristic_length=lambda p: min(p.depth, p.width),
    default_element_ratio=(0.15, 0.3),
    default_bcs=(
        {"type": "fixed", "region": REGION_BASE_1},
        {"type": "fixed", "region": REGION_BASE_2},
        {"type": "pressure", "region": REGION_LOAD, "magnitude": 0.1},
    ),
    tags=("crash", "kabuk", "rops"),
    surface_only=True,
)
