"""Crash senaryo şablonu — 1.17a.

Tek çağrıda uçtan uca crash koşusu: geometri şablonu → 2D mesh → malzeme
ataması → /crash/solve (kabuk kalınlığı, bariyer, model, engine/th/kesitler).
Yeni çözücü mantığı yok: mevcut uçların fonksiyonlarını sırayla çağırır
(0.5.4 DOE runner deseni). Hangi parametrenin değişeceğine mühendis karar
verir; burada hepsi açık girdi, varsayılanlar 1.13–1.16 elle koşulan crash box
(geometri 3931) kurulumu.

1.18b — `plate_ball_shell`: plaka (parça 0, rol free) + küre (parça 1,
moving). `template_defaults` açıkken boş listeler şablon kurulumuyla dolar:
küre rijit gövde (bölge kure, `ball_mass_kg` ana düğüme), plaka kenarı /BCS
111111, küre → plaka TYPE7 (master küre, slave plaka düğümleri); rijit duvar
yok, ilk hız −z (normal +z, açı 0). Değerler isteğin açık alanları; dolu
liste olduğu gibi kullanılır.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field, ValidationError, model_validator
from sqlalchemy.orm import Session

from app.api.crash import CrashSolveRequest, crash_solve
from app.api.crash_catalog import scenario_templates
from app.api.geometry import GenerateMeshRequest, generate_mesh
from app.db.session import get_db
from app.models.material import Material, MaterialAssignment
from app.solvers.crash_params import (
    CrashContactParams,
    CrashBcParams,
    CrashEngineParams,
    CrashFilterParams,
    CrashGravityParams,
    CrashImpVelParams,
    CrashMassParams,
    CrashPressureLoadParams,
    CrashModelParams,
    CrashRigidBodyParams,
    CrashSectionParams,
    CrashThParams,
)
from app.templates import get_template
from app.templates.service import create_geometry_from_template

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/crash", tags=["crash"])

#: Crash senaryosu kurulabilen şablonlar → mesh boyutu; kaynak katalog (K0,
#: durum ready). Yeni senaryo = katalog maddesi + aşağıdaki kurulum.
CRASH_TEMPLATES: dict[str, int] = scenario_templates()


class CrashWall(BaseModel):
    point: tuple[float, float, float]
    normal: tuple[float, float, float]


class CrashScenarioRequest(BaseModel):
    template_id: str = Field(default="crash_box_shell")
    geometry: dict[str, Any] = Field(
        default_factory=dict, description="Şablon parametreleri (mm); boş alan = şablon varsayılanı"
    )
    element_size_mm: float = Field(default=5.0, gt=0)
    element_scheme: str = Field(default="quad", description="2D: quad | tet (tri) | mix")
    material_id: int | None = Field(default=None, description="Boş = material_name ile aranır")
    material_name: str = Field(default="S235")
    # 1.18b — plaka–küre: küre parçası (rijit gövde) için ayrı malzeme / kabuk
    # kalınlığı / ana düğüm kütlesi; boş malzeme = plaka malzemesi.
    ball_material_id: int | None = Field(default=None, description="Küre malzemesi; boş = plaka malzemesi")
    ball_thickness_mm: float = Field(default=1.0, gt=0, description="Küre kabuk kalınlığı (mm)")
    ball_mass_kg: float = Field(default=0.0, ge=0, description="Küre rijit gövde ana düğüm kütlesi (kabuk kütlesine ek)")
    # K5 — verilirse ek kütle = toplam − küre kabuk kütlesi (π·D²·t·ρ, küre malzemesi)
    ball_total_mass_kg: float | None = Field(default=None, gt=0, description="Küre toplam kütlesi (kg)")
    template_defaults: bool = Field(
        default=True, description="Boş listeleri şablonun crash kurulumuyla doldur (plate_ball_shell, drop_box_shell)"
    )
    # K2 — düşme testi: H verilirse çarpma hızı √(2·|g|·H) (speed_m_s yerine);
    # gravity boşsa drop_box_shell'de şablon varsayılanı −9.81 m/s² Z.
    drop_height_mm: float | None = Field(default=None, gt=0, description="Düşme yüksekliği H (mm)")
    # K3 — direk yan çarpması: silindirik rijit duvar çapı ve uç kütleleri
    pole_diameter_mm: float = Field(default=254.0, gt=0, description="Direk çapı D (mm)")
    end_mass_kg: float = Field(default=0.0, ge=0, description="Her uç rijit gövdesinin ek kütlesi (kg)")
    # K4 — ROPS: yük köşesine zorlanmış yanal itme hızı (m/s); yavaş itme
    push_speed_m_s: float = Field(default=1.0, gt=0, description="ROPS yanal itme hızı (m/s)")
    # K10 — patlama: Friedlander basınç darbesi (plaka yüzeyine)
    blast_peak_mpa: float = Field(default=2.0, description="Ps (MPa), işaretli")
    blast_duration_ms: float = Field(default=0.2, gt=0, description="td (ms)")
    blast_decay: float = Field(default=1.0, ge=0, description="Friedlander b")
    pressure_loads: list[CrashPressureLoadParams] = Field(default_factory=list)
    gravity: CrashGravityParams | None = Field(default=None, description="/GRAV; boş = yok (düşmede varsayılan)")
    thickness_mm: float | None = Field(
        default=None, gt=0, description="Kabuk kalınlığı; boş = şablonun cidar kalınlığı (wall)"
    )
    speed_m_s: float = Field(default=10.0)
    angle_deg: float = Field(default=0.0)
    wall: CrashWall | None = Field(
        default=None,
        description="Rijit duvar; boş = şablondan: ön uç (x = 0) kesit merkezi, normal +x",
    )
    t_end_ms: float = Field(default=4.0, gt=0)
    model: CrashModelParams = Field(default_factory=lambda: CrashModelParams(law="plastic"))
    engine: CrashEngineParams = Field(default_factory=CrashEngineParams)
    th: CrashThParams = Field(default_factory=CrashThParams)
    sections: list[CrashSectionParams] = Field(default_factory=list)
    contacts: list[CrashContactParams] = Field(default_factory=list)
    added_masses: list[CrashMassParams] = Field(default_factory=list)
    rigid_bodies: list[CrashRigidBodyParams] = Field(
        default_factory=list,
        description="Ör. kızak: region 'kutu_arka' + mass_kg (değer mühendisin)",
    )
    boundary_conditions: list[CrashBcParams] = Field(default_factory=list)
    imposed_velocities: list[CrashImpVelParams] = Field(default_factory=list)
    filters: CrashFilterParams = Field(default_factory=CrashFilterParams)
    name: str | None = None
    run_solver: bool = True
    wait: bool = False

    @model_validator(mode="after")
    def _template_ok(self) -> "CrashScenarioRequest":
        if self.template_id not in CRASH_TEMPLATES:
            raise ValueError(
                f"Crash senaryosu yalnız {sorted(CRASH_TEMPLATES)} şablonlarıyla kurulur."
            )
        return self


def _resolved_geometry(req: CrashScenarioRequest) -> dict[str, Any]:
    """Şablon parametreleri varsayılanlarla birleşik, doğrulanmış (wall vb. buradan)."""
    model = get_template(req.template_id).params_model
    return model.model_validate(req.geometry).model_dump()


def _default_wall(template_id: str, g: dict[str, Any], req: "CrashScenarioRequest | None" = None) -> dict[str, Any]:
    if template_id == "pole_beam_shell":
        # K3 — direk ekseni z, kiriş ortasında; yüzeyi ön dış yüzden (x = 0) g geride.
        d = req.pole_diameter_mm if req is not None else 254.0
        return {"kind": "cyl", "point": (-float(g["gap"]) - d / 2.0, float(g["length"]) / 2.0, float(g["width"]) / 2.0),
                "normal": (1.0, 0.0, 0.0), "axis": (0.0, 0.0, 1.0), "diameter_mm": d}
    if template_id == "drop_box_shell":
        # K2 — zemin z = 0, normal +z; açı 0 → ilk hız −z.
        return {"point": (0.0, 0.0, 0.0), "normal": (0.0, 0.0, 1.0)}
    if template_id == "hopkinson_bar":
        # K9 — duvar yok; normal −x → ilk hız +x (çarpıcı giriş çubuğuna doğru).
        return {"point": (0.0, 0.0, 0.0), "normal": (-1.0, 0.0, 0.0)}
    if template_id == "s_rail_shell":
        # K7 — ön uç x = 0 (+x normal), kesit merkezi eksende; kiriş −x ile gelir.
        return {"point": (0.0, 0.0, 0.0), "normal": (1.0, 0.0, 0.0)}
    if template_id == "taylor_bar":
        # K1 — çarpma yüzü x = 0, eksen merkezde; çubuk −x ile gelir.
        return {"point": (0.0, 0.0, 0.0), "normal": (1.0, 0.0, 0.0)}
    if template_id in ("plate_ball_shell", "rops_frame_shell", "door_beam_shell", "blast_plate_shell", "bucket_rock_shell"):
        # Duvar yazılmaz; normal yalnız ilk hız yönü için (açı 0 → −z, plakaya doğru;
        # ROPS'ta hareketli parça yok, ilk hız kullanılmaz).
        return {"point": (0.0, 0.0, 0.0), "normal": (0.0, 0.0, 1.0)}
    # crash_box_shell: kutu x ekseninde, ön uç x = 0; nokta dış kesit merkezi.
    return {"point": (0.0, g["box_height"] / 2.0, g["box_width"] / 2.0), "normal": (1.0, 0.0, 0.0)}


def _rops_setup(req: "CrashScenarioRequest", g: dict[str, Any], t: float) -> dict[str, Any]:
    """K4 ROPS: hareketli parça yok, duvar yok; tabanlar /BCS, yük köşesi rijit
    gövde + zorlanmış +y hızı, iki dikmeyi z = H/2'de kesen /SECT (kuvvet)."""
    out: dict[str, Any] = {
        "use_rigid_wall": False,
        "parts": [{"part_id": 0, "role": "free", "thickness_mm": t}],
        "rigid_bodies": req.rigid_bodies,
        "boundary_conditions": req.boundary_conditions,
        "imposed_velocities": req.imposed_velocities,
        "sections": req.sections,
    }
    if req.template_defaults:
        if not req.boundary_conditions:
            out["boundary_conditions"] = [
                CrashBcParams(name="taban_1", region="taban_1", dofs="111111"),
                CrashBcParams(name="taban_2", region="taban_2", dofs="111111"),
            ]
        if not req.rigid_bodies:
            out["rigid_bodies"] = [CrashRigidBodyParams(name="yuk", region="yuk", mass_kg=0.0)]
        if not req.imposed_velocities:
            out["imposed_velocities"] = [
                CrashImpVelParams(name="itme", rigid_body="yuk", direction="Y", velocity_m_s=req.push_speed_m_s)
            ]
        if not req.sections:
            h, w = float(g["height"]), float(g["span"])
            m = max(float(g["depth"]), float(g["width"])) * 2.0
            out["sections"] = [CrashSectionParams(
                name="dikmeler_z_H2", origin=(-m, -m, h / 2.0), corner1=(m, -m, h / 2.0),
                corner2=(-m, w + m, h / 2.0),
            )]
    return out


def _door_setup(req: "CrashScenarioRequest", t: float) -> dict[str, Any]:
    """K8 kapı intrüzyonu: hareketli parça yok; kiriş uçları /BCS, impaktör rijit
    gövde + zorlanmış +x hızı, impaktör (master) → kiriş (slave) TYPE7."""
    out: dict[str, Any] = {
        "use_rigid_wall": False,
        "parts": [
            {"part_id": 0, "role": "free", "thickness_mm": t},
            {"part_id": 1, "role": "free", "thickness_mm": req.ball_thickness_mm},
        ],
        "rigid_bodies": req.rigid_bodies,
        "boundary_conditions": req.boundary_conditions,
        "imposed_velocities": req.imposed_velocities,
        "contacts": req.contacts,
    }
    if req.template_defaults:
        if not req.boundary_conditions:
            out["boundary_conditions"] = [
                CrashBcParams(name="uc_1", region="uc_1", dofs="111111"),
                CrashBcParams(name="uc_2", region="uc_2", dofs="111111"),
                # İmpaktör yalnız x'te (zorlanmış hız) — kılavuzsuz ilk koşuda (#93, #94) eğri
                # temasta z'ye kayıp dönerek kirişten ayrıldı (kuvvet ~25 mm'de sıfır).
                CrashBcParams(name="impaktor_kilavuz", rigid_body="impaktor", dofs="011111"),
            ]
        if not req.rigid_bodies:
            out["rigid_bodies"] = [CrashRigidBodyParams(name="impaktor", region="impaktor", mass_kg=0.0)]
        if not req.imposed_velocities:
            out["imposed_velocities"] = [
                CrashImpVelParams(name="itme", rigid_body="impaktor", direction="X", velocity_m_s=req.push_speed_m_s)
            ]
        if not req.contacts:
            out["contacts"] = [CrashContactParams(type=7, master_part=1, slave_part=0)]
    return out


def _plate_ball_setup(
    req: CrashScenarioRequest, g: dict[str, Any], plate_t: float, ball_added_kg: float | None = None,
    ball_region: str = "kure", edge_region: str = "plaka_kenar",
) -> dict[str, Any]:
    """plate_ball_shell crash kurulumu: parçalar + (boşsa) RBODY / BCS / temas.
    K5: küre ana düğüm ivmesi TH'de (HIC / CFC kanalı)."""
    out: dict[str, Any] = {
        "use_rigid_wall": False,
        "scenario": "plate_ball",
        "parts": [
            {"part_id": 0, "role": "free", "thickness_mm": plate_t},
            {"part_id": 1, "role": "moving", "thickness_mm": req.ball_thickness_mm},
        ],
        "rigid_bodies": req.rigid_bodies,
        "boundary_conditions": req.boundary_conditions,
        "contacts": req.contacts,
    }
    if req.template_defaults:
        if not req.rigid_bodies:
            added = req.ball_mass_kg if ball_added_kg is None else ball_added_kg
            out["rigid_bodies"] = [CrashRigidBodyParams(name=ball_region, region=ball_region, mass_kg=added, th_accel=True)]
        if not req.boundary_conditions:
            out["boundary_conditions"] = [CrashBcParams(name=edge_region, region=edge_region, dofs="111111")]
        if not req.contacts:
            out["contacts"] = [CrashContactParams(type=7, master_part=1, slave_part=0)]
    return out


def _material(db: Session, req: CrashScenarioRequest) -> Material:
    if req.material_id is not None:
        mat = db.get(Material, req.material_id)
    else:
        mat = db.query(Material).filter(Material.name == req.material_name).one_or_none()
    if mat is None:
        raise HTTPException(status_code=404, detail="Malzeme bulunamadı.")
    return mat


@router.post("/scenario")
def crash_scenario(
    req: CrashScenarioRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Şablon → mesh → malzeme → crash çözümü; crash_runs kaydı /crash/solve'dan."""
    try:
        g = _resolved_geometry(req)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=f"Şablon parametresi geçersiz: {exc}") from exc
    mat = _material(db, req)
    dimension = CRASH_TEMPLATES[req.template_id]

    try:
        geo, _regions, _tess = create_geometry_from_template(db, req.template_id, g)
    except Exception as exc:  # noqa: BLE001 — şablon kurulum hataları 422
        raise HTTPException(status_code=422, detail=f"Geometri kurulamadı: {exc}") from exc
    db.add(MaterialAssignment(geometry_id=geo.id, part_id=0, material_id=mat.id))
    ball_mat = None
    if req.template_id in ("plate_ball_shell", "door_beam_shell", "hopkinson_bar", "bucket_rock_shell"):
        ball_mat = db.get(Material, req.ball_material_id) if req.ball_material_id is not None else mat
        if ball_mat is None:
            raise HTTPException(status_code=404, detail="Küre malzemesi bulunamadı.")
        db.add(MaterialAssignment(geometry_id=geo.id, part_id=1, material_id=ball_mat.id))
    db.commit()

    # 3D (K1): kart "quad" varsayılanı solidde hex değil tet üretiyor (Recombine3D
    # yalnız tet bıraktı, ölçüldü) — solid şablonlarda açıkça tet.
    scheme = req.element_scheme if dimension == 2 or req.element_scheme != "quad" else "tet"
    generate_mesh(
        geo.id,
        GenerateMeshRequest(element_size=req.element_size_mm, dimension=dimension, element_scheme=scheme),
        db,
    )

    wall_key = {"plate_ball_shell": "plate_thickness", "blast_plate_shell": "plate_thickness",
                "bucket_rock_shell": "thickness"}.get(req.template_id, "wall")
    if dimension == 3:
        thickness = None  # solid: kabuk kalınlığı yok
    else:
        thickness = req.thickness_mm if req.thickness_mm is not None else float(g[wall_key])
    wall = req.wall.model_dump() if req.wall is not None else _default_wall(req.template_id, g, req)
    setup: dict[str, Any] = {
        "parts": [{"part_id": 0, "role": "moving", **({"thickness_mm": thickness} if thickness else {})}],
        "rigid_bodies": req.rigid_bodies,
        "boundary_conditions": req.boundary_conditions,
        "contacts": req.contacts,
    }
    ball_added_kg: float | None = None
    ball_key = {"plate_ball_shell": "ball_diameter", "bucket_rock_shell": "rock_diameter"}.get(req.template_id)
    if ball_key and req.ball_total_mass_kg is not None and ball_mat is not None:
        shell_kg = math.pi * float(g[ball_key]) ** 2 * req.ball_thickness_mm * float(ball_mat.density) * 1e-9
        ball_added_kg = max(0.0, req.ball_total_mass_kg - shell_kg)
    if req.template_id == "plate_ball_shell":
        setup = _plate_ball_setup(req, g, thickness, ball_added_kg)
    if req.template_id == "bucket_rock_shell":
        # K11 — taş rijit gövde (+ ivme kanalı), kepçe uzun kenarları /BCS, taş → taban TYPE7.
        setup = _plate_ball_setup(req, g, thickness, ball_added_kg, ball_region="tas", edge_region="kepce_kenar")
    if req.template_id == "rops_frame_shell":
        setup = _rops_setup(req, g, thickness)
    if req.template_id == "door_beam_shell":
        setup = _door_setup(req, thickness)
    if req.template_id == "blast_plate_shell":
        # K10 — hareketli parça / duvar yok; kenarlar /BCS, yük /PLOAD (Friedlander).
        setup = {
            "use_rigid_wall": False,
            "parts": [{"part_id": 0, "role": "free", "thickness_mm": thickness}],
            "boundary_conditions": req.boundary_conditions or (
                [CrashBcParams(name="plaka_kenar", region="plaka_kenar", dofs="111111")] if req.template_defaults else []
            ),
            "pressure_loads": req.pressure_loads or (
                [CrashPressureLoadParams(name="patlama", part_id=0, peak_mpa=req.blast_peak_mpa,
                                         duration_ms=req.blast_duration_ms, decay=req.blast_decay)]
                if req.template_defaults else []
            ),
            "rigid_bodies": req.rigid_bodies,
        }
    if req.template_id == "hopkinson_bar":
        # K9 — giriş çubuğu serbest (BC yok), çarpıcı hareketli; çarpıcı → giriş TYPE7;
        # kuvvet x = Li/4 kesitinden (yansıma dönmeden). Duvar yok.
        li, dd = float(g["bar_length"]), float(g["diameter"])
        setup = {
            "use_rigid_wall": False,
            "parts": [{"part_id": 0, "role": "free"}, {"part_id": 1, "role": "moving"}],
            "rigid_bodies": req.rigid_bodies,
            "boundary_conditions": req.boundary_conditions,
            "contacts": req.contacts or ([CrashContactParams(type=7, master_part=0, slave_part=1)] if req.template_defaults else []),
            "sections": req.sections or ([CrashSectionParams(
                name="giris_Li_4", origin=(li / 4.0, -dd, -dd), corner1=(li / 4.0, dd, -dd),
                corner2=(li / 4.0, -dd, dd), parts=[0],
            )] if req.template_defaults else []),
        }
    if req.template_id == "s_rail_shell" and req.template_defaults and not req.boundary_conditions:
        # K7 — kızak kızakta yönlendirilir: yalnız x ötelemesi serbest (gerçek S-kiriş
        # testi). Yönlendirmesiz ilk koşu (#90) yana kırılıp dönerek duvardan ayrıldı.
        guided = [rb.name for rb in req.rigid_bodies if rb.region == "arka_halka"]
        if guided:
            setup["boundary_conditions"] = [
                CrashBcParams(name=f"kilavuz_{n}", rigid_body=n, dofs="011111") for n in guided
            ]
    if req.template_id == "pole_beam_shell" and req.template_defaults and not req.rigid_bodies:
        # K3 — uç halkaları rijit gövde (araç kütlesi temsili), ek kütle mühendisin.
        setup["rigid_bodies"] = [
            CrashRigidBodyParams(name="uc_1", region="uc_1", mass_kg=req.end_mass_kg),
            CrashRigidBodyParams(name="uc_2", region="uc_2", mass_kg=req.end_mass_kg),
        ]
    gravity = req.gravity
    if gravity is None and req.template_id == "drop_box_shell" and req.template_defaults:
        gravity = CrashGravityParams(accel_m_s2=-9.81, direction="Z")
    speed = req.speed_m_s
    if req.drop_height_mm is not None:
        g_abs = abs(gravity.accel_m_s2) if gravity is not None else 9.81
        speed = math.sqrt(2.0 * g_abs * req.drop_height_mm / 1000.0)
    solve = CrashSolveRequest(
        geometry_id=geo.id,
        dimension=dimension,
        run_solver=req.run_solver,
        wait=req.wait,
        t_end_ms=req.t_end_ms,
        name=req.name,
        barrier={"speed_m_s": speed, "angle_deg": req.angle_deg, "wall": wall},
        gravity=gravity,
        model=req.model,
        engine=req.engine,
        th=req.th,
        added_masses=req.added_masses,
        **{"sections": req.sections, "imposed_velocities": req.imposed_velocities,
           "pressure_loads": req.pressure_loads, **setup},
        filters=req.filters,
    )
    result = crash_solve(solve, background_tasks, db)
    logger.info(
        "Crash senaryo: template=%s geometry_id=%s run_id=%s", req.template_id, geo.id, result.get("run_id")
    )
    return {
        "geometry_id": geo.id,
        "scenario": {
            "template_id": req.template_id,
            "geometry": g,
            "element_size_mm": req.element_size_mm,
            "element_scheme": scheme,
            "material_id": mat.id,
            "material_name": mat.name,
            "thickness_mm": thickness,
            "wall": wall,
            "speed_m_s": speed,
            "drop_height_mm": req.drop_height_mm,
            "gravity": gravity.model_dump() if gravity is not None else None,
            **(
                {
                    "ball_material_id": ball_mat.id,
                    "ball_material_name": ball_mat.name,
                    "ball_thickness_mm": req.ball_thickness_mm,
                    "ball_mass_kg": req.ball_mass_kg if ball_added_kg is None else ball_added_kg,
                    "ball_total_mass_kg": req.ball_total_mass_kg,
                }
                if ball_mat is not None
                else {}
            ),
        },
        "crash": result,
    }


#: 1.17f validasyon raporu (scripts/crash_validation.py üretir; repo docs/validation).
VALIDATION_REPORT = Path(__file__).resolve().parents[3] / "docs" / "validation" / "crash_validation.json"


@router.get("/validation")
def crash_validation_report() -> dict[str, Any]:
    """Son validasyon raporu (veri; kabul kriteri yok)."""
    import json

    if not VALIDATION_REPORT.is_file():
        raise HTTPException(status_code=404, detail="Validasyon raporu yok (scripts/crash_validation.py).")
    return json.loads(VALIDATION_REPORT.read_text(encoding="utf-8"))
