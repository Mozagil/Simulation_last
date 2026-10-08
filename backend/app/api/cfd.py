"""CFD (OpenFOAM) koşu API'si — Faz 2.2.

POST /cfd/solve    case parametreleri + blockMeshDict → iş klasörü, arka planda koşu
GET  /cfd/jobs/{id} job.json + canlı residual geçmişi
WS   /cfd/jobs/{id}/ws  ilerleme (iterasyon, yüzde, son residual'lar)

Durability `/solve` ve crash yollarına dokunulmaz. Koşu kaydı (DB, `cfd_runs`)
2.4'te ayrı onayla; şimdilik iş durumu `uploads/cfd/<job_id>/job.json`.
Mesh şimdilik ham ``blockMeshDict`` metni olarak gelir — parametrik kanal 2.3'te,
STEP → snappyHexMesh 2.5'te.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from app.jobs.progress import get_hub
from app.solvers.base import InputArtifact, SolverError
from app.solvers.openfoam import OpenFoamAdapter, SolverLog, residual_result, resolve_openfoam_image
from app.solvers.openfoam_case import CfdCaseParams

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cfd", tags=["cfd"])

CFD_DIR = Path("uploads") / "cfd"

# job_id → canlı residual geçmişi (ws / GET için; iş bitince job.json'a yazılır)
_live_lock = threading.Lock()
_live: dict[str, dict[str, Any]] = {}


class CfdSolveRequest(BaseModel):
    case: CfdCaseParams
    #: Ham OpenFOAM blockMeshDict metni (yama adları case.patches ile aynı olmalı).
    block_mesh_dict: str = Field(min_length=1)
    run_solver: bool = True
    #: True: istek koşu bitene kadar bekler (test / betik). False: arka plan.
    wait: bool = False


def _job_dir(job_id: str) -> Path:
    return CFD_DIR / job_id


def _write_job(meta: dict[str, Any]) -> None:
    path = _job_dir(str(meta["job_id"])) / "job.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def _read_job(job_id: str) -> dict[str, Any] | None:
    path = _job_dir(job_id) / "job.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _live_snapshot(log: SolverLog, end_iter: int) -> dict[str, Any]:
    last = log.last_iteration or 0
    return {
        "iteration": last,
        "percent": min(100.0, 100.0 * float(last) / end_iter) if end_iter > 0 else 0.0,
        "residuals": {k: list(v) for k, v in log.initial_residuals.items()},
        "iterations": list(log.iterations),
    }


def _complete_cfd_job(job_id: str) -> None:
    meta = _read_job(job_id)
    if meta is None:
        return
    hub = get_hub()
    app = meta.get("application", "solver")
    end_iter = int(meta.get("end_iterations") or 0)
    hub.update(job_id, state="running", percent=0.0, message=f"{app} çalışıyor")

    def _cb(log: SolverLog) -> None:
        snap = _live_snapshot(log, end_iter)
        with _live_lock:
            _live[job_id] = snap
        last = {k: v[-1] for k, v in log.initial_residuals.items() if v}
        msg = f"iterasyon {snap['iteration']}" + (
            " · " + " ".join(f"{k} {v:.1e}" for k, v in last.items()) if last else ""
        )
        hub.update(job_id, state="running", percent=snap["percent"], cycle=int(snap["iteration"]), message=msg)

    adapter = OpenFoamAdapter()
    try:
        handle = adapter.submit(InputArtifact(path=Path(meta["case_dir"]), kind="directory"), progress_cb=_cb)
        res = adapter.parse_results(handle)
        meta["status"] = "solved"
        meta["message"] = (
            f"{app} bitti · {int(res.scalars.get('iterations', 0))} iterasyon · "
            + ("yakınsadı" if res.scalars.get("converged") else "iterasyon sınırına ulaştı")
        )
        meta["solver_ran"] = True
        meta["scalars"] = res.scalars
        meta["curves"] = res.curves
        meta["diagnostics"] = res.diagnostics
        _write_job(meta)
        hub.update(job_id, state="done", percent=100.0, message=meta["message"])
    except Exception as exc:  # noqa: BLE001 — arka plan işi isteği düşürmesin
        logger.warning("cfd job başarısız job_id=%s: %s", job_id, exc)
        log_path = Path(meta["case_dir"]) / f"log.{app}"
        if log_path.is_file():
            from app.solvers.openfoam import parse_solver_log

            partial = residual_result(parse_solver_log(log_path.read_text(encoding="utf-8", errors="replace")))
            meta["curves"] = partial.curves
        meta["status"] = "failed"
        meta["message"] = str(exc)
        meta["solver_ran"] = False
        _write_job(meta)
        hub.update(job_id, state="failed", message=str(exc))
    finally:
        with _live_lock:
            _live.pop(job_id, None)


@router.post("/solve")
def cfd_solve(body: CfdSolveRequest, background_tasks: BackgroundTasks) -> dict[str, Any]:
    job_id = str(uuid.uuid4())
    case_dir = _job_dir(job_id) / "case"
    try:
        OpenFoamAdapter().build_input({"output_dir": str(case_dir), "case": body.case.model_dump()})
    except SolverError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    (case_dir / "system" / "blockMeshDict").write_text(body.block_mesh_dict, encoding="utf-8", newline="\n")

    image = resolve_openfoam_image()
    meta: dict[str, Any] = {
        "job_id": job_id,
        "status": "case_only",
        "message": "case yazıldı",
        "case_dir": str(case_dir),
        "application": "simpleFoam",
        "end_iterations": body.case.control.iterations,
        "turbulence": body.case.turbulence.model,
        "openfoam_image": image,
        "solver_ran": False,
        "scalars": {},
        "curves": {},
    }
    hub = get_hub()
    hub.create(job_id)
    result: dict[str, Any] = {
        "job_id": job_id,
        "progress_url": f"/cfd/jobs/{job_id}",
        "ws_url": f"/cfd/jobs/{job_id}/ws",
        "case_url": f"/files/cfd/{job_id}/case",
        "openfoam_available": image is not None,
    }

    if not body.run_solver:
        _write_job(meta)
        hub.update(job_id, state="done", percent=0.0, message="case_only")
        return {**result, "status": meta["status"], "message": meta["message"]}
    if image is None:
        meta["status"] = "failed"
        meta["message"] = "OpenFOAM yapılandırılmamış (OPENFOAM_DOCKER_IMAGE)"
        _write_job(meta)
        hub.update(job_id, state="failed", message=meta["message"])
        return {**result, "status": meta["status"], "message": meta["message"]}

    meta["status"] = "pending"
    meta["message"] = "simpleFoam kuyrukta"
    _write_job(meta)
    hub.update(job_id, state="running", percent=0.0, message=meta["message"])
    if body.wait:
        _complete_cfd_job(job_id)
        done = _read_job(job_id) or meta
        return {**result, "status": done.get("status"), "message": done.get("message"), "scalars": done.get("scalars") or {}}
    background_tasks.add_task(_complete_cfd_job, job_id)
    return {**result, "status": "pending", "message": meta["message"]}


@router.get("/jobs/{job_id}")
def cfd_job_snapshot(job_id: str) -> dict[str, Any]:
    disk = _read_job(job_id)
    live_hub = get_hub().get(job_id)
    if disk is None and live_hub is None:
        raise HTTPException(status_code=404, detail="cfd job yok")
    out: dict[str, Any] = dict(disk or {})
    if live_hub is not None:
        out["percent"] = live_hub.percent
        out["iteration"] = live_hub.cycle
        out["hub_state"] = live_hub.state
        out["live_message"] = live_hub.message
    with _live_lock:
        live = _live.get(job_id)
    if live is not None:
        out["curves"] = {"iteration": live["iterations"], "residuals": live["residuals"]}
    return out


@router.websocket("/jobs/{job_id}/ws")
async def cfd_job_ws(websocket: WebSocket, job_id: str) -> None:
    hub = get_hub()
    if hub.get(job_id) is None:
        disk = _read_job(job_id)
        if disk is None:
            await websocket.close(code=4404)
            return
        hub.create(job_id)
        status = disk.get("status")
        hub.update(
            job_id,
            state="done" if status in ("solved", "case_only") else "failed" if status == "failed" else "pending",
            percent=100.0 if status == "solved" else 0.0,
            message=str(disk.get("message") or ""),
        )
    await websocket.accept()
    try:
        while True:
            job = hub.get(job_id)
            if job is None:
                break
            payload = job.to_dict()
            payload["kind"] = "cfd"
            with _live_lock:
                live = _live.get(job_id)
            if live is not None:
                payload["last_residuals"] = {k: v[-1] for k, v in live["residuals"].items() if v}
            await websocket.send_json(payload)
            if job.state in ("done", "failed"):
                break
            await hub.wait(job_id, timeout=1.0)
    except WebSocketDisconnect:
        return
