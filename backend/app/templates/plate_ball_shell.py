"""Şablon: plaka–küre (kabuk) — delinme / darbe örneği (Faz 1, 1.18a).

İki ayrı yüzey grubu, ortak kenar yok → 2D mesh'te iki parça
(`_surface_parts_by_coincident_nodes`): parça 0 kare plaka, parça 1 küre.

- Plaka: a × a kare, ORTA yüzeyi z = 0 düzleminde, merkez orijinde. Kalınlık
  t geometride yalnız kürenin konumunu belirler; kabuk kalınlığı crash
  çözümünde parça kalınlığı olarak ayrıca girilir (1.13b deseni).
- Küre: çap D, yüzeyi (hacim yok; 6 yamalı küp-küre, bkz. `_build`); merkez (0, 0, t/2 + g + D/2). g plakanın
  üst yüzeyi ile kürenin alt noktası arasındaki boşluk. Küre kabuğunun kendi
  kalınlığı ve temas boşluğu (TYPE7 gap) çözüm kartlarındadır — g'yi
  mühendis buna göre seçer.

Bölgeler: plaka_kenar (4 kenar, dim 1), plaka (yüzey), kure (yüzey).
Analitik yok. Varsayılan BC'ler yalnız durability akışı için (kenar + küre sabit,
plakaya 0.1 MPa basınç); crash kurulumu 1.18b senaryosunda.
"""

from __future__ import annotations

import math

from pydantic import BaseModel, Field

from app.templates.base import GeometryTemplate, Region

REGION_PLATE_EDGE = "plaka_kenar"
REGION_PLATE = "plaka"
REGION_BALL = "kure"

_TOL = 1e-6
#: Küre yaması başına iç nokta ızgarası (n−1)²; 8 → yarıçap sapması < %0.2.
_FILL_N = 8


class PlateBallShellParams(BaseModel):
    """Tüm boyutlar mm."""

    plate_size: float = Field(300.0, gt=0, description="Kare plaka kenarı a (x, y)", json_schema_extra={"unit": "mm", "symbol": "a"})
    plate_thickness: float = Field(5.0, gt=0, description="Plaka kalınlığı t (küre konumu; kabuk kalınlığı)", json_schema_extra={"unit": "mm", "symbol": "t"})
    ball_diameter: float = Field(50.0, gt=0, description="Küre çapı D", json_schema_extra={"unit": "mm", "symbol": "D"})
    gap: float = Field(1.0, ge=0, description="Plaka üst yüzeyi – küre alt noktası boşluğu g", json_schema_extra={"unit": "mm", "symbol": "g"})

    @property
    def ball_center_z(self) -> float:
        return self.plate_thickness / 2.0 + self.gap + self.ball_diameter / 2.0


def add_cube_sphere(centre_xyz: tuple[float, float, float], radius: float) -> None:
    """Gmsh OCC'ye 6 yamalı küp-küre yüzeyi ekler (K11'de taş için de kullanılır).

    Tek parça OCC küresi (periyodik yüzey, kutup) mesh katmanının dikişli
    açılışında meshlenemiyor ("Impossible to mesh periodic surface"; dilimli
    küre de kutuptaki dejenere kenar yüzünden kapalı döngü kuramıyor — ölçüldü
    2026-10-04). Bu yüzden küre küpün yüzlerinin küreye izdüşümü olan 6 yamadan
    kurulur: kenarlar gerçek büyük çember yayları, iç yüzey küre üzerindeki
    eş-açılı `_FILL_N`² noktaya oturtulan dolgu yüzeyi. Sapma test edilir.
    """
    import gmsh

    occ = gmsh.model.occ
    cx, cy, cz = centre_xyz

    def sphere_point(t) -> tuple[float, float, float]:
        n = math.sqrt(t[0] ** 2 + t[1] ** 2 + t[2] ** 2)
        return (cx + radius * t[0] / n, cy + radius * t[1] / n, cz + radius * t[2] / n)

    centre = occ.addPoint(cx, cy, cz)
    corner_pts: dict[tuple[int, int, int], int] = {}
    arcs: dict[tuple, int] = {}

    def corner(key: tuple[int, int, int]) -> int:
        if key not in corner_pts:
            corner_pts[key] = occ.addPoint(*sphere_point(key))
        return corner_pts[key]

    for axis in range(3):
        u_ax, v_ax = (i for i in range(3) if i != axis)
        for sign in (-1, 1):
            corners = []
            for u, v in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                t = [0, 0, 0]
                t[axis], t[u_ax], t[v_ax] = sign, u, v
                corners.append(tuple(t))
            loop = []
            for i in range(4):
                a, b = corners[i], corners[(i + 1) % 4]
                key = tuple(sorted((a, b)))
                if key not in arcs:
                    arcs[key] = occ.addCircleArc(corner(key[0]), centre, corner(key[1]))
                loop.append(arcs[key] if key[0] == a else -arcs[key])
            inner = []
            for i in range(1, _FILL_N):
                for j in range(1, _FILL_N):
                    t = [0.0, 0.0, 0.0]
                    t[axis] = float(sign)
                    t[u_ax] = math.tan((-1.0 + 2.0 * i / _FILL_N) * math.pi / 4.0)
                    t[v_ax] = math.tan((-1.0 + 2.0 * j / _FILL_N) * math.pi / 4.0)
                    inner.append(occ.addPoint(*sphere_point(t)))
            occ.addSurfaceFilling(occ.addWire(loop), pointTags=inner)
    occ.remove([(0, centre)])


def _build(p: PlateBallShellParams) -> None:
    """Plaka (parça 0, önce kurulur → STEP'te ilk yüzey) + küp-küre (parça 1)."""
    import gmsh

    h = p.plate_size / 2.0
    gmsh.model.occ.addRectangle(-h, -h, 0.0, p.plate_size, p.plate_size)
    add_cube_sphere((0.0, 0.0, p.ball_center_z), p.ball_diameter / 2.0)


def _plate_edge(bbox, p: BaseModel) -> bool:
    x0, y0, z0, x1, y1, z1 = bbox
    h = p.plate_size / 2.0  # type: ignore[attr-defined]
    if abs(z0) > _TOL or abs(z1) > _TOL:
        return False
    on_x = abs(x0 - x1) < _TOL and abs(abs(x0) - h) < _TOL
    on_y = abs(y0 - y1) < _TOL and abs(abs(y0) - h) < _TOL
    return on_x or on_y


def _plate_face(bbox, p: BaseModel) -> bool:
    return abs(bbox[2]) < _TOL and abs(bbox[5]) < _TOL


def _ball_face(bbox, p: BaseModel) -> bool:
    # Dolgu yüzeyinin OCC sınır kutusu kontrol çokgeninden gelir, gevşek (alt
    # yama z0 < 0 çıkabiliyor) — küre yüzü = plaka olmayan yüz.
    return not _plate_face(bbox, p)


def plate_area_mm2(p: PlateBallShellParams) -> float:
    return p.plate_size**2


def ball_area_mm2(p: PlateBallShellParams) -> float:
    return math.pi * p.ball_diameter**2


PLATE_BALL_SHELL = GeometryTemplate(
    id="plate_ball_shell",
    name="Plaka–küre — kabuk (darbe / delinme)",
    description=(
        "Kare plaka orta yüzeyi (z = 0) ve üstünde g boşlukla küre yüzeyi; iki ayrı kabuk "
        "parçası (0 plaka, 1 küre). Crash'te küre rijit gövde + hız, plaka kenarı sabit. "
        "Analitik yok."
    ),
    params_model=PlateBallShellParams,
    build=_build,
    regions=(
        Region(
            name=REGION_PLATE_EDGE,
            description="Plakanın dört dış kenarı (z = 0)",
            select=_plate_edge,
            dim=1,
            expected_faces=4,
        ),
        Region(
            name=REGION_PLATE,
            description="Plaka orta yüzeyi",
            select=_plate_face,
            dim=2,
            expected_faces=1,
        ),
        Region(
            name=REGION_BALL,
            description="Küre yüzeyi (impaktör, 6 yama)",
            select=_ball_face,
            dim=2,
            expected_faces=6,
        ),
    ),
    analytic=None,
    characteristic_length=lambda p: p.ball_diameter,
    default_element_ratio=(0.1, 0.2),
    # Durability akışı için geçerli bir yük durumu (şablon crash için): plaka
    # kenarı sabit + plakaya basınç; bağlantısız küre tekil kalmasın diye sabit.
    default_bcs=(
        {"type": "fixed", "region": REGION_PLATE_EDGE},
        {"type": "fixed", "region": REGION_BALL},
        {"type": "pressure", "region": REGION_PLATE, "magnitude": 0.1},
    ),
    tags=("crash", "kabuk", "darbe"),
    surface_only=True,
)
