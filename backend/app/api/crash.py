"""Crash API — `/crash/solve` + ilerleme. CalculiX `/solve` dokunulmaz.

AnalysisRun tablosuna yazılmaz (durability geçmişine karışmasın).
Job `uploads/crash/{job_id}/job.json`.
"""

from __future__ import annotations

import json
import logging
import shutil
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session, joinedload

from app.api.geometry import MESH_DIR, _get_geometry_or_404
from app.api.crash_runs import record_from_meta
from app.db.session import SessionLocal, get_db
from app.jobs.progress import get_hub
from app.models.component import Component
from app.models.geometry import PhysicalGroup
from app.models.material import MaterialAssignment
from app.postprocess.crash_errors import classify_failure, crash_error, diverged_error, error_message
from app.solvers.base import InputArtifact, SolverError
from app.solvers.crash_params import (
    CrashBarrierParams,
    CrashContactParams,
    CrashBcParams,
    CrashBlastLoadParams,
    CrashEngineParams,
    CrashFilterParams,
    CrashGravityParams,
    CrashImpVelParams,
    CrashInitVelParams,
    CrashPressureLoadParams,
    CrashSphProjectileParams,
    CrashMassParams,
    CrashModelParams,
    CrashRigidBodyParams,
    CrashSectionParams,
    CrashThParams,
)
from app.solvers.openradioss import RAW_CARDS_MARKER, OpenRadiossAdapter, resolve_openradioss
from app.solvers.openradioss_ids import deck_inventory, raw_card_report
from app.solvers.openradioss_progress import ParsedCrashProgress

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/crash", tags=["crash"])

CRASH_DIR = Path("uploads") / "crash"


class CrashPartSpec(BaseModel):
    """Parça rolü: hareketli (ilk hız alır) ya da sabit (/BCS). Mühendis seçer."""

    part_id: int = Field(..., ge=0, description="Mesh part_id (hacim sırası)")
    role: str = Field(
        default="moving",
        description="moving (ilk hız) | fixed (tüm düğümler /BCS) | free (ilk hız yok, /BCS yok — 1.18b)",
    )
    thickness_mm: float | None = Field(
        default=None, gt=0, description="Kabuk parça kalınlığı (mm); solid parçada yok sayılır"
    )
    model: CrashModelParams | None = Field(
        default=None,
        description="Parça başına malzeme/eleman kartı (1.14b); boşsa istekteki global model",
    )

    @field_validator("role")
    @classmethod
    def _role_ok(cls, value: str) -> str:
        v = value.strip().lower()
        if v not in ("moving", "fixed", "free"):
            raise ValueError("role moving, fixed veya free olmalı.")
        return v


class CrashSolveRequest(BaseModel):
    geometry_id: int
    #: TODO 11.1 — varsayılan: hız 0 (yükleme başka mekanizmadan: /GRAV,
    #: /IMPVEL, SPH, patlama). Hız yönü `barrier.direction` ile duvardan bağımsız.
    barrier: CrashBarrierParams = Field(default_factory=lambda: CrashBarrierParams(speed_m_s=0.0))
    parts: list[CrashPartSpec] = Field(
        default_factory=list,
        description="Parça rolleri; verilmeyen parça hareketli sayılır.",
    )
    dimension: int = Field(default=3, description="3 = solid (tet/hex), 2 = kabuk (tri/quad)")
    run_solver: bool = False
    wait: bool = Field(
        default=False,
        description="True ise OpenRadioss bitene kadar bekler; varsayılan arka plan.",
    )
    t_end_ms: float = Field(default=10.0, gt=0)
    name: str | None = None
    th_nodes: list[int] = Field(default_factory=list)
    model: CrashModelParams = Field(default_factory=CrashModelParams)
    contacts: list[CrashContactParams] = Field(
        default_factory=list,
        description="Temas tanımları (/INTER/TYPE7 | TYPE24); boşsa temas yok.",
    )
    use_rigid_wall: bool = Field(
        default=True,
        description="False ise /RWALL yazılmaz (parça–parça çarpışma temasla).",
    )
    scenario: str = Field(default="rigid_wall", description="rigid_wall | plate_ball")
    engine: CrashEngineParams = Field(
        default_factory=CrashEngineParams,
        description="Çıktı aralıkları + zaman adımı kartı (1.15a); boş = eski davranış",
    )
    th: CrashThParams = Field(
        default_factory=CrashThParams,
        description="/TH grupları + değişkenleri (1.15b); boş = eski deck",
    )
    sections: list[CrashSectionParams] = Field(
        default_factory=list, description="/SECT/PARAL kesitleri (1.15c); TH th.sect"
    )
    added_masses: list[CrashMassParams] = Field(
        default_factory=list, description="/ADMAS — bölge ya da parçaya ek kütle (1.17b)"
    )
    rigid_bodies: list[CrashRigidBodyParams] = Field(
        default_factory=list, description="/RBODY — bölge ya da parça rijit + ana düğüme kütle (1.17b)"
    )
    boundary_conditions: list[CrashBcParams] = Field(
        default_factory=list, description="/BCS — bölge ya da parçada kilitli serbestlikler (1.17c)"
    )
    imposed_velocities: list[CrashImpVelParams] = Field(
        default_factory=list, description="/IMPVEL — bölge, parça ya da rijit gövdeye sabit hız (1.17c)"
    )
    initial_velocities: list[CrashInitVelParams] = Field(
        default_factory=list,
        description="/INIVEL — bölge ya da parçaya ilk hız (TODO 11.9); doluysa bariyer hızı parçalara verilmez",
    )
    filters: CrashFilterParams = Field(
        default_factory=CrashFilterParams, description="SAE J211 CFC sınıfları (1.17e); ham korunur"
    )
    gravity: CrashGravityParams | None = Field(
        default=None, description="/GRAV sabit yerçekimi (K2); boş = yok"
    )
    pressure_loads: list[CrashPressureLoadParams] = Field(
        default_factory=list, description="/PLOAD zamana bağlı basınç (K10, Friedlander)"
    )
    sph_projectiles: list[CrashSphProjectileParams] = Field(
        default_factory=list, description="SPH mermiler (K12, ör. kuş)"
    )
    blast_loads: list[CrashBlastLoadParams] = Field(
        default_factory=list, description="/LOAD/PBLAST ampirik patlama (K13, mayın)"
    )
    raw_cards: str = Field(
        default="",
        max_length=200_000,
        description="1.22a — OpenRadioss ham kartları (mesh düğüm/eleman ID'leriyle); /END'den önce aynen",
    )

    @field_validator("scenario")
    @classmethod
    def _scenario_ok(cls, value: str) -> str:
        v = value.strip().lower()
        if v not in ("rigid_wall", "plate_ball"):
            raise ValueError("scenario rigid_wall veya plate_ball olmalı.")
        return v


def _job_dir(job_id: str) -> Path:
    return CRASH_DIR / job_id


def _write_job(meta: dict[str, Any]) -> None:
    path = _job_dir(str(meta["job_id"])) / "job.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def _read_job(job_id: str) -> dict[str, Any] | None:
    path = _job_dir(job_id) / "job.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _merged_snapshot(job_id: str) -> dict[str, Any] | None:
    disk = _read_job(job_id)
    live = get_hub().get(job_id)
    if disk is None and live is None:
        return None
    out: dict[str, Any] = dict(disk or {})
    if live is not None:
        if disk is None:
            out.update(live.to_dict())
        else:
            out["percent"] = live.percent
            out["cycle"] = live.cycle
            out["time_ms"] = live.time_ms
            out["dt_ms"] = live.dt_ms
            out["mass_added_rel"] = live.mass_added_rel
            out["elapsed_s"] = live.elapsed_s
            out["remaining_s"] = live.remaining_s
            out["hub_state"] = live.state
            out["kind"] = live.kind
    return out


def _cleanup_outputs(work_dir: Path) -> list[str]:
    """1.17g — çözüm sonrası kullanılmayan çıktılar: Radioss restart (*.rst)
    dosyaları iş başına ~5 MB+ (crash klasörünün ~%49'u); restart desteği yok.
    `CRASH_KEEP_RST=1` ise dokunulmaz. Animasyon (A0xx) ve TH korunur."""
    import os

    if os.environ.get("CRASH_KEEP_RST", "").strip() in ("1", "true", "yes"):
        return []
    removed = []
    for f in sorted(work_dir.glob("*.rst")):
        try:
            f.unlink()
            removed.append(f.name)
        except OSError:
            pass
    return removed


def _sync_run(meta: dict[str, Any]) -> None:
    """1.16a — job.json durumunu crash_runs'a yansıt (arka plan işi kendi oturumuyla)."""
    db = SessionLocal()
    try:
        record_from_meta(db, meta)
    except Exception as exc:  # noqa: BLE001 — kayıt hatası çözümü düşürmesin
        logger.warning("crash_runs güncellenemedi job_id=%s: %s", meta.get("job_id"), exc)
        db.rollback()
    finally:
        db.close()


def _complete_crash_job(job_id: str) -> None:
    meta = _read_job(job_id)
    if meta is None:
        return
    hub = get_hub()
    hub.update(job_id, state="running", percent=0.0, message="OpenRadioss çalışıyor")

    def _cb(parsed: ParsedCrashProgress) -> None:
        state = "failed" if parsed.state == "failed" else "running"
        hub.update(
            job_id,
            state=state,
            percent=parsed.percent,
            cycle=parsed.cycle,
            time_ms=parsed.time_ms,
            dt_ms=parsed.dt_ms,
            mass_added_rel=parsed.mass_added_rel,
            elapsed_s=parsed.elapsed_s,
            remaining_s=parsed.remaining_s,
            message=parsed.message,
        )

    adapter = OpenRadiossAdapter()
    artifact = InputArtifact(path=Path(meta["starter_path"]))
    try:
        handle = adapter.submit(
            artifact,
            t_end_ms=float(meta.get("t_end_ms") or 10.0),
            progress_cb=_cb,
        )
        parsed = adapter.parse_results(handle)
        meta["removed_outputs"] = _cleanup_outputs(_job_dir(job_id))
        meta["solver_ran"] = True
        meta["scalars"] = parsed.scalars
        meta["curves"] = parsed.curves
        meta["diagnostics"] = dict(parsed.diagnostics)
        diverged = parsed.scalars.get("diverged_at_ms")
        if diverged is not None:
            # Iraksama hatadır (Radioss yine NORMAL TERMINATION yazabilir): failed,
            # eğri/animasyon ıraksama anına kadar incelensin diye saklanır.
            err = diverged_error(float(diverged))
            meta["diagnostics"]["error"] = err
            meta["status"] = "failed"
            meta["message"] = error_message(err)
        else:
            meta["status"] = "solved"
            meta["message"] = "OpenRadioss bitti"
        _write_job(meta)
        _sync_run(meta)
        hub.update(
            job_id,
            state="failed" if meta["status"] == "failed" else "done",
            percent=100.0,
            message=meta["message"],
        )
    except Exception as exc:  # noqa: BLE001 — arka plan işi isteği düşürmesin
        logger.warning("crash job başarısız job_id=%s: %s", job_id, exc)
        err = classify_failure(str(exc), _job_dir(job_id))
        meta["status"] = "failed"
        meta["message"] = error_message(err)
        meta["solver_ran"] = False
        meta["diagnostics"] = {**(meta.get("diagnostics") or {}), "error": err}
        _write_job(meta)
        _sync_run(meta)
        hub.update(job_id, state="failed", message=meta["message"])


def _starter_params(
    body: CrashSolveRequest, db: Session
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """İstek + DB (mesh, malzeme, bileşen, bölge) → adaptör parametreleri.

    /solve ve 1.22b ID envanteri aynı deck'i üretsin diye ortak; output_dir /
    job_name çağırana kalır. Döner: (params, materials, law36_curve_source).
    """
    if body.dimension not in (2, 3):
        raise HTTPException(
            status_code=400, detail="crash dimension=3 (solid) ya da dimension=2 (kabuk) ister."
        )

    geo = _get_geometry_or_404(db, body.geometry_id)
    stem = Path(geo.current_filename).stem
    mesh_path = MESH_DIR / f"{stem}_d{body.dimension}.msh"
    if not mesh_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Önce dimension={body.dimension} mesh üretin ({mesh_path.name}).",
        )

    assignments = (
        db.query(MaterialAssignment)
        .options(joinedload(MaterialAssignment.material))
        .filter(MaterialAssignment.geometry_id == body.geometry_id)
        .all()
    )
    if not assignments:
        raise HTTPException(
            status_code=422,
            detail="En az bir parça için malzeme atayın.",
        )

    materials = [
        {
            "part_id": a.part_id,
            "name": a.material.name,
            "density": a.material.density,
            "youngs_modulus": a.material.youngs_modulus,
            "poisson_ratio": a.material.poisson_ratio,
            "yield_strength": a.material.yield_strength,
            "material_id": a.material.id,
            "crash_curves": a.material.crash_curves,
        }
        for a in assignments
    ]
    # 1.14c2 — LAW36 eğrisinin kaynağı ve kullanılan eğri, parça başına. Malzeme
    # eğrisi sonradan değişse de iş kendi kopyasını job.json'da tutar.
    part_model = {p.part_id: p.model for p in body.parts if p.model is not None}
    law36_curve_source: dict[str, dict[str, Any]] = {}
    for m in materials:
        eff = part_model.get(m["part_id"], body.model)
        if eff.law == "tabulated":
            law36_curve_source[str(m["part_id"])] = (
                {"source": "istek", "curves": [c.model_dump() for c in eff.tab_curves]}
                if eff.tab_curves
                else {"source": f"malzeme #{m['material_id']}", "curves": m["crash_curves"]}
            )

    # Kabuk kalınlığının tek kaynağı ürün ağacı bileşeni (Malzeme adımı); aynı
    # mesh parça numarası (2D'de ATA, bileşen ve export hepsi mesh numarası).
    component_thickness: dict[int, float] = {}
    if body.dimension == 2:
        for comp in db.query(Component).filter(Component.geometry_id == body.geometry_id):
            if comp.property_kind == "shell" and comp.thickness and comp.thickness > 0:
                component_thickness[int(comp.part_id)] = float(comp.thickness)

    # 1.17b — kütle / rijit gövde bölgeleri: PhysicalGroup (CAD varlıkları) →
    # mesh düğümleri. Yalnız istekte geçen bölgeler okunur.
    wanted_regions = {
        s.region
        for s in [*body.added_masses, *body.rigid_bodies, *body.boundary_conditions, *body.imposed_velocities,
                  *body.initial_velocities]
        if s.region
    }
    region_nodes: dict[str, list[int]] = {}
    if wanted_regions:
        groups = {
            g.name: (int(g.dim), list(g.entity_tags or []))
            for g in db.query(PhysicalGroup).filter(PhysicalGroup.geometry_id == body.geometry_id)
            if g.name in wanted_regions
        }
        unknown = sorted(wanted_regions - set(groups))
        if unknown:
            raise HTTPException(
                status_code=422, detail=f"Bölge bu geometride yok: {', '.join(unknown)}"
            )
        from app.mesh.openradioss_export import region_node_ids

        region_nodes = region_node_ids(mesh_path, groups)

    params = {
        "mesh_path": mesh_path,
        "barrier": body.barrier.model_dump(),
        "materials": materials,
        "t_end_ms": body.t_end_ms,
        "engine": body.engine.model_dump(),
        "th": body.th.model_dump(),
        "sections": [s.model_dump() for s in body.sections],
        "th_nodes": body.th_nodes,
        "title": (body.name or "crash")[:80],
        "model": body.model.model_dump(),
        "scenario": body.scenario,
        "parts": [p.model_dump() for p in body.parts],
        "contacts": [c.model_dump() for c in body.contacts],
        "use_rigid_wall": body.use_rigid_wall,
        "component_thickness": component_thickness,
        "added_masses": [m.model_dump() for m in body.added_masses],
        "rigid_bodies": [r.model_dump() for r in body.rigid_bodies],
        "boundary_conditions": [b.model_dump() for b in body.boundary_conditions],
        "imposed_velocities": [v.model_dump() for v in body.imposed_velocities],
        "initial_velocities": [v.model_dump() for v in body.initial_velocities],
        "filters": body.filters.model_dump(),
        "gravity": body.gravity.model_dump() if body.gravity else None,
        "pressure_loads": [pl.model_dump() for pl in body.pressure_loads],
        "sph_projectiles": [sp.model_dump() for sp in body.sph_projectiles],
        "blast_loads": [bl.model_dump() for bl in body.blast_loads],
        "raw_cards": body.raw_cards,
        "region_nodes": region_nodes,
    }
    return params, materials, law36_curve_source


@router.post("/raw-cards/inventory")
def crash_raw_cards_inventory(
    body: CrashSolveRequest, db: Session = Depends(get_db)
) -> dict[str, Any]:
    """1.22b — bu istekle üretilecek deck'in ID envanteri + ham kart çakışmaları.

    Deck ham kartsız üretilir (geçici klasör, iş kaydı açılmaz); ham kartlar
    ayrıca taranır. Yalnız veri: öneri yok.
    """
    params, _, _ = _starter_params(body, db)
    params["raw_cards"] = ""
    tmp = CRASH_DIR / "_inventory" / str(uuid.uuid4())
    try:
        try:
            artifact = OpenRadiossAdapter().build_input({**params, "output_dir": tmp, "job_name": "crash"})
        except SolverError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        generated = artifact.path.read_text(encoding="utf-8")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return {**deck_inventory(generated), **raw_card_report(generated, body.raw_cards)}


def deck_outline(text: str) -> list[dict[str, Any]]:
    """1.23 D1 — deck kart listesi: sütun 1'de `/` ile başlayan her satır bir kart başlığı;
    blok bir sonraki başlığa kadar. `line` 1 tabanlı; `lines` blok satır sayısı."""
    lines = text.split("\n")
    heads = [i for i, ln in enumerate(lines) if ln.startswith("/")]
    out: list[dict[str, Any]] = []
    for k, i in enumerate(heads):
        end = heads[k + 1] if k + 1 < len(heads) else len(lines)
        out.append({"card": lines[i].rstrip(), "line": i + 1, "lines": end - i})
    return out


@router.post("/deck/preview")
def crash_deck_preview(body: CrashSolveRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    """1.23 D1 — üretilecek deck'i (ham kartlar dahil, koşudaki gibi) koşmadan döndürür:
    starter + engine metni ve kart listesi. Geçici klasör, iş kaydı yok. Salt görüntüleme."""
    params, _, _ = _starter_params(body, db)
    tmp = CRASH_DIR / "_preview" / str(uuid.uuid4())
    try:
        try:
            artifact = OpenRadiossAdapter().build_input({**params, "output_dir": tmp, "job_name": "crash"})
        except SolverError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        starter = artifact.path.read_text(encoding="utf-8")
        engine_path = artifact.path.with_name(artifact.path.name.replace("_0000.rad", "_0001.rad"))
        engine = engine_path.read_text(encoding="utf-8") if engine_path.exists() else ""
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return {
        "starter": starter,
        "engine": engine,
        "starter_outline": deck_outline(starter),
        "engine_outline": deck_outline(engine),
    }


@router.post("/raw-cards/check")
def crash_raw_cards_check(
    body: CrashSolveRequest, db: Session = Depends(get_db)
) -> dict[str, Any]:
    """1.22c — "Kontrol et": ham kartlı deck'te yalnız starter koşar (engine yok).

    Starter'ın ERROR / WARNING blokları aynen döner; iş kaydı açılmaz, geçici
    klasör silinir. `raw_cards_deck_line`: ham kartın deck'teki ilk satırı.
    """
    from app.postprocess.openradioss_th import starter_message_blocks

    params, _, _ = _starter_params(body, db)
    tmp = CRASH_DIR / "_check" / str(uuid.uuid4())
    adapter = OpenRadiossAdapter()
    try:
        try:
            artifact = adapter.build_input({**params, "output_dir": tmp, "job_name": "crash"})
        except SolverError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        deck = artifact.path.read_text(encoding="utf-8").split("\n")
        try:
            res = adapter.check_starter(artifact)
        except SolverError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    blocks = starter_message_blocks(res["out_text"])
    marker = next((i for i, ln in enumerate(deck, start=1) if ln == RAW_CARDS_MARKER), None)
    return {
        "exit_code": res["exit_code"],
        "errors": [b for b in blocks if b["kind"] == "error"],
        "warnings": [b for b in blocks if b["kind"] == "warning"],
        "raw_cards_deck_line": marker + 1 if marker else None,
        # .out yoksa (starter erken düştü) konsolun sonu — aynen.
        "console_tail": "" if res["out_text"] else "\n".join(res["console"].splitlines()[-40:]),
    }


@router.post("/solve")
def crash_solve(
    body: CrashSolveRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """3D (solid) ya da 2D (kabuk) mesh + bariyer → OpenRadioss .rad; isteğe bağlı solver."""
    params, materials, law36_curve_source = _starter_params(body, db)

    job_id = str(uuid.uuid4())
    work_dir = _job_dir(job_id)
    work_dir.mkdir(parents=True, exist_ok=True)
    adapter = OpenRadiossAdapter()
    try:
        artifact = adapter.build_input({**params, "output_dir": work_dir, "job_name": "crash"})
    except SolverError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    engine_path = artifact.path.with_name("crash_0001.rad")
    starter_text = artifact.path.read_text(encoding="utf-8")
    engine_text = engine_path.read_text(encoding="utf-8") if engine_path.is_file() else ""
    cards = {
        "has_tetra4": "/TETRA4" in starter_text,
        "has_rwall": "/RWALL" in starter_text,
        "has_inivel": "/INIVEL" in starter_text,
        "has_tfile": "/TFILE" in engine_text,
        "has_law2": "/MAT/LAW2" in starter_text,
        "has_law1": "/MAT/LAW1" in starter_text,
        "has_law36": "/MAT/LAW36" in starter_text,
        "n_fail": sum(1 for ln in starter_text.splitlines() if ln.startswith("/FAIL/")),
        "has_bcs": "/BCS/" in starter_text,
        "has_shell": "/SHELL/" in starter_text or "/SH3N/" in starter_text,
        "n_parts": sum(1 for ln in starter_text.splitlines() if ln.startswith("/PART/")),
        "n_inter": sum(1 for ln in starter_text.splitlines() if ln.startswith("/INTER/")),
        # Aynı konumda ayrı düğüm (bağlantısız eleman) sayısı — yalnız veri.
        "n_coincident_nodes": next(
            (
                int(ln.split(":", 1)[1])
                for ln in starter_text.splitlines()[:5]
                if ln.startswith("# coincident_nodes:")
            ),
            0,
        ),
    }
    or_ok = resolve_openradioss() is not None
    meta: dict[str, Any] = {
        "job_id": job_id,
        "geometry_id": body.geometry_id,
        "name": body.name,
        "status": "rad_only",
        "message": "rad üretildi",
        "t_end_ms": body.t_end_ms,
        "starter_path": str(artifact.path).replace("\\", "/"),
        "engine_path": str(engine_path).replace("\\", "/"),
        "barrier": body.barrier.model_dump(),
        "model": body.model.model_dump(),
        "scenario": body.scenario,
        "parts": [p.model_dump() for p in body.parts],
        "contacts": [c.model_dump() for c in body.contacts],
        "use_rigid_wall": body.use_rigid_wall,
        "engine": body.engine.model_dump(),
        "th": body.th.model_dump(),
        "sections": [s.model_dump() for s in body.sections],
        "added_masses": [m.model_dump() for m in body.added_masses],
        "rigid_bodies": [r.model_dump() for r in body.rigid_bodies],
        "boundary_conditions": [b.model_dump() for b in body.boundary_conditions],
        "imposed_velocities": [v.model_dump() for v in body.imposed_velocities],
        "initial_velocities": [v.model_dump() for v in body.initial_velocities],
        "filters": body.filters.model_dump(),
        "gravity": body.gravity.model_dump() if body.gravity else None,
        "pressure_loads": [pl.model_dump() for pl in body.pressure_loads],
        "sph_projectiles": [sp.model_dump() for sp in body.sph_projectiles],
        "blast_loads": [bl.model_dump() for bl in body.blast_loads],
        "raw_cards": body.raw_cards,
        "dimension": body.dimension,
        "solver_ran": False,
        "openradioss_available": or_ok,
        "law36_curve_source": law36_curve_source,
        "materials": materials,
        "scalars": {},
        "curves": {},
    }
    _write_job(meta)
    run = record_from_meta(db, meta)
    hub = get_hub()
    hub.create(job_id)

    result: dict[str, Any] = {
        "job_id": job_id,
        "geometry_id": body.geometry_id,
        "status": meta["status"],
        "message": meta["message"],
        "starter_url": f"/files/crash/{job_id}/{artifact.path.name}",
        "engine_url": f"/files/crash/{job_id}/{engine_path.name}",
        "progress_url": f"/crash/jobs/{job_id}",
        "ws_url": f"/crash/jobs/{job_id}/ws",
        "cards": cards,
        "run_id": run.id if run is not None else None,
        "law36_curve_source": law36_curve_source,
        "openradioss_available": or_ok,
        "solver_ran": False,
        "scalars": {},
    }

    if body.run_solver:
        if not or_ok:
            err = crash_error(5)
            meta["status"] = "failed"
            meta["message"] = error_message(err)
            meta["diagnostics"] = {"error": err}
            _write_job(meta)
            record_from_meta(db, meta)
            hub.update(job_id, state="failed", message=meta["message"])
            result["status"] = "failed"
            result["message"] = meta["message"]
            result["diagnostics"] = meta["diagnostics"]
            return result
        if not body.wait:
            meta["status"] = "pending"
            meta["message"] = "OpenRadioss çalışıyor…"
            _write_job(meta)
            record_from_meta(db, meta)
            hub.update(job_id, state="running", percent=0.0, message=meta["message"])
            background_tasks.add_task(_complete_crash_job, job_id)
            result["status"] = "pending"
            result["message"] = meta["message"]
        else:
            _complete_crash_job(job_id)
            done = _read_job(job_id) or meta
            result["status"] = done.get("status")
            result["message"] = done.get("message")
            result["solver_ran"] = bool(done.get("solver_ran"))
            result["scalars"] = done.get("scalars") or {}
            result["diagnostics"] = done.get("diagnostics") or {}

    else:
        hub.update(job_id, state="done", percent=0.0, message="rad_only")

    logger.info(
        "Crash solve: geometry_id=%s job_id=%s status=%s",
        body.geometry_id,
        job_id,
        result["status"],
    )
    return result


@router.get("/jobs/{job_id}")
def crash_job_snapshot(job_id: str) -> dict:
    snap = _merged_snapshot(job_id)
    if snap is None:
        raise HTTPException(status_code=404, detail="crash job yok")
    return snap


_CFC_CLASSES = (60, 180, 600, 1000)


@router.get("/jobs/{job_id}/cfc")
def crash_job_refilter(job_id: str, force_cfc: int | None = None, acc_cfc: int | None = None) -> dict[str, Any]:
    """Koşu sonrası yeniden süzme (post-process, kullanıcı 2026-10-08): kayıtlı ham
    TH'den farklı CFC sınıfıyla süzülmüş kuvvet / ivme eğrileri ve tepe / HIC.
    Çözücü yeniden koşmaz; koşunun kendi kaydı değişmez."""
    for name, v in (("force_cfc", force_cfc), ("acc_cfc", acc_cfc)):
        if v is not None and v not in _CFC_CLASSES:
            raise HTTPException(status_code=422, detail=f"{name}: {', '.join(map(str, _CFC_CLASSES))} olmalı")
    work = _job_dir(job_id)
    if not work.is_dir():
        raise HTTPException(status_code=404, detail="crash job yok")
    from app.postprocess.openradioss_th import parse_openradioss_dir

    res = parse_openradioss_dir(work, filters_override={"force_cfc": force_cfc, "acc_cfc": acc_cfc})
    suffixes = tuple(f"_cfc{c}" for c in (force_cfc, acc_cfc) if c)
    curves = {k: v for k, v in res.curves.items() if k == "time" or k.endswith(suffixes)}
    scalars = {k: v for k, v in res.scalars.items() if suffixes and k.endswith(suffixes)}
    return {"job_id": job_id, "force_cfc": force_cfc, "acc_cfc": acc_cfc, "curves": curves, "scalars": scalars}


@router.websocket("/jobs/{job_id}/ws")
async def crash_job_ws(websocket: WebSocket, job_id: str) -> None:
    hub = get_hub()
    if hub.get(job_id) is None:
        disk = _read_job(job_id)
        if disk is not None:
            hub.create(job_id)
            hub.update(
                job_id,
                state=disk.get("status") if disk.get("status") in ("done", "failed", "pending", "running") else "pending",
                message=str(disk.get("message") or ""),
            )
            if disk.get("status") == "solved":
                hub.update(job_id, state="done", percent=100.0)
            elif disk.get("status") == "rad_only":
                hub.update(job_id, state="done", percent=0.0, message="rad_only")
            elif disk.get("status") == "failed":
                hub.update(job_id, state="failed")
        else:
            await websocket.close(code=4404)
            return
    await websocket.accept()
    try:
        while True:
            job = hub.get(job_id)
            if job is None:
                break
            await websocket.send_json(job.to_dict())
            if job.state in ("done", "failed"):
                break
            await hub.wait(job_id, timeout=1.0)
    except WebSocketDisconnect:
        return
