"""MBD (Project Chrono) koşu API'si — Faz 5.2a.

POST /mbd/solve       çeyrek araç parametreleri → ChronoAdapter, sonuç döner
GET  /mbd/jobs/{id}   aynı iş klasöründen skalerler ve eğriler

DB yok. İş klasörü ``uploads/chrono_jobs/<id>``. Durability ``/solve``, crash ve
CFD yollarına dokunulmaz. PyChrono bu süreçte import edilmez.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from app.solvers.base import InputArtifact, JobHandle, SolverError
from app.solvers.chrono import RESULTS_FILE, ChronoAdapter, ChronoQuarterCarParams

router = APIRouter(prefix="/mbd", tags=["mbd"])

MBD_DIR = Path("uploads") / "chrono_jobs"
_JOB_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _adapter() -> ChronoAdapter:
    return ChronoAdapter(work_root=MBD_DIR)


def _job_dir(job_id: str) -> Path:
    if not _JOB_ID.match(job_id):
        raise HTTPException(status_code=404, detail="Koşu bulunamadı.")
    path = MBD_DIR / job_id
    if not (path / RESULTS_FILE).is_file():
        raise HTTPException(status_code=404, detail="Koşu bulunamadı.")
    return path


def _result_body(job_id: str, work_dir: Path) -> dict[str, Any]:
    rs = _adapter().parse_results(
        JobHandle(job_id=job_id, work_dir=work_dir, artifact=InputArtifact(path=work_dir, kind="directory"))
    )
    return {
        "job_id": job_id,
        "state": "done",
        "scalars": rs.scalars,
        "curves": rs.curves,
        "diagnostics": rs.diagnostics,
    }


def _http_error(exc: SolverError) -> HTTPException:
    msg = str(exc)
    code = 503 if "yapılandırılmamış" in msg else 422
    return HTTPException(status_code=code, detail=msg)


@router.post("/solve")
def mbd_solve(body: ChronoQuarterCarParams) -> dict[str, Any]:
    """Çeyrek araç tümsek geçişi. Koşu bitene kadar bekler (saniyeler)."""
    adapter = _adapter()
    job_id = uuid.uuid4().hex[:12]
    try:
        job = adapter.submit(adapter.build_input({**body.model_dump(), "job_id": job_id}))
    except SolverError as exc:
        raise _http_error(exc) from exc
    status = adapter.poll_status(job)
    if status.state != "done":
        raise HTTPException(status_code=422, detail=status.message or "Chrono koşusu başarısız.")
    return _result_body(job_id, job.work_dir)


@router.get("/jobs/{job_id}")
def mbd_job(job_id: str) -> dict[str, Any]:
    path = _job_dir(job_id)
    try:
        return _result_body(job_id, path)
    except SolverError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
