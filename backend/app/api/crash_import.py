"""LS-DYNA keyword içe aktarma API — 1.21e-1 (`/crash/import/dyna`).

Yalnız okuma + çeviri: .k / .dyn (ve *INCLUDE dosyaları) yüklenir, ara
modelden OpenRadioss adaptör parametrelerine çevrilir, çeviri raporu
döner. Koşu başlatılmaz; parametreler `uploads/crash_import/{id}/
import.json`'a yazılır (DB şeması değişmez). Kart yazmak / çözmek
mevcut adaptörün işi.

Birim çarpanları (dosya → mm, kg, s) ve hız etkisi için ε̇ listesi
mühendisten gelir; tahmin edilmez.
"""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db

from app.importers.dyna_k import SUPPORTED_SUFFIXES, DynaParseError, read_keyword_file
from app.importers.dyna_material import DynaMaterialError, DynaUnits, to_crash_materials
from app.importers.dyna_mesh import DynaMeshError, to_crash_mesh
from app.importers.dyna_preview import surface_preview
from app.importers.dyna_setup import to_crash_setup

router = APIRouter(prefix="/crash/import", tags=["crash"])

IMPORT_DIR = Path("uploads") / "crash_import"
MAX_FILE_BYTES = 200 * 1024 * 1024


def _parse_rates(raw: str) -> list[float]:
    try:
        return [float(x) for x in raw.replace(";", ",").split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status_code=422, detail=f"ε̇ listesi okunamadı: '{raw}'") from None


async def _save(upload: UploadFile, folder: Path) -> Path:
    name = Path(upload.filename or "").name
    if not name or name in (".", ".."):
        raise HTTPException(status_code=422, detail="Dosya adı boş.")
    target = folder / name
    if target.exists():
        raise HTTPException(status_code=422, detail=f"'{name}' iki kez yüklendi.")
    data = await upload.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail=f"'{name}' 200 MB'tan büyük.")
    target.write_bytes(data)
    return target


@router.post("/dyna")
async def import_dyna(
    main: UploadFile = File(..., description=".k / .dyn / .key ana dosya"),
    includes: list[UploadFile] = File(default=[], description="*INCLUDE dosyaları"),
    length_to_mm: float = Form(..., description="Dosya uzunluk birimi → mm"),
    mass_to_kg: float = Form(..., description="Dosya kütle birimi → kg"),
    time_to_s: float = Form(..., description="Dosya zaman birimi → s"),
    rates_per_s: str = Form(default="", description="Hız etkisi için ε̇ (1/s), virgüllü; boş = yok"),
) -> dict[str, Any]:
    if Path(main.filename or "").suffix.lower() not in SUPPORTED_SUFFIXES:
        raise HTTPException(
            status_code=422, detail=f"Ana dosya uzantısı {', '.join(SUPPORTED_SUFFIXES)} olmalı."
        )
    rates = _parse_rates(rates_per_s)
    try:
        units = DynaUnits(length_to_mm, mass_to_kg, time_to_s)
    except DynaMaterialError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    import_id = uuid.uuid4().hex
    folder = IMPORT_DIR / import_id
    folder.mkdir(parents=True)
    try:
        main_path = await _save(main, folder)
        for inc in includes:
            await _save(inc, folder)
        model = read_keyword_file(main_path)
        mesh = to_crash_mesh(model, length_to_mm=units.length_to_mm)
        materials = to_crash_materials(model, mesh, units, rates_per_s=rates)
        setup = to_crash_setup(model, mesh, units)
    except (DynaParseError, DynaMeshError, DynaMaterialError) as exc:
        shutil.rmtree(folder, ignore_errors=True)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HTTPException:
        shutil.rmtree(folder, ignore_errors=True)
        raise

    params = mesh.adapter_params()
    materials.apply(params)
    setup.apply(params)
    report = {
        "import_id": import_id,
        "file": main_path.name,
        "units": {"length_to_mm": length_to_mm, "mass_to_kg": mass_to_kg, "time_to_s": time_to_s},
        "rates_per_s": sorted(set(rates)),
        "parse": model.summary(),
        "mesh": mesh.report(),
        "materials": materials.report(),
        "setup": setup.report(),
    }
    (folder / "import.json").write_text(
        json.dumps({"report": report, "params": params}), encoding="utf-8"
    )
    return report


def _load(import_id: str) -> dict[str, Any]:
    if len(import_id) != 32 or not all(c in "0123456789abcdef" for c in import_id):
        raise HTTPException(status_code=404, detail="İçe aktarma bulunamadı.")
    path = IMPORT_DIR / import_id / "import.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="İçe aktarma bulunamadı.")
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/dyna/{import_id}")
def get_import(import_id: str) -> dict[str, Any]:
    """Kayıtlı çeviri raporu (parametreler hariç; ağ boyutu büyük olabilir)."""
    return _load(import_id)["report"]


@router.get("/dyna/{import_id}/preview")
def get_preview(import_id: str) -> dict[str, Any]:
    """1.21e-2a — viewport önizlemesi: dış yüzey (mm) + yüz başına PID."""
    return surface_preview(_load(import_id)["params"])


class ImportSolveRequest(BaseModel):
    """1.21e-2c — içe aktarılan modeli koş. Kurulum dosyadan (import.json); burada yalnız ad,
    çözücü / bekleme ve (dosyada *CONTROL_TERMINATION yoksa) süre."""

    name: str | None = Field(default=None, max_length=200)
    t_end_ms: float | None = Field(default=None, gt=0, description="Dosyadaki süreyi ezer; dosyada yoksa zorunlu")
    run_solver: bool = True
    wait: bool = False


@router.post("/dyna/{import_id}/solve")
def solve_import(
    import_id: str,
    body: ImportSolveRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """1.21e-2c — import.json parametreleri → adaptör (deck) → OpenRadioss. Koşu `crash_runs`'a
    geometrisiz, `import_id` ile kaydedilir (1.21e-2b). İş akışı `/crash/solve` ile aynı (job.json,
    canlı ilerleme, arka plan / bekleme); kartları mevcut yazıcı üretir."""
    from app.api import crash as crash_api
    from app.api.crash_runs import record_from_meta
    from app.solvers.base import SolverError
    from app.solvers.openradioss import OpenRadiossAdapter, resolve_openradioss

    stored = _load(import_id)
    params: dict[str, Any] = dict(stored["params"])
    t_end = body.t_end_ms if body.t_end_ms is not None else params.get("t_end_ms")
    if t_end is None:
        raise HTTPException(status_code=422, detail="Dosyada *CONTROL_TERMINATION yok — süre (t_end_ms) girin.")
    params["t_end_ms"] = float(t_end)

    job_id = str(uuid.uuid4())
    work_dir = crash_api._job_dir(job_id)
    work_dir.mkdir(parents=True, exist_ok=True)
    try:
        artifact = OpenRadiossAdapter().build_input({**params, "output_dir": work_dir, "job_name": "crash"})
    except SolverError as exc:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    engine_path = artifact.path.with_name("crash_0001.rad")
    or_ok = resolve_openradioss() is not None
    report = stored["report"]
    meta: dict[str, Any] = {
        "job_id": job_id,
        "geometry_id": None,
        "import_id": import_id,
        "name": body.name or f"İçe aktarma · {report.get('file', import_id)}",
        "status": "rad_only",
        "message": "rad üretildi",
        "t_end_ms": float(t_end),
        "starter_path": str(artifact.path).replace("\\", "/"),
        "engine_path": str(engine_path).replace("\\", "/"),
        # İstek anlık görüntüsü: içe aktarmanın kurulumu (ağ hariç — import.json'da)
        **{k: params[k] for k in ("parts", "contacts", "use_rigid_wall", "boundary_conditions",
                                  "initial_velocities", "rigid_bodies", "gravity") if k in params},
        "dimension": params.get("dimension"),
        "solver_ran": False,
        "openradioss_available": or_ok,
        "materials": list(params.get("materials") or []),
        "scalars": {},
        "curves": {},
    }
    crash_api._write_job(meta)
    run = record_from_meta(db, meta)
    hub = crash_api.get_hub()
    hub.create(job_id)
    result: dict[str, Any] = {
        "job_id": job_id,
        "import_id": import_id,
        "run_id": run.id if run is not None else None,
        "status": meta["status"],
        "message": meta["message"],
        "starter_url": f"/files/crash/{job_id}/{artifact.path.name}",
        "engine_url": f"/files/crash/{job_id}/{engine_path.name}",
        "progress_url": f"/crash/jobs/{job_id}",
        "ws_url": f"/crash/jobs/{job_id}/ws",
        "openradioss_available": or_ok,
        "solver_ran": False,
        "scalars": {},
    }
    if not body.run_solver:
        hub.update(job_id, state="done", percent=0.0, message="rad_only")
        return result
    if not or_ok:
        err = crash_api.crash_error(5)
        meta.update(status="failed", message=crash_api.error_message(err), diagnostics={"error": err})
        crash_api._write_job(meta)
        record_from_meta(db, meta)
        hub.update(job_id, state="failed", message=meta["message"])
        return {**result, "status": "failed", "message": meta["message"], "diagnostics": meta["diagnostics"]}
    if body.wait:
        crash_api._complete_crash_job(job_id)
        done = crash_api._read_job(job_id) or meta
        return {**result, "status": done.get("status"), "message": done.get("message"),
                "solver_ran": bool(done.get("solver_ran")), "scalars": done.get("scalars") or {},
                "diagnostics": done.get("diagnostics") or {}}
    meta.update(status="pending", message="OpenRadioss çalışıyor…")
    crash_api._write_job(meta)
    record_from_meta(db, meta)
    hub.update(job_id, state="running", percent=0.0, message=meta["message"])
    background_tasks.add_task(crash_api._complete_crash_job, job_id)
    return {**result, "status": "pending", "message": meta["message"]}
