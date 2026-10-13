"""Şablon: parametrik roket — burun + gövde tüpü + kanatçıklar (+ boat-tail) (Faz 2, R1).

Kullanıcı 2026-10-08: akademik / savunma sanayii roket yarışmaları için hazır
şablon mantığımızın rokete özel modülü; dış akış (CFD) rüzgâr tünelinde çözülür.

Eksen +x; burun ucu x = 0'da, taban x = L_toplam'da. Akış +x yönünde gelir
(tünel girişi burun tarafında). Profil (x, r) XY düzleminde kurulup x ekseni
etrafında 360° döndürülür; kanatçıklar kökü gövdeye 1 mm gömülü trapez
prizmalardır, eşit açılarla çoğaltılıp gövdeyle birleştirilir (tek solid).

Burun profilleri (R = D/2, Ln = burun boyu, ξ = x/Ln):
- konik:       r = R·ξ
- ogive (teğet): ρ = (R² + Ln²)/(2R),  r = √(ρ² − (Ln − x)²) + R − ρ
- elips:       r = R·√(1 − (1 − ξ)²)
- von Kármán (Haack, C = 0): θ = arccos(1 − 2ξ),  r = R/√π · √(θ − sin 2θ / 2)

Bölgeler (CFD'de her biri ayrı yama → yama başına kuvvet):
``burun``, ``govde``, ``kanatcik``, ``taban``. Boat-tail yüzeyi (varsa) bölge
dışında kalır ve CFD'de ``body`` yamasına düşer; ayrı yama istenirse kullanıcı
Physical Group ekler.
Analitik referans (Barrowman CP / CNα) R2'de eklenecek.
"""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.templates.base import GeometryTemplate, Region

REGION_NOSE = "burun"
REGION_BODY = "govde"
REGION_FINS = "kanatcik"
REGION_BASE = "taban"

NoseShape = Literal["konik", "ogive", "elips", "von_karman"]

_TOL = 1e-3  # mm
_FIN_EMBED = 1.0  # kanatçık kökünün gövdeye gömülme payı (mm) — temiz birleştirme için
_NOSE_SAMPLES = 40


class RocketParams(BaseModel):
    """Tüm boyutlar mm."""

    nose_shape: NoseShape = Field("ogive", description="Burun profili")
    nose_length: float = Field(300.0, gt=0, description="Burun boyu Ln", json_schema_extra={"unit": "mm", "symbol": "Ln"})
    body_diameter: float = Field(100.0, gt=0, description="Gövde çapı D", json_schema_extra={"unit": "mm", "symbol": "D"})
    body_length: float = Field(1200.0, gt=0, description="Gövde tüpü boyu Lb", json_schema_extra={"unit": "mm", "symbol": "Lb"})
    fin_count: int = Field(4, ge=2, le=8, description="Kanatçık sayısı N", json_schema_extra={"symbol": "N"})
    fin_root_chord: float = Field(150.0, gt=0, description="Kök veteri Cr", json_schema_extra={"unit": "mm", "symbol": "Cr"})
    fin_tip_chord: float = Field(60.0, ge=0, description="Uç veteri Ct", json_schema_extra={"unit": "mm", "symbol": "Ct"})
    fin_span: float = Field(100.0, gt=0, description="Kanatçık açıklığı s (gövde yüzeyinden)", json_schema_extra={"unit": "mm", "symbol": "s"})
    fin_sweep: float = Field(80.0, ge=0, description="Hücum kenarı ok mesafesi Xs", json_schema_extra={"unit": "mm", "symbol": "Xs"})
    fin_thickness: float = Field(4.0, gt=0, description="Kanatçık kalınlığı t", json_schema_extra={"unit": "mm", "symbol": "t"})
    fin_offset: float = Field(0.0, ge=0, description="Kanatçık firar kenarının gövde sonuna uzaklığı", json_schema_extra={"unit": "mm", "symbol": "Xf"})
    boattail_length: float = Field(0.0, ge=0, description="Boat-tail boyu Lt (0 = yok)", json_schema_extra={"unit": "mm", "symbol": "Lt"})
    boattail_aft_diameter: float = Field(80.0, gt=0, description="Boat-tail arka çapı Dt", json_schema_extra={"unit": "mm", "symbol": "Dt"})

    @model_validator(mode="after")
    def _ok(self) -> "RocketParams":
        if self.fin_root_chord + self.fin_offset > self.body_length:
            raise ValueError("Kanatçık kökü (Cr + Xf) gövde tüpüne sığmalı.")
        if self.fin_thickness >= self.body_diameter * math.pi / self.fin_count:
            raise ValueError("Kanatçık kalınlığı, kanatçıklar arası çevreden küçük olmalı.")
        if self.boattail_length > 0 and self.boattail_aft_diameter >= self.body_diameter:
            raise ValueError("Boat-tail arka çapı Dt gövde çapı D'den küçük olmalı.")
        return self

    @property
    def radius(self) -> float:
        return self.body_diameter / 2.0

    @property
    def total_length(self) -> float:
        return self.nose_length + self.body_length + self.boattail_length

    @property
    def body_end_x(self) -> float:
        return self.nose_length + self.body_length


def nose_radius(shape: str, x: float, length: float, radius: float) -> float:
    """Burun profili r(x), 0 ≤ x ≤ Ln (uç x = 0)."""
    xi = min(max(x / length, 0.0), 1.0)
    if shape == "konik":
        return radius * xi
    if shape == "ogive":
        rho = (radius**2 + length**2) / (2.0 * radius)
        return math.sqrt(max(rho**2 - (length - x) ** 2, 0.0)) + radius - rho
    if shape == "elips":
        return radius * math.sqrt(max(1.0 - (1.0 - xi) ** 2, 0.0))
    if shape == "von_karman":
        theta = math.acos(1.0 - 2.0 * xi)
        return radius / math.sqrt(math.pi) * math.sqrt(max(theta - math.sin(2.0 * theta) / 2.0, 0.0))
    raise ValueError(f"Bilinmeyen burun profili: {shape}")


def _build(p: RocketParams) -> None:
    import gmsh

    occ = gmsh.model.occ
    R = p.radius
    # Burun eğrisi: uç (0, 0) → omuz (Ln, R). Konikte doğru çizgi.
    tip = occ.addPoint(0.0, 0.0, 0.0)
    if p.nose_shape == "konik":
        shoulder = occ.addPoint(p.nose_length, R, 0.0)
        nose_curve = occ.addLine(tip, shoulder)
    else:
        pts = [tip]
        for i in range(1, _NOSE_SAMPLES):
            # Uca yakın sıklaşan örnekleme (küt profillerde dik başlangıç).
            x = p.nose_length * (1.0 - math.cos(0.5 * math.pi * i / _NOSE_SAMPLES))
            pts.append(occ.addPoint(x, nose_radius(p.nose_shape, x, p.nose_length, R), 0.0))
        # Omuz TAM (Ln, R): kayan noktalı son örnek gövde çizgisinin başına
        # oturmayınca birleşim çemberi iki ayrı kenar oluyordu (ölçüldü:
        # von Kármán + boat-tail'de 42 açık kenar).
        shoulder = occ.addPoint(p.nose_length, R, 0.0)
        pts.append(shoulder)
        nose_curve = occ.addSpline(pts)
    body_end = occ.addPoint(p.body_end_x, R, 0.0)
    curves = [nose_curve, occ.addLine(shoulder, body_end)]
    last = body_end
    if p.boattail_length > 0:
        aft = occ.addPoint(p.total_length, p.boattail_aft_diameter / 2.0, 0.0)
        curves.append(occ.addLine(last, aft))
        last = aft
    base_axis = occ.addPoint(p.total_length, 0.0, 0.0)
    curves.append(occ.addLine(last, base_axis))
    # Profil YÜZEYİNİ 360° döndürmek katının içinde dikiş yüzü bırakıyor
    # (ölçüldü: z = 0'da iç yüz → CFD yüzeyi kapalı olmaz; iki yarım döndürme
    # tabanı ikiye bölüp konik burunda OCC hatası veriyor). Bunun yerine dış
    # kontur eğrileri (eksen çizgisi hariç) döndürülüp kabuktan hacim kurulur.
    shell = [(d, t) for d, t in occ.revolve([(1, c) for c in curves], 0, 0, 0, 1, 0, 0, 2.0 * math.pi) if d == 2]
    occ.synchronize()
    # Her eğri ayrı döndürüldüğü için komşu yüzeylerin birleşim çemberleri ayrı
    # eğriler olarak doğuyor; dikilmezse yüzey açık kalıyordu (ölçüldü: von Kármán
    # + boat-tail'de 42 açık kenar). sewing=True ortak kenarları birleştirir.
    body = [(3, occ.addVolume([occ.addSurfaceLoop([t for _, t in shell], sewing=True)]))]

    # Kanatçık: XY düzleminde trapez (kök x: [x_le, x_le + Cr], r = R − gömme),
    # z yönünde ±t/2 ekstrüde; x ekseni etrafında eşit açılarla çoğaltılır.
    x_te_root = p.body_end_x - p.fin_offset
    x_le_root = x_te_root - p.fin_root_chord
    r0 = R - _FIN_EMBED
    r1 = R + p.fin_span
    x_le_tip = x_le_root + p.fin_sweep
    x_te_tip = x_le_tip + p.fin_tip_chord
    z0 = -p.fin_thickness / 2.0
    corners = [(x_le_root, r0), (x_te_root, r0), (x_te_tip, r1), (x_le_tip, r1)]
    if p.fin_tip_chord == 0:
        corners = [(x_le_root, r0), (x_te_root, r0), (x_le_tip, r1)]
    fin_pts = [occ.addPoint(x, r, z0) for x, r in corners]
    fin_lines = [occ.addLine(fin_pts[i], fin_pts[(i + 1) % len(fin_pts)]) for i in range(len(fin_pts))]
    fin_face = occ.addPlaneSurface([occ.addCurveLoop(fin_lines)])
    fin_vol = [(d, t) for d, t in occ.extrude([(2, fin_face)], 0, 0, p.fin_thickness) if d == 3]
    fins = list(fin_vol)
    for k in range(1, p.fin_count):
        copy = occ.copy(fin_vol)
        occ.rotate(copy, 0, 0, 0, 1, 0, 0, 2.0 * math.pi * k / p.fin_count)
        fins.extend(copy)
    occ.fuse(body, fins)
    # Birleştirme kapalı (periyodik) yüzeyleri ikiye bölüyor; ikinci yarıda
    # burun–gövde çemberi çift eğri kalıyordu. Çift varlıklar birleştirilir.
    occ.removeAllDuplicates()
    occ.synchronize()


def _radial_max(bbox) -> float:
    _x0, y0, z0, _x1, y1, z1 = bbox
    return max(abs(y0), abs(y1), abs(z0), abs(z1))


def _is_fin(bbox, p: BaseModel) -> bool:
    return _radial_max(bbox) > p.radius + 0.5  # type: ignore[attr-defined]


def _is_nose(bbox, p: BaseModel) -> bool:
    return not _is_fin(bbox, p) and bbox[3] <= p.nose_length + _TOL  # type: ignore[attr-defined]


def _is_body(bbox, p: BaseModel) -> bool:
    x0, x1 = bbox[0], bbox[3]
    return (
        not _is_fin(bbox, p)
        and abs(x0 - p.nose_length) < 0.5  # type: ignore[attr-defined]
        and abs(x1 - p.body_end_x) < 0.5  # type: ignore[attr-defined]
    )


def _is_base(bbox, p: BaseModel) -> bool:
    return abs(bbox[0] - p.total_length) < _TOL and abs(bbox[3] - p.total_length) < _TOL  # type: ignore[attr-defined]


ROCKET = GeometryTemplate(
    id="rocket",
    name="Roket — burun + gövde + kanatçık (dış akış)",
    description=(
        "Parametrik roket: burun (konik / ogive / elips / von Kármán), gövde tüpü, N kanatçık "
        "(kök/uç veteri, açıklık, ok, kalınlık), isteğe bağlı boat-tail. Eksen +x, burun ucu x = 0. "
        "CFD rüzgâr tünelinde her bölge ayrı yama (yama başına kuvvet). Barrowman referansı R2'de."
    ),
    params_model=RocketParams,
    build=_build,
    regions=(
        Region(name=REGION_NOSE, description="Burun yüzeyi (0 ≤ x ≤ Ln)", select=_is_nose, dim=2),
        Region(name=REGION_BODY, description="Gövde tüpü (kanatçık delikli silindir)", select=_is_body, dim=2),
        Region(name=REGION_FINS, description="Kanatçık yüzeyleri (tümü)", select=_is_fin, dim=2),
        Region(name=REGION_BASE, description="Taban (x = L_toplam)", select=_is_base, dim=2, expected_faces=1),
    ),
    analytic=None,
    characteristic_length=lambda p: p.body_diameter,
    default_element_ratio=(0.05, 0.1),
    default_bcs=(),
    tags=("cfd", "roket", "dis_akis"),
)
