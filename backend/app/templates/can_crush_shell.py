"""Şablon: alüminyum kutu (can) ezme — kabuk, açıyla gelen C-kesit çarpıcı (1.24d).

Problem tanımı (kullanıcı 2026-10-14, Ansys Explicit örneği resmi — dosya kopyalanmadı):
ince cidarlı silindir kutu (alt / üst kapak, bir uçta delik), üstünden açıyla gelen rijit
C-kesit çarpıcı, altta sabit taban. Üç ayrı yüzey grubu, ortak kenar yok → 2D mesh'te
üç parça (`_surface_parts_by_coincident_nodes`):

- parça 0 kutu: eksen z, taban z = 0, üst z = H. Yan yüzey 4 çeyrek yamadan (tek parça
  OCC silindir yüzeyi periyodik — küre şablonundaki "Impossible to mesh periodic surface"
  sorunu olmasın), taban diski, üst kapak ortada Ø d delikli.
- parça 1 çarpıcı: C-kesit (gövde w + iki flanş h_f), uzunluğu L y ekseninde; gövde
  aşağıda, flanşlar yukarı. y ekseni etrafında θ döndürülür; en alt noktası kapak
  üstünden g yukarıda (kutu merkezinin üstünde).
- parça 2 taban: a × a kare, z = −g_b.

Kabuk kalınlıkları çözümde parça kalınlığı (kutu `wall`, çarpıcı / taban ayrı alan).
Bölgeler: kutu_yan, kutu_taban, kutu_kapak, carpici, taban. Analitik yok. Varsayılan
BC'ler yalnız durability akışı için; crash kurulumu `crash_scenario.py` (1.24d).
"""

from __future__ import annotations

import math

from pydantic import BaseModel, Field, model_validator

from app.templates.base import GeometryTemplate, Region

REGION_SIDE = "kutu_yan"
REGION_BOTTOM = "kutu_taban"
REGION_TOP = "kutu_kapak"
REGION_IMPACTOR = "carpici"
REGION_BASE = "taban"

_TOL = 1e-6


class CanCrushShellParams(BaseModel):
    """Tüm boyutlar mm, açı derece."""

    can_diameter: float = Field(66.0, gt=0, description="Kutu çapı D", json_schema_extra={"unit": "mm", "symbol": "D"})
    can_height: float = Field(115.0, gt=0, description="Kutu yüksekliği H", json_schema_extra={"unit": "mm", "symbol": "H"})
    wall: float = Field(0.5, gt=0, description="Kutu cidar kalınlığı t (kabuk)", json_schema_extra={"unit": "mm", "symbol": "t"})
    hole_diameter: float = Field(20.0, ge=0, description="Üst kapak delik çapı d (0 = deliksiz)", json_schema_extra={"unit": "mm", "symbol": "d"})
    impactor_length: float = Field(120.0, gt=0, description="Çarpıcı uzunluğu L (y)", json_schema_extra={"unit": "mm", "symbol": "L"})
    impactor_width: float = Field(40.0, gt=0, description="C gövde genişliği w", json_schema_extra={"unit": "mm", "symbol": "w"})
    impactor_flange: float = Field(20.0, gt=0, description="C flanş yüksekliği h_f", json_schema_extra={"unit": "mm", "symbol": "h_f"})
    impactor_angle_deg: float = Field(15.0, ge=0, lt=80, description="Çarpıcı eğimi θ (y ekseni etrafında)", json_schema_extra={"unit": "°", "symbol": "θ"})
    gap: float = Field(1.0, ge=0, description="Kapak – çarpıcı en alt noktası boşluğu g", json_schema_extra={"unit": "mm", "symbol": "g"})
    base_size: float = Field(150.0, gt=0, description="Taban plakası kenarı a", json_schema_extra={"unit": "mm", "symbol": "a"})
    # 1.0: TYPE24 kabuk temas boşluğu ≈ (t_kutu + t_taban) / 2 = 0.75 mm; 0.5 mm başlangıç penetrasyonu
    # sayılıp yok sayıldı, kutu tabana 2.5 mm girdi (#376) — 1.0 ile 0 penetrasyon (#377).
    base_gap: float = Field(1.0, ge=0, description="Taban – kutu altı boşluğu g_b", json_schema_extra={"unit": "mm", "symbol": "g_b"})

    @model_validator(mode="after")
    def _ok(self) -> "CanCrushShellParams":
        if self.hole_diameter >= self.can_diameter:
            raise ValueError("Delik çapı kutu çapından küçük olmalı.")
        if self.base_size <= self.can_diameter:
            raise ValueError("Taban kenarı kutu çapından büyük olmalı.")
        return self

    def impactor_lift(self) -> float:
        """Döndürülmüş C'nin en alt noktası z = 0'a göre −(w/2)·sinθ; kaldırma miktarı."""
        return self.can_height + self.gap + self.impactor_width / 2.0 * math.sin(math.radians(self.impactor_angle_deg))


def _quarter_arcs(occ, z: float, r: float) -> list[int]:
    """z düzleminde merkez eksende r yarıçaplı çember, 4 çeyrek yay (saat yönü tersine)."""
    c = occ.addPoint(0.0, 0.0, z)
    pts = [occ.addPoint(r * math.cos(k * math.pi / 2), r * math.sin(k * math.pi / 2), z) for k in range(4)]
    arcs = [occ.addCircleArc(pts[k], c, pts[(k + 1) % 4]) for k in range(4)]
    occ.remove([(0, c)])
    return arcs


def _build(p: CanCrushShellParams) -> None:
    """Kutu (parça 0, önce) → çarpıcı (parça 1) → taban (parça 2)."""
    import gmsh

    occ = gmsh.model.occ
    r = p.can_diameter / 2.0
    # Kutu: alt çember 4 yay → z'de çekilir (yan yamalar + üst yaylar)
    bottom = _quarter_arcs(occ, 0.0, r)
    top: list[int] = []
    for a in bottom:
        out = occ.extrude([(1, a)], 0.0, 0.0, p.can_height)
        top.append(next(t for d, t in out if d == 1))
    occ.addPlaneSurface([occ.addCurveLoop(bottom)])
    outer = occ.addCurveLoop(top)
    if p.hole_diameter > 0:
        hole = occ.addCurveLoop(_quarter_arcs(occ, p.can_height, p.hole_diameter / 2.0))
        occ.addPlaneSurface([outer, hole])
    else:
        occ.addPlaneSurface([outer])

    # Çarpıcı: C-kesit x–z'de, y boyunca L; gövde z = 0, flanşlar x = ±w/2
    w, hf, ln = p.impactor_width, p.impactor_flange, p.impactor_length
    y0 = -ln / 2.0
    web = occ.addRectangle(-w / 2.0, y0, 0.0, w, ln)
    flanges = []
    for x in (-w / 2.0, w / 2.0):
        q = [occ.addPoint(x, y0, 0.0), occ.addPoint(x, y0 + ln, 0.0), occ.addPoint(x, y0 + ln, hf), occ.addPoint(x, y0, hf)]
        lines = [occ.addLine(q[i], q[(i + 1) % 4]) for i in range(4)]
        flanges.append(occ.addPlaneSurface([occ.addCurveLoop(lines)]))
    c_dimtags = [(2, web), *[(2, f) for f in flanges]]
    # Gövde ve flanşlar ortak kenarla birleşsin (tek parça)
    c_dimtags, _ = occ.fragment(c_dimtags, [])
    occ.rotate(c_dimtags, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, math.radians(p.impactor_angle_deg))
    occ.translate(c_dimtags, 0.0, 0.0, p.impactor_lift())

    # Taban plakası
    a = p.base_size
    occ.addRectangle(-a / 2.0, -a / 2.0, -p.base_gap, a, a)


def _bbox_z(bbox) -> tuple[float, float]:
    return bbox[2], bbox[5]


def _side(bbox, p: BaseModel) -> bool:
    z0, z1 = _bbox_z(bbox)
    return abs(z0) < _TOL and abs(z1 - p.can_height) < _TOL  # type: ignore[attr-defined]


def _bottom(bbox, p: BaseModel) -> bool:
    z0, z1 = _bbox_z(bbox)
    r = p.can_diameter / 2.0  # type: ignore[attr-defined]
    return abs(z0) < _TOL and abs(z1) < _TOL and bbox[3] - bbox[0] < 2 * r + 1e-3


def _top(bbox, p: BaseModel) -> bool:
    z0, z1 = _bbox_z(bbox)
    h = p.can_height  # type: ignore[attr-defined]
    return abs(z0 - h) < _TOL and abs(z1 - h) < _TOL


def _impactor(bbox, p: BaseModel) -> bool:
    return bbox[5] > p.can_height + _TOL  # type: ignore[attr-defined]


def _base(bbox, p: BaseModel) -> bool:
    z0, z1 = _bbox_z(bbox)
    zb = -p.base_gap  # type: ignore[attr-defined]
    return abs(z0 - zb) < _TOL and abs(z1 - zb) < _TOL and bbox[3] - bbox[0] > p.can_diameter + 1e-3  # type: ignore[attr-defined]


CAN_CRUSH_SHELL = GeometryTemplate(
    id="can_crush_shell",
    name="Kutu (can) ezme — kabuk, açılı C-kesit çarpıcı",
    description=(
        "İnce cidarlı silindir kutu (alt / üst kapak, üstte Ø d delik), üstünde θ eğimli C-kesit "
        "çarpıcı, altında kare taban; üç kabuk parçası (0 kutu, 1 çarpıcı, 2 taban). Crash'te "
        "çarpıcı rijit gövde + −z hız, taban sabit, genel temas. Analitik yok."
    ),
    params_model=CanCrushShellParams,
    build=_build,
    regions=(
        Region(name=REGION_SIDE, description="Kutu yan yüzeyi (4 çeyrek yama)", select=_side, dim=2, expected_faces=4),
        Region(name=REGION_BOTTOM, description="Kutu taban diski (z = 0)", select=_bottom, dim=2, expected_faces=1),
        Region(name=REGION_TOP, description="Kutu üst kapağı (delikli)", select=_top, dim=2, expected_faces=1),
        Region(name=REGION_IMPACTOR, description="C-kesit çarpıcı (gövde + 2 flanş)", select=_impactor, dim=2, expected_faces=3),
        Region(name=REGION_BASE, description="Taban plakası (z = −g_b)", select=_base, dim=2, expected_faces=1),
    ),
    analytic=None,
    characteristic_length=lambda p: p.can_diameter,
    default_element_ratio=(0.04, 0.08),
    # Durability akışı için geçerli bir yük durumu: taban + çarpıcı sabit, kapağa basınç.
    default_bcs=(
        {"type": "fixed", "region": REGION_BASE},
        {"type": "fixed", "region": REGION_IMPACTOR},
        {"type": "fixed", "region": REGION_BOTTOM},
        {"type": "pressure", "region": REGION_TOP, "magnitude": 0.1},
    ),
    tags=("crash", "kabuk", "ezme"),
    surface_only=True,
)
