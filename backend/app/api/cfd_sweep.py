"""Roket Mach × α taraması — R5.

``POST /cfd/rocket/sweep``: Mach listesi × α listesi; her nokta bir R3 koşusu
(``rocket_solve``, sıralı, aynı mesh, aynı çözücü — çözücü mühendisin seçimi,
Mach'a göre otomatik değişmez). Hız = M · √(γ·R·T). Durum dosyası
``uploads/cfd_sweeps/<id>/sweep.json`` her noktadan sonra yazılır.
``GET /cfd/rocket/sweep/{id}``: noktalar + Mach başına tablo.
``GET /cfd/rocket/sweep/{id}/csv?kind=table|points``: CSV dışa aktarım.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import Field

from app.api.cfd_rocket import RocketSolveRequest, rocket_solve
from app.db.session import SessionLocal
from app.postprocess.rocket_aero import speed_of_sound
from app.postprocess.rocket_table import POINT_COLUMNS, TABLE_COLUMNS, aero_table, to_csv

router = APIRouter(prefix="/cfd/rocket", tags=["cfd"])

SWEEP_DIR = Path("uploads") / "cfd_sweeps"
_lock = threading.Lock()


class RocketSweepRequest(RocketSolveRequest):
    """R3 alanları (hız / α hariç) + tarama listeleri."""

    speed_m_s: float = Field(1.0, gt=0)  # kullanılmaz; hız Mach'tan
    machs: list[float] = Field(min_length=1, max_length=20)
    alphas_deg: list[float] = Field(min_length=1, max_length=20)


def _path(sweep_id: str) -> Path:
    return SWEEP_DIR / sweep_id / "sweep.json"


def _write(sweep_id: str, data: dict[str, Any]) -> None:
    p = _path(sweep_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        p.write_text(json.dumps(data, indent=1), encoding="utf-8")


def read_sweep(sweep_id: str) -> dict[str, Any] | None:
    p = _path(sweep_id)
    if not p.is_file():
        return None
    with _lock:
        return json.loads(p.read_text(encoding="utf-8"))


def _point_result(out: dict[str, Any]) -> dict[str, Any]:
    a = out.get("rocket_aero") or {}
    return {
        "status": out.get("status"),
        "message": out.get("message"),
        "job_id": out.get("job_id"),
        **{k: a.get(k) for k in ("CA", "CN", "CD", "CL", "Cm", "x_cp_m", "stability_calibers")},
    }


def run_sweep(sweep_id: str, body: RocketSweepRequest) -> None:
    data = read_sweep(sweep_id) or {}
    a_snd = speed_of_sound(body.temperature_k)
    base = body.model_dump(exclude={"machs", "alphas_deg", "speed_m_s", "alpha_deg", "wait", "name"})
    data["status"] = "running"
    _write(sweep_id, data)
    for pt in data["points"]:
        pt["status"] = "running"
        _write(sweep_id, data)
        req = RocketSolveRequest(
            **base,
            speed_m_s=pt["speed_m_s"],
            alpha_deg=pt["alpha_deg"],
            wait=True,
            name=f"{body.name or 'R5'} M{pt['mach']:g} α{pt['alpha_deg']:g}",
        )
        db = SessionLocal()
        try:
            pt.update(_point_result(rocket_solve(req, BackgroundTasks(), db)))
        except HTTPException as e:
            pt.update({"status": "failed", "message": str(e.detail)})
        except Exception as e:  # noqa: BLE001 — nokta hatası taramayı durdurmaz
            pt.update({"status": "failed", "message": f"{type(e).__name__}: {e}"})
        finally:
            db.close()
        data["table"] = aero_table(data["points"])
        _write(sweep_id, data)
    done = sum(1 for p in data["points"] if p.get("status") == "solved")
    data["status"] = "done"
    data["message"] = f"{done}/{len(data['points'])} nokta çözüldü · a = {a_snd:.1f} m/s"
    _write(sweep_id, data)


@router.post("/sweep")
def rocket_sweep(body: RocketSweepRequest, background_tasks: BackgroundTasks) -> dict[str, Any]:
    sweep_id = str(uuid.uuid4())
    a_snd = speed_of_sound(body.temperature_k)
    points = [
        {"mach": m, "alpha_deg": al, "speed_m_s": m * a_snd, "status": "pending"}
        for m in body.machs
        for al in body.alphas_deg
    ]
    data = {
        "sweep_id": sweep_id,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "solver": body.solver,
        "mesh_id": body.mesh_id,
        "name": body.name,
        "request": body.model_dump(),
        "points": points,
        "table": [],
    }
    _write(sweep_id, data)
    if body.wait:
        run_sweep(sweep_id, body)
    else:
        background_tasks.add_task(run_sweep, sweep_id, body)
    return read_sweep(sweep_id) or data


@router.get("/sweep/{sweep_id}")
def rocket_sweep_get(sweep_id: str) -> dict[str, Any]:
    data = read_sweep(sweep_id)
    if data is None:
        raise HTTPException(status_code=404, detail="tarama yok")
    return data


@router.get("/sweep/{sweep_id}/csv", response_class=PlainTextResponse)
def rocket_sweep_csv(sweep_id: str, kind: Literal["table", "points"] = "table") -> PlainTextResponse:
    data = read_sweep(sweep_id)
    if data is None:
        raise HTTPException(status_code=404, detail="tarama yok")
    if kind == "table":
        text = to_csv(data.get("table") or [], TABLE_COLUMNS)
    else:
        text = to_csv(data["points"], POINT_COLUMNS)
    return PlainTextResponse(
        text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="rocket_{kind}_{sweep_id[:8]}.csv"'},
    )
