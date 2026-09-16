"""Crash API — `/crash/solve` + ilerleme. CalculiX `/solve` dokunulmaz.

AnalysisRun tablosuna yazılmaz (durability geçmişine karışmasın).
Job `uploads/crash/{job_id}/job.json`.
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session, joinedload

from app.api.geometry import MESH_DIR, _get_geometry_or_404
from app.db.session import get_db
from app.jobs.progress import get_hub
from app.models.material import MaterialAssignment
from app.solvers.base import InputArtifact, SolverError
from app.solvers.crash_params import CrashBarrierParams, CrashModelParams
from app.solvers.openradioss import OpenRadiossAdapter, resolve_openradioss
from app.solvers.openradioss_progress import ParsedCrashProgress

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/crash", tags=["crash"])

CRASH_DIR = Path("uploads") / "crash"


class CrashSolveRequest(BaseModel):
    geometry_id: int
    barrier: CrashBarrierParams
    dimension: int = Field(default=3, description="Crash solid mesh — yalnız 3")
    run_solver: bool = False
    wait: bool = Field(
        default=False,
        description="True ise OpenRadioss bitene kadar bekler; varsayılan arka plan.",
    )
    t_end_ms: float = Field(default=10.0, gt=0)
    name: str | None = None
    th_nodes: list[int] = Field(default_factory=list)
    model: CrashModelParams = Field(default_factory=CrashModelParams)
    scenario: str = Field(default="rigid_wall", description="rigid_wall | plate_ball")

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
            out["hub_state"] = live.state
            out["kind"] = live.kind
    return out


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
        meta["status"] = "solved"
        meta["message"] = "OpenRadioss bitti"
        meta["solver_ran"] = True
        meta["scalars"] = parsed.scalars
        meta["curves"] = parsed.curves
        _write_job(meta)
        hub.update(job_id, state="done", percent=100.0, message=meta["message"])
    except Exception as exc:  # noqa: BLE001 — arka plan işi isteği düşürmesin
        logger.warning("crash job başarısız job_id=%s: %s", job_id, exc)
        meta["status"] = "failed"
        meta["message"] = str(exc)
        meta["solver_ran"] = False
        _write_job(meta)
        hub.update(job_id, state="failed", message=str(exc))


@router.post("/solve")
def crash_solve(
    body: CrashSolveRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """3D mesh + bariyer → OpenRadioss .rad; isteğe bağlı solver."""
    if body.dimension != 3:
        raise HTTPException(status_code=400, detail="crash yalnız dimension=3 (solid tet).")

    geo = _get_geometry_or_404(db, body.geometry_id)
    stem = Path(geo.current_filename).stem
    mesh_path = MESH_DIR / f"{stem}_d3.msh"
    if not mesh_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Önce dimension=3 mesh üretin ({mesh_path.name}).",
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
        }
        for a in assignments
    ]

    job_id = str(uuid.uuid4())
    work_dir = _job_dir(job_id)
    work_dir.mkdir(parents=True, exist_ok=True)
    adapter = OpenRadiossAdapter()
    try:
        artifact = adapter.build_input(
            {
                "output_dir": work_dir,
                "job_name": "crash",
                "mesh_path": mesh_path,
                "barrier": body.barrier.model_dump(),
                "materials": materials,
                "t_end_ms": body.t_end_ms,
                "th_nodes": body.th_nodes,
                "title": (body.name or "crash")[:80],
                "model": body.model.model_dump(),
                "scenario": body.scenario,
            }
        )
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
        "solver_ran": False,
        "openradioss_available": or_ok,
        "scalars": {},
        "curves": {},
    }
    _write_job(meta)
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
        "openradioss_available": or_ok,
        "solver_ran": False,
        "scalars": {},
    }

    if body.run_solver:
        if not or_ok:
            meta["status"] = "failed"
            meta["message"] = "OpenRadioss bulunamadı"
            _write_job(meta)
            hub.update(job_id, state="failed", message=meta["message"])
            result["status"] = "failed"
            result["message"] = meta["message"]
            return result
        if not body.wait:
            meta["status"] = "pending"
            meta["message"] = "OpenRadioss çalışıyor…"
            _write_job(meta)
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
