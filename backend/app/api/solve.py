"""CalculiX solve API — .inp üret + isteğe bağlı ccx çalıştır."""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload

from app.api.geometry import MESH_DIR, TESSELLATION_DIR, UPLOAD_DIR, _get_geometry_or_404
from app.db.session import SessionLocal, get_db
from app.models.material import MaterialAssignment
from app.models.run import AnalysisRun
from app.postprocess.fatigue import compute_safety_factor, estimate_fatigue_life
from app.postprocess.report import build_run_report_pdf
from app.solvers.base import InputArtifact, SolverError
from app.solvers.calculix import CalculiXAdapter, _ccx_executable

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/geometry", tags=["solve"])

RUNS_DIR = Path("uploads") / "runs"


def _attach_fatigue_and_sf(
    scalars: dict[str, Any],
    assignments: list[Any],
    analysis_type: str,
    results_preview_path: Path | None,
) -> tuple[dict[str, Any], str | None, bool]:
    fatigue_note = None
    fatigue_runout = False
    max_vm = scalars.get("max_von_mises")
    if analysis_type == "modal" or max_vm is None or not assignments:
        return scalars, fatigue_note, fatigue_runout
    worst = min(assignments, key=lambda a: a.material.yield_strength)
    yield_mpa = worst.material.yield_strength / 1e6
    sf = compute_safety_factor(max_vm, yield_mpa)
    if sf is not None:
        scalars["safety_factor"] = sf
    sn_curve = worst.material.sn_curve
    if sn_curve and sn_curve.get("points"):
        points_mpa = [
            {"N": p["N"], "sigma": p["sigma"] / 1e6} for p in sn_curve["points"]
        ]
        fatigue = estimate_fatigue_life(max_vm, points_mpa)
        if fatigue.get("cycles") is not None:
            scalars["fatigue_life_cycles"] = fatigue["cycles"]
            fatigue_note = fatigue.get("note")
            fatigue_runout = bool(fatigue.get("runout", False))
    if results_preview_path and results_preview_path.exists():
        data = json.loads(results_preview_path.read_text(encoding="utf-8"))
        vm = data.get("von_mises") or []
        data["yield_mpa"] = yield_mpa
        data["safety_factor"] = [
            (yield_mpa / v) if v is not None and v > 1e-30 else None for v in vm
        ]
        results_preview_path.write_text(
            json.dumps(data, separators=(",", ":")), encoding="utf-8"
        )
    return scalars, fatigue_note, fatigue_runout


def _complete_ccx_job(run_id: int) -> None:
    db = SessionLocal()
    run = None
    try:
        run = db.get(AnalysisRun, run_id)
        if run is None or not run.inp_path:
            return
        analysis_type = str((run.scalars or {}).get("_analysis_type") or "static")
        adapter = CalculiXAdapter()
        handle = adapter.submit(InputArtifact(path=Path(run.inp_path)))
        status = adapter.poll_status(handle)
        parsed = adapter.parse_results(handle)
        assignments = (
            db.query(MaterialAssignment)
            .options(joinedload(MaterialAssignment.material))
            .filter(MaterialAssignment.geometry_id == run.geometry_id)
            .all()
        )
        scalars = dict(parsed.scalars or {})
        scalars["_analysis_type"] = analysis_type
        scalars, _note, _runout = _attach_fatigue_and_sf(
            scalars,
            assignments,
            analysis_type,
            parsed.results_preview_path,
        )
        run.status = "solved"
        run.message = f"ccx bitti ({status.state})"
        run.scalars = scalars
        run.frd_path = (
            str(parsed.raw_result_path).replace("\\", "/")
            if parsed.raw_result_path
            else None
        )
        run.results_preview_path = (
            str(parsed.results_preview_path).replace("\\", "/")
            if parsed.results_preview_path
            else None
        )
        db.commit()
    except Exception as exc:  # noqa: BLE001 — arka plan işi isteği düşürmesin
        logger.warning("ccx job başarısız run_id=%s: %s", run_id, exc)
        if run is not None:
            run.status = "failed"
            run.message = str(exc)
            db.commit()
    finally:
        db.close()


class SolveBC(BaseModel):
    type: str
    face_ids: list[int] | None = None
    edge_ids: list[int] | None = None
    node_ids: list[int] | None = None
    fx: float | None = None
    fy: float | None = None
    fz: float | None = None
    magnitude: float | None = None
    dx: float | None = None
    dy: float | None = None
    dz: float | None = None
    gx: float | None = None
    gy: float | None = None
    gz: float | None = None
    dofs: dict[str, float] | None = None
    axis: list[float] | None = None
    normal: list[float] | None = None
    ref_node_id: int | None = None


class SolveRequest(BaseModel):
    dimension: int = Field(..., description="2 | 3")
    shell_thickness: float = Field(default=3.0, gt=0)
    run_solver: bool = Field(
        default=False,
        description="True ise ccx çalıştırılır (kurulu olmalı)",
    )
    bcs: list[SolveBC] = Field(default_factory=list)
    # Kullanıcının bu çözüme verdiği isteğe bağlı etiket (history'de görünür).
    name: str | None = Field(default=None)
    # Düzenle akışında geri yüklemek için — yoksa DB'de null kalır.
    element_size: float | None = Field(default=None)
    element_scheme: str | None = Field(default=None)
    analysis_type: str = Field(default="static", description="static | modal")
    n_modes: int | None = Field(default=None, ge=1, le=200)
    freq_min: float | None = Field(default=None)
    freq_max: float | None = Field(default=None)
    wait: bool = Field(
        default=True,
        description="False ve run_solver ise ccx arka planda; yanıt hemen pending döner.",
    )


@router.post("/{geometry_id}/solve")
def solve_geometry(
    geometry_id: int,
    body: SolveRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Mesh + malzeme atamalarından CalculiX .inp üretir; isteğe bağlı ccx."""
    if body.dimension not in (2, 3):
        raise HTTPException(status_code=400, detail="dimension 2 veya 3 olmalı.")

    geo = _get_geometry_or_404(db, geometry_id)
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
        .filter(MaterialAssignment.geometry_id == geometry_id)
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
        }
        for a in assignments
    ]

    bcs = [bc.model_dump(exclude_none=True) for bc in body.bcs]
    # KRİTİK: eskiden bcs boşsa sessizce `face_ids=[]` ile bir "fixed" BC
    # (aslında hiçbir düğümü sabitlemeyen, no-op) + gravity kullanılıyordu.
    # Bu, cismi hiçbir yerde sabitlemeden yerçekimine bırakıyordu — rijit
    # cisim hareketi (singular stiffness matrix), sayısal olarak anlamsız
    # dev sonuçlar üretiyordu (gerçek bir testte doğrulandı:
    # max_displacement=87709030867 mm gibi). Artık sessizce "çalışıyormuş
    # gibi" davranmak yerine net bir hata döndürüyoruz — mühendis en az
    # bir yer değiştirme kısıtı (Fixed/Displacement/Sliding) eklemeden
    # çözüm yapılamaz.
    if not bcs:
        raise HTTPException(
            status_code=422,
            detail=(
                "En az bir sınır koşulu (BC) eklemeden çözülemez. "
                "BC olmadan (özellikle bir Fixed support olmadan) model "
                "boşlukta serbestçe hareket eder — rijit cisim hareketi "
                "(anlamsız, aşırı büyük deplasman) üretir."
            ),
        )
    has_constraint = any(
        bc.get("type") in ("fixed", "displacement", "sliding") for bc in bcs
    )
    if not has_constraint:
        raise HTTPException(
            status_code=422,
            detail=(
                "En az bir yer değiştirme kısıtlayan BC gerekli "
                "(Fixed / Displacement / Sliding). Sadece yük (Force / "
                "Pressure / Gravity) ile model boşlukta asılı kalır — "
                "rijit cisim hareketi oluşur, sonuçlar anlamsız çıkar."
            ),
        )

    # ÖNCE kalıcı bir AnalysisRun satırı oluşturulur (status="pending") —
    # bu, ROADMAP.md "7. Veritabanına kayıt + geçmiş" gereksinimi: her
    # çözüm (başarılı ya da başarısız) SİLİNMEDEN kaydedilir, Faz 4'teki
    # surrogate model eğitimi için veri kaynağı olacak. run.id, dosya
    # adlandırması için de kullanılıyor — eskiden `geo{id}_d{dim}` idi ve
    # aynı geometride ikinci bir case çözünce öncekinin dosyalarının üzerine
    # yazıyordu; artık her run kendi klasöründe (`uploads/runs/{run_id}/`)
    # bağımsız yaşıyor.
    analysis_type = (body.analysis_type or "static").lower()
    if analysis_type not in ("static", "modal"):
        raise HTTPException(status_code=400, detail="analysis_type static veya modal olmalı.")
    n_modes = body.n_modes if body.n_modes is not None else 10
    run_name = body.name
    if analysis_type == "modal" and not (run_name and run_name.strip()):
        run_name = f"Modal · {n_modes} mod"

    run = AnalysisRun(
        geometry_id=geometry_id,
        name=run_name,
        dimension=body.dimension,
        element_size=body.element_size,
        element_scheme=body.element_scheme,
        shell_thickness=body.shell_thickness,
        bcs=bcs,
        materials_snapshot=materials,
        status="pending",
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    run_dir = RUNS_DIR / str(run.id)
    run_dir.mkdir(parents=True, exist_ok=True)
    job_name = f"run{run.id}"

    # Bu run'ın kendi mesh önizlemesinin anlık görüntüsü — aynı geometride
    # sonraki bir case'in mesh'i yeniden üretilse bile bu run etkilenmesin.
    mesh_preview_src = MESH_DIR / f"{stem}_d{body.dimension}.preview.json"
    mesh_preview_snapshot_path: str | None = None
    if mesh_preview_src.exists():
        mesh_preview_dst = run_dir / "mesh_preview.json"
        mesh_preview_dst.write_bytes(mesh_preview_src.read_bytes())
        mesh_preview_snapshot_path = str(mesh_preview_dst).replace("\\", "/")
        run.mesh_preview_path = mesh_preview_snapshot_path

    # Bu run'ın kendi CAD tessellation'ının (STL) anlık görüntüsü — geometri
    # bu run'dan SONRA mutasyona uğrarsa (heal/defeature/offset/midsurface)
    # canlı STL artık FARKLI bir durumu gösterir. Karşılaştırma/geçmiş
    # görünümü HER ZAMAN bu anlık görüntüyü kullanmalı (gerçek bir ekran
    # görüntüsünde "sonuçlar geometriden kaymış" diye tespit edilen hatanın
    # kök nedeni buydu).
    tessellation_src = TESSELLATION_DIR / f"{geometry_id}.stl"
    if tessellation_src.exists():
        tessellation_dst = run_dir / "tessellation.stl"
        tessellation_dst.write_bytes(tessellation_src.read_bytes())
        run.tessellation_snapshot_path = str(tessellation_dst).replace("\\", "/")

    adapter = CalculiXAdapter()
    try:
        artifact = adapter.build_input(
            {
                "mesh_path": mesh_path,
                "dimension": body.dimension,
                "output_dir": run_dir,
                "job_name": job_name,
                "materials": materials,
                "shell_thickness": body.shell_thickness,
                "bcs": bcs,
                "analysis_type": analysis_type,
                "n_modes": n_modes,
                "freq_min": body.freq_min,
                "freq_max": body.freq_max,
            }
        )
    except SolverError as exc:
        run.status = "failed"
        run.message = str(exc)
        db.commit()
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    inp_text = artifact.path.read_text(encoding="utf-8")
    cards_ok = {
        "has_material": "*MATERIAL" in inp_text,
        "has_elastic": "*ELASTIC" in inp_text,
        "has_density": "*DENSITY" in inp_text,
        "has_section": ("*SOLID SECTION" in inp_text) or ("*SHELL SECTION" in inp_text),
        "has_step": "*STEP" in inp_text,
    }

    run.inp_path = str(artifact.path).replace("\\", "/")
    run.status = "inp_only"
    run.message = "modal inp üretildi" if analysis_type == "modal" else "inp üretildi"
    run.scalars = {"_analysis_type": analysis_type}
    db.commit()

    result: dict[str, Any] = {
        "geometry_id": geometry_id,
        "run_id": run.id,
        "dimension": body.dimension,
        "analysis_type": analysis_type,
        "n_modes": n_modes if analysis_type == "modal" else None,
        "inp_path": run.inp_path,
        "inp_url": f"/files/runs/{run.id}/{artifact.path.name}",
        "ccx_available": _ccx_executable() is not None,
        "cards": cards_ok,
        "solver_ran": False,
        "job_id": None,
        "frd_path": None,
        "frequencies": [],
        "status": run.status,
        "message": run.message,
        "mesh_preview_url": (
            f"/files/runs/{run.id}/mesh_preview.json" if mesh_preview_snapshot_path else None
        ),
    }

    if body.run_solver:
        if not body.wait:
            run.status = "pending"
            run.message = "ccx çalışıyor…"
            db.commit()
            result["status"] = "pending"
            result["message"] = run.message
            background_tasks.add_task(_complete_ccx_job, run.id)
        else:
            try:
                handle = adapter.submit(artifact)
                status = adapter.poll_status(handle)
                parsed = adapter.parse_results(handle)
                result["solver_ran"] = True
                result["job_id"] = handle.job_id
                result["frd_path"] = (
                    str(parsed.raw_result_path).replace("\\", "/")
                    if parsed.raw_result_path
                    else None
                )
                result["message"] = f"ccx bitti ({status.state})"
                result["status"] = "solved"
                scalars = dict(parsed.scalars or {})
                scalars["_analysis_type"] = analysis_type
                scalars, fatigue_note, fatigue_runout = _attach_fatigue_and_sf(
                    scalars,
                    assignments,
                    analysis_type,
                    parsed.results_preview_path,
                )
                result["scalars"] = scalars
                if fatigue_note:
                    result["fatigue_note"] = fatigue_note
                    result["fatigue_runout"] = fatigue_runout
                result["results_preview_url"] = (
                    f"/files/runs/{run.id}/{parsed.results_preview_path.name}"
                    if parsed.results_preview_path
                    else None
                )
                freqs = parsed.curves.get("frequencies") or []
                if freqs:
                    result["frequencies"] = freqs

                run.status = "solved"
                run.message = result["message"]
                run.scalars = scalars
                run.frd_path = result["frd_path"]
                run.results_preview_path = (
                    str(parsed.results_preview_path).replace("\\", "/")
                    if parsed.results_preview_path
                    else None
                )
                db.commit()
            except SolverError as exc:
                result["message"] = str(exc)
                result["status"] = "failed"
                logger.warning("ccx çalıştırılamadı: %s", exc)
                run.status = "failed"
                run.message = str(exc)
                db.commit()

    logger.info(
        "Solve: geometry_id=%d run_id=%d dim=%d inp=%s ran=%s",
        geometry_id,
        run.id,
        body.dimension,
        artifact.path,
        result["solver_ran"],
    )
    return result


@router.get("/runs")
def list_runs(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Tüm analiz geçmişini listeler — en yeni önce.

    ROADMAP.md "7. Veritabanına kayıt + geçmiş" — frontend'de geçmiş
    analizler listesi ve Faz 4 surrogate model eğitim verisi kaynağı.
    Kullanıcı tek tek silebilir; otomatik temizlik yoktur.
    """
    runs = (
        db.query(AnalysisRun)
        .options(joinedload(AnalysisRun.geometry))
        .order_by(AnalysisRun.created_at.desc())
        .all()
    )
    return {
        "count": len(runs),
        "runs": [
            {
                "id": r.id,
                "geometry_id": r.geometry_id,
                "geometry_filename": r.geometry.original_filename if r.geometry else None,
                "name": r.name,
                "created_at": r.created_at.isoformat(),
                "dimension": r.dimension,
                "status": r.status,
                "message": r.message,
                "scalars": r.scalars,
            }
            for r in runs
        ],
    }


@router.get("/runs/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Tek bir run'ın tam detayı — split-screen karşılaştırma için gereken
    tüm URL'leri (geometri tessellation, bu run'ın kendi mesh önizlemesi,
    sonuç önizlemesi) içerir.
    """
    run = db.get(AnalysisRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run bulunamadı: id={run_id}")

    return {
        "id": run.id,
        "geometry_id": run.geometry_id,
        "geometry_filename": run.geometry.original_filename if run.geometry else None,
        "name": run.name,
        "created_at": run.created_at.isoformat(),
        "dimension": run.dimension,
        "element_size": run.element_size,
        "element_scheme": run.element_scheme,
        "shell_thickness": run.shell_thickness,
        "bcs": run.bcs,
        "materials_snapshot": run.materials_snapshot,
        "status": run.status,
        "message": run.message,
        "scalars": run.scalars,
        "tessellation_url": (
            f"/files/runs/{run.id}/tessellation.stl"
            if run.tessellation_snapshot_path
            # Eski run'lar (bu düzeltmeden ÖNCE çözülmüş) anlık görüntüye
            # sahip değil — geriye dönük uyumluluk için canlı geometriye
            # düşülür (bu run'dan sonra geometri mutasyona uğramadıysa
            # doğru, uğradıysa yine kayma görülebilir — bilinen sınırlama).
            else (f"/files/tessellations/{run.geometry_id}.stl" if run.geometry_id else None)
        ),
        "mesh_preview_url": f"/files/runs/{run.id}/mesh_preview.json" if run.mesh_preview_path else None,
        "results_preview_url": (
            f"/files/runs/{run.id}/{Path(run.results_preview_path).name}"
            if run.results_preview_path
            else None
        ),
        "inp_url": f"/files/runs/{run.id}/{Path(run.inp_path).name}" if run.inp_path else None,
    }


@router.delete("/runs/{run_id}")
def delete_run(run_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Bir analiz kaydını ve `uploads/runs/{id}/` klasörünü siler.

    Geometri, mesh ve diğer run'lar durur. Kullanıcı isteğiyle silinir;
    otomatik temizlik yoktur.
    """
    run = db.get(AnalysisRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run bulunamadı: id={run_id}")

    geometry_id = run.geometry_id
    run_dir = RUNS_DIR / str(run.id)
    if run_dir.exists():
        shutil.rmtree(run_dir)

    db.delete(run)
    db.commit()
    logger.info("Run silindi: run_id=%d geometry_id=%s", run_id, geometry_id)
    return {"deleted": True, "run_id": run_id}


@router.get("/runs/{run_id}/report.pdf")
def get_run_report_pdf(run_id: int, db: Session = Depends(get_db)) -> Response:
    """Bu run için okunabilir bir PDF özet rapor üretir — proje/case bilgisi,
    malzeme, BC listesi, sonuç skalerleri. Ham veri (.inp/.frd/.json) ayrı
    endpoint'lerden zaten indirilebiliyor; bu rapor paylaşılabilir bir özet.
    """
    run = db.get(AnalysisRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run bulunamadı: id={run_id}")

    pdf_bytes = build_run_report_pdf(
        run_id=run.id,
        run_name=run.name,
        geometry_filename=run.geometry.original_filename if run.geometry else None,
        created_at=run.created_at,
        dimension=run.dimension,
        status=run.status,
        message=run.message,
        bcs=run.bcs or [],
        materials_snapshot=run.materials_snapshot or [],
        scalars=run.scalars or {},
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="run{run.id}_report.pdf"',
        },
    )


# Static mount için dizin
Path(RUNS_DIR).mkdir(parents=True, exist_ok=True)
_ = UPLOAD_DIR
