"""CFD (OpenFOAM) koşu API'si — Faz 2.2.

POST /cfd/solve    case parametreleri + mesh (kanal | blockMeshDict) → iş klasörü, arka planda koşu
GET  /cfd/jobs/{id} job.json + canlı residual geçmişi (+ kanal: Poiseuille karşılaştırması)
WS   /cfd/jobs/{id}/ws  ilerleme (iterasyon, yüzde, son residual'lar)

Durability `/solve` ve crash yollarına dokunulmaz. Koşu kaydı (DB, `cfd_runs`)
2.4'te ayrı onayla; şimdilik iş durumu `uploads/cfd/<job_id>/job.json`.
Mesh: parametrik kanal (2.3, ``channel``) ya da ham ``blockMeshDict`` metni;
STEP → snappyHexMesh 2.5'te.
"""

from __future__ import annotations

import json
import logging
import shutil
import threading
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, model_validator

from sqlalchemy.orm import Session

from app.api.cfd_mesh import mesh_dir, read_mesh_meta
from app.api.cfd_runs import record_from_meta
from app.db.session import SessionLocal, get_db
from app.jobs.progress import get_hub
from app.mesh.cfd_blockmesh import ChannelMeshParams, channel_block_mesh_dict, poiseuille_reference
from app.solvers.base import InputArtifact, SolverError
from app.solvers.openfoam import OpenFoamAdapter, SolverLog, residual_result, resolve_openfoam_image
from app.solvers.openfoam_case import CfdCaseParams

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cfd", tags=["cfd"])

CFD_DIR = Path("uploads") / "cfd"

# job_id → canlı residual geçmişi (ws / GET için; iş bitince job.json'a yazılır)
_live_lock = threading.Lock()
_live: dict[str, dict[str, Any]] = {}


class RocketRun(BaseModel):
    """Roket rüzgâr tüneli koşusu (R3) — ``/cfd/rocket/solve`` doldurur; koşu sonunda
    kuvvet/momentten CN, CA, CD, CL, Cm, x_cp hesaplanır (``rocket_aero``)."""

    speed_m_s: float = Field(gt=0)
    alpha_deg: float
    diameter_m: float = Field(gt=0)
    x_ref_m: float
    cg_given: bool = False
    mach: float | None = None
    barrowman: dict[str, Any] | None = None


class CfdSolveRequest(BaseModel):
    case: CfdCaseParams
    #: Koşu adı (geçmiş listesinde) ve isteğe bağlı geometri bağı.
    name: str | None = Field(None, max_length=200)
    geometry_id: int | None = None
    #: Mesh — üçünden biri: parametrik kanal (2.3), ham blockMeshDict metni ya da
    #: /cfd/mesh ile üretilmiş ağ (2.5, ``mesh_id``). Yama adları case.patches ile
    #: aynı olmalı (kanal: inlet, outlet, walls, frontAndBack; tünel: mesh yama listesi).
    channel: ChannelMeshParams | None = None
    block_mesh_dict: str | None = Field(None, min_length=1)
    mesh_id: str | None = None
    run_solver: bool = True
    #: True: istek koşu bitene kadar bekler (test / betik). False: arka plan.
    wait: bool = False
    #: Roket koşusu bilgisi (R3; ``/cfd/rocket/solve`` doldurur).
    rocket: RocketRun | None = None

    @model_validator(mode="after")
    def _one_mesh(self) -> "CfdSolveRequest":
        if sum(x is not None for x in (self.channel, self.block_mesh_dict, self.mesh_id)) != 1:
            raise ValueError("Mesh için 'channel', 'block_mesh_dict' ya da 'mesh_id' alanlarından tam biri verilmeli.")
        if self.channel is not None:
            mesh_patches = {"inlet", "outlet", "walls", "frontAndBack"}
            extra = sorted({p.name for p in self.case.patches} - mesh_patches)
            if extra:
                raise ValueError(
                    f"Kanal mesh'inde olmayan yama: {', '.join(extra)} (kanal: {', '.join(sorted(mesh_patches))})"
                )
        return self


def auto_visualization(mesh_meta: dict[str, Any], body_patches: list[str]) -> dict[str, Any]:
    """2.8: tünel mesh'i için varsayılan görselleştirme — gövde yamaları, gövde
    merkezinden geçen y-kesiti, gövdenin önünde 5 × 5 akım çizgisi tohumu."""
    bb = (mesh_meta.get("surface") or {}).get("bbox_m") or [0, 0, 0, 0, 0, 0]
    xmin, ymin, zmin, xmax, ymax, zmax = bb
    length = max(xmax - xmin, 1e-6)
    cy, cz = (ymin + ymax) / 2, (zmin + zmax) / 2
    hy, hz = max((ymax - ymin) * 0.6, 0.05 * length), max((zmax - zmin) * 0.6, 0.05 * length)
    x0 = xmin - 0.05 * length
    seeds = [[x0, cy + hy * (i - 2) / 2, cz + hz * (j - 2) / 2] for i in range(5) for j in range(5)]
    return {
        "surface_patches": body_patches,
        "slice_point": [(xmin + xmax) / 2, cy, cz],
        "slice_normal": [0.0, 1.0, 0.0],
        "streamline_seeds": seeds,
    }


def _viz_ref(case: CfdCaseParams) -> dict[str, Any]:
    """Cp için serbest akım değerleri: |U| giriş / serbest akım yamasından."""
    u = next((p.velocity_m_s for p in case.patches if p.kind in ("inlet", "farfield") and p.velocity_m_s), (0.0, 0.0, 0.0))
    comp = case.is_compressible
    return {
        "u_ref": (u[0] ** 2 + u[1] ** 2 + u[2] ** 2) ** 0.5,
        "p_ref": case.compressible.p_inf_pa if comp else 0.0,
        "rho_ref": case.rho_kg_m3,
        "compressible": comp,
    }


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


def _channel_reference(body: CfdSolveRequest) -> dict[str, Any] | None:
    """Laminer kanal → Poiseuille analitik değerleri (veri; karşılaştırma koşu sonunda)."""
    if body.channel is None or body.case.turbulence.model != "laminar":
        return None
    inlet = next((p for p in body.case.patches if p.kind == "inlet"), None)
    if inlet is None or inlet.velocity_m_s is None:
        return None
    ref = poiseuille_reference(body.channel, float(inlet.velocity_m_s[0]), body.case.nu_m2_s)
    return {"kind": "poiseuille_2d", "analytic": ref}


def _compare_reference(meta: dict[str, Any], scalars: dict[str, float]) -> None:
    ref = meta.get("reference")
    if not ref:
        return
    a = ref["analytic"]
    cfd: dict[str, float] = {}
    if "dp_kinematic" in scalars:
        cfd["dp_kinematic"] = scalars["dp_kinematic"]
    if "u_max" in scalars:
        cfd["u_max_m_s"] = scalars["u_max"]
    ref["cfd"] = cfd
    ref["diff_percent"] = {k: 100.0 * (v - a[k]) / a[k] for k, v in cfd.items() if a.get(k)}


def _sync_run(meta: dict[str, Any]) -> None:
    """job.json durumunu cfd_runs'a yansıt (arka plan işi kendi oturumuyla)."""
    db = SessionLocal()
    try:
        record_from_meta(db, meta)
    except Exception as exc:  # noqa: BLE001 — kayıt hatası çözümü düşürmesin
        logger.warning("cfd_runs güncellenemedi job_id=%s: %s", meta.get("job_id"), exc)
        db.rollback()
    finally:
        db.close()


def _rocket_results(meta: dict[str, Any], scalars: dict[str, float]) -> None:
    """R3: roket koşusunda katsayılar + Barrowman ile yan yana (veri)."""
    rk = meta.get("rocket")
    if not rk:
        return
    from app.postprocess.rocket_aero import rocket_aero

    aero = rocket_aero(
        scalars,
        speed_m_s=rk["speed_m_s"],
        alpha_deg=rk["alpha_deg"],
        rho_kg_m3=float(meta.get("rho_kg_m3") or 1.0),
        diameter_m=rk["diameter_m"],
        x_ref_m=rk["x_ref_m"],
        cg_given=bool(rk.get("cg_given")),
    )
    b = rk.get("barrowman")
    if aero and b:
        cmp: dict[str, Any] = {"cn_alpha_barrowman": b["cn_alpha"], "x_cp_barrowman_m": b["x_cp_mm"] / 1000.0}
        if "CN_alpha_per_rad" in aero:
            cmp["cn_alpha_diff_percent"] = 100.0 * (aero["CN_alpha_per_rad"] - b["cn_alpha"]) / b["cn_alpha"]
        if "x_cp_m" in aero:
            cmp["x_cp_diff_calibers"] = (aero["x_cp_m"] - b["x_cp_mm"] / 1000.0) / rk["diameter_m"]
        aero["barrowman"] = cmp
    meta["rocket_aero"] = aero


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
        forces = meta.get("forces") or {}
        handle._average_last = int(forces.get("average_last") or 50)  # type: ignore[attr-defined]
        res = adapter.parse_results(handle)
        a_ref = forces.get("a_ref_m2")
        if a_ref and "Cd" in res.scalars:
            res.scalars["CdA_m2"] = res.scalars["Cd"] * float(a_ref)
            res.scalars["CdA_mean_m2"] = res.scalars["Cd_mean"] * float(a_ref)
        meta["status"] = "solved"
        meta["message"] = (
            f"{app} bitti · {int(res.scalars.get('iterations', 0))} iterasyon · "
            + ("yakınsadı" if res.scalars.get("converged") else "iterasyon sınırına ulaştı")
        )
        meta["solver_ran"] = True
        rho = float(meta.get("rho_kg_m3") or 1.0)
        if "p_avg_inlet" in res.scalars and "p_avg_outlet" in res.scalars:
            dp = res.scalars["p_avg_inlet"] - res.scalars["p_avg_outlet"]
            if meta.get("application", "simpleFoam") == "simpleFoam":
                res.scalars["dp_kinematic"] = dp
                res.scalars["dp_pa"] = rho * dp
            else:  # sıkıştırılabilir: p mutlak (Pa)
                res.scalars["dp_pa"] = dp
        meta["scalars"] = res.scalars
        meta["curves"] = res.curves
        meta["diagnostics"] = res.diagnostics
        _compare_reference(meta, res.scalars)
        _rocket_results(meta, res.scalars)
        _write_job(meta)
        _sync_run(meta)
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
        _sync_run(meta)
        hub.update(job_id, state="failed", message=str(exc))
    finally:
        with _live_lock:
            _live.pop(job_id, None)


@router.post("/solve")
def cfd_solve(
    body: CfdSolveRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
) -> dict[str, Any]:
    job_id = str(uuid.uuid4())
    case_dir = _job_dir(job_id) / "case"
    mesh_meta: dict[str, Any] | None = None
    if body.mesh_id is not None:
        mesh_meta = read_mesh_meta(body.mesh_id)
        if mesh_meta is None or mesh_meta.get("status") != "meshed":
            raise HTTPException(status_code=422, detail=f"Mesh hazır değil ya da yok: {body.mesh_id}")
        extra = sorted({p.name for p in body.case.patches} - set(mesh_meta.get("patches") or []))
        if extra:
            raise HTTPException(
                status_code=422,
                detail=f"Mesh'te olmayan yama: {', '.join(extra)} (mesh: {', '.join(mesh_meta.get('patches') or [])})",
            )
    if mesh_meta is not None and body.case.visualization is None:
        tunnel_names = {"inlet", "outlet", "sides", "ground"}
        walls = [p.name for p in body.case.patches if p.kind == "wall" and p.name not in tunnel_names]
        body.case.visualization = CfdCaseParams.model_validate(
            {**body.case.model_dump(), "visualization": auto_visualization(mesh_meta, walls)}
        ).visualization
    try:
        OpenFoamAdapter().build_input({"output_dir": str(case_dir), "case": body.case.model_dump()})
    except SolverError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if mesh_meta is not None:
        src = mesh_dir(body.mesh_id or "") / "case" / "constant" / "polyMesh"
        shutil.copytree(src, case_dir / "constant" / "polyMesh", dirs_exist_ok=True)
    else:
        bmd = channel_block_mesh_dict(body.channel) if body.channel is not None else body.block_mesh_dict
        (case_dir / "system" / "blockMeshDict").write_text(bmd or "", encoding="utf-8", newline="\n")

    image = resolve_openfoam_image()
    meta: dict[str, Any] = {
        "job_id": job_id,
        "name": body.name,
        "geometry_id": body.geometry_id if body.geometry_id is not None else (mesh_meta or {}).get("geometry_id"),
        "case": body.case.model_dump(),
        "status": "case_only",
        "message": "case yazıldı",
        "case_dir": str(case_dir),
        "application": body.case.solver,
        "end_iterations": body.case.control.iterations,
        "turbulence": body.case.turbulence.model,
        "rho_kg_m3": body.case.rho_kg_m3,
        "viz_ref": _viz_ref(body.case) if body.case.visualization is not None else None,
        "forces": body.case.forces.model_dump() if body.case.forces is not None else None,
        "mesh": {"kind": "channel", **body.channel.model_dump(), "cells": body.channel.cell_count}
        if body.channel is not None
        else {
            "kind": mesh_meta.get("mesher") or "snappy",
            "mesh_id": body.mesh_id,
            "cells": (mesh_meta.get("check") or {}).get("cells"),
            "tunnel": mesh_meta.get("tunnel"),
        }
        if mesh_meta is not None
        else {"kind": "block_mesh_dict"},
        "reference": _channel_reference(body),
        "rocket": body.rocket.model_dump() if body.rocket is not None else None,
        "openfoam_image": image,
        "solver_ran": False,
        "scalars": {},
        "curves": {},
    }
    hub = get_hub()
    hub.create(job_id)

    def save() -> None:
        _write_job(meta)
        run = record_from_meta(db, meta)
        result["run_id"] = run.id

    result: dict[str, Any] = {
        "job_id": job_id,
        "progress_url": f"/cfd/jobs/{job_id}",
        "ws_url": f"/cfd/jobs/{job_id}/ws",
        "case_url": f"/files/cfd/{job_id}/case",
        "openfoam_available": image is not None,
    }

    if not body.run_solver:
        save()
        hub.update(job_id, state="done", percent=0.0, message="case_only")
        return {**result, "status": meta["status"], "message": meta["message"]}
    if image is None:
        meta["status"] = "failed"
        meta["message"] = "OpenFOAM yapılandırılmamış (OPENFOAM_DOCKER_IMAGE)"
        save()
        hub.update(job_id, state="failed", message=meta["message"])
        return {**result, "status": meta["status"], "message": meta["message"]}

    meta["status"] = "pending"
    meta["message"] = f"{body.case.solver} kuyrukta"
    save()
    hub.update(job_id, state="running", percent=0.0, message=meta["message"])
    if body.wait:
        _complete_cfd_job(job_id)
        done = _read_job(job_id) or meta
        return {
            **result,
            "status": done.get("status"),
            "message": done.get("message"),
            "scalars": done.get("scalars") or {},
            "reference": done.get("reference"),
            "rocket_aero": done.get("rocket_aero"),
        }
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


@router.get("/jobs/{job_id}/fields")
def cfd_job_fields(job_id: str) -> dict[str, Any]:
    """2.8: yüzey Cp, kesit |U|, akım çizgileri (koşu sonunda yazılan çıktılardan)."""
    meta = _read_job(job_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="cfd job yok")
    ref = meta.get("viz_ref")
    if not ref or meta.get("status") != "solved":
        raise HTTPException(status_code=404, detail="Bu koşuda alan görselleştirme çıktısı yok.")
    cache = _job_dir(job_id) / "fields.json"
    if cache.is_file():
        return json.loads(cache.read_text(encoding="utf-8"))
    from app.postprocess.openfoam_viz import build_fields

    data = build_fields(Path(meta["case_dir"]), **ref)
    if "body" not in data and "slice" not in data:
        raise HTTPException(status_code=404, detail="Alan çıktısı bulunamadı (postProcessing/vizSurfaces).")
    cache.write_text(json.dumps(data), encoding="utf-8")
    return data


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
