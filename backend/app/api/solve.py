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
from app.models.geometry import Geometry
from app.models.material import MaterialAssignment
from app.models.run import AnalysisRun
from app.postprocess.fatigue import compute_safety_factor, estimate_fatigue_life
from app.postprocess.report import build_run_report_pdf
from app.solvers.base import InputArtifact, SolverError
from app.solvers.calculix import CalculiXAdapter, _ccx_executable
from app.dataset.rebuild import discard_solver_input
from app.postprocess.stress_probe import DEFAULT_STANDOFF_RATIO, recompute_from_sample
from app.templates.compare import build_analytic_comparison, store_comparison_on_scalars

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


def _analytic_comparison_for(
    geo: Geometry | None,
    materials: list[dict[str, Any]],
    bcs: list[dict[str, Any]],
    analysis_type: str,
    scalars: dict[str, Any],
) -> dict[str, Any] | None:
    if geo is None:
        return None
    comparison = build_analytic_comparison(
        template_id=geo.template_id,
        template_params=geo.template_params,
        materials=materials,
        bcs=bcs,
        analysis_type=analysis_type,
        fea_scalars=scalars,
    )
    store_comparison_on_scalars(scalars, comparison)
    return comparison


def _stress_probe_for(
    geo: Geometry | None,
    run_id: int,
    scalars: dict[str, Any],
) -> None:
    """Tekillikten uzakta ölçülen max von Mises'i skalerlere ekler.

    NEDEN: `max_von_mises` ankastre köşe gibi TEKİL noktalardan okunuyor ve
    mesh'ten mesh'e oynuyor. Ölçtük (convergence study_id=8, S235
    L500/T10/W50, uçtan 500 N):

        ham max σ  : gürültü tabanı %5.57 · teoriden +%10 sapma
        1×T maskeli: gürültü tabanı %1.20 · teoriden −%0.8 sapma

    Yani maskeli ölçüm hem 4.6× daha az gürültülü hem teoriye çok daha
    yakın. Surrogate hedefi olarak bunu kullanmak, modelin doğruluk
    tavanını %5.6'dan %1.2'ye çekiyor.

    Karakteristik uzunluk şablondan gelir; şablonsuz (kullanıcı yüklemesi)
    geometride atlanır — ne kadar uzaklaşacağımızı bilemeyiz.
    """
    if geo is None or not geo.template_id:
        return
    try:
        from app.templates import get_template

        tpl = get_template(geo.template_id)
        if tpl.characteristic_length is None or not geo.template_params:
            return
        params = tpl.parse_params(geo.template_params)
        char_len = float(tpl.characteristic_length(params))
        if char_len <= 0:
            return
        probe = recompute_from_sample(
            RUNS_DIR / str(run_id) / f"run{run_id}.train.npz",
            characteristic_length=char_len,
            standoff_ratio=DEFAULT_STANDOFF_RATIO,
        )
        if probe and probe.get("max_von_mises_away") is not None:
            scalars["max_von_mises_away"] = probe["max_von_mises_away"]
            scalars["stress_probe_standoff_mm"] = probe["standoff_mm"]
            scalars["stress_probe_fraction_used"] = probe["fraction_used"]
    except Exception as exc:  # noqa: BLE001
        # Ölçüm başarısız olursa çözüm geçerliliğini yitirmez — ham
        # max_von_mises yerinde duruyor.
        logger.warning("stress probe hesaplanamadı (run %s): %s", run_id, exc)


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
        geo = db.get(Geometry, run.geometry_id)
        _analytic_comparison_for(
            geo,
            list(run.materials_snapshot or []),
            list(run.bcs or []),
            analysis_type,
            scalars,
        )
        _stress_probe_for(geo, run.id, scalars)
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
        discard_solver_input(run)
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
    #: İsimli bölge (`ankastre_uc`, `yuk_yuzeyi` …). Şablondan üretilen
    #: geometrilerde yüzey numarası parametreye göre kayar; isim sabittir.
    #: ÖNCEDEN: bu alan modelde yoktu, pydantic sessizce atıyordu — bölge
    #: adıyla gönderilen BC hiçbir yere bağlanmıyor, model YÜKSÜZ çözülüyor
    #: ve hata verilmiyordu. Artık burada çözülür (bkz. `_bind_regions`).
    region: str | None = None
    face_ids: list[int] | None = None
    edge_ids: list[int] | None = None
    node_ids: list[int] | None = None
    # CAD vertex (node_ids) ile mesh düğümü AYRI şeylerdir: node_ids
    # geometrinin kalıcı köşe id'leridir ve remesh'i atlatır; mesh_node_ids
    # ise kullanıcının mesh üzerinde tıkladığı ham düğüm numaralarıdır ve
    # element size değişip mesh yeniden üretilirse anlamını yitirir.
    mesh_node_ids: list[int] | None = None
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


#: Hedef (yüzey/kenar/düğüm) GEREKTİREN BC tipleri. `gravity` hacim
#: yüküdür, `rigid_body` referans düğümle çalışır — ikisi de listede yok.
_TARGETED_BC_TYPES = ("fixed", "cload", "pressure", "displacement", "sliding", "bearing")


def _bind_regions(
    db: Session, geometry_id: int, bcs: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """`region` adlarını yüzey/kenar id'lerine çevirir.

    DOE ve yakınsama yolları bunu zaten yapıyordu (`bind_scenario_bcs`);
    `/solve` yapmıyordu ve bölge adıyla gelen BC sessizce düşüyordu.
    """
    if not any(bc.get("region") for bc in bcs):
        return bcs
    from app.doe.regions import DoeBindError, bind_scenario_bcs, groups_by_name

    try:
        return bind_scenario_bcs(groups_by_name(db, geometry_id), bcs)
    except DoeBindError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _require_targets(bcs: list[dict[str, Any]]) -> None:
    """Hedefi olmayan BC sessizce yok sayılmaz.

    Hedefsiz bir `cload` modeli YÜKSÜZ çözer: ccx hata vermez, sonuç sıfır
    deplasman çıkar ve bu "çalıştı" gibi görünür.
    """
    empty = [
        f"#{i} {bc.get('type')}"
        for i, bc in enumerate(bcs)
        if str(bc.get("type") or "").lower() in _TARGETED_BC_TYPES
        and not (
            bc.get("face_ids")
            or bc.get("edge_ids")
            or bc.get("node_ids")
            or bc.get("mesh_node_ids")
        )
    ]
    if empty:
        raise HTTPException(
            status_code=422,
            detail=(
                "Şu sınır koşulları hiçbir yüzey/kenar/düğüme bağlı değil: "
                f"{', '.join(empty)}. Yüzey seçin ya da `region` adı verin — "
                "hedefsiz BC sessizce yok sayılırsa model yüksüz çözülür."
            ),
        )


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
    #: Büyük deformasyon (geometrik nonlineerlik). Lineer çözüm denge
    #: denklemlerini deforme OLMAMIŞ geometride kurar; u/L büyüdükçe bu
    #: varsayım bozulur ve çözücü SESSİZCE yanlış cevap verir. Korpus
    #: kapısı bu yüzden u/L > 0.10 run'ları eliyor. NLGEOM açıkken çözüm
    #: iterasyonlu ve belirgin şekilde yavaştır — varsayılan kapalı.
    nlgeom: bool = Field(default=False)
    #: NLGEOM yükleme artım sayısı. Yakınsamıyorsa artırın.
    n_increments: int = Field(default=20, ge=1, le=500)
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
    bcs = _bind_regions(db, geometry_id, bcs)
    _require_targets(bcs)
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
                "nlgeom": body.nlgeom,
                "n_increments": body.n_increments,
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
    # NLGEOM bayrağını kaydet: korpus ve karşılaştırma tarafı bir run'ın
    # lineer mi nonlineer mi çözüldüğünü bilmek zorunda — ikisi aynı
    # modele girmemeli.
    run.scalars = {"_analysis_type": analysis_type, "_nlgeom": bool(body.nlgeom)}
    db.commit()

    result: dict[str, Any] = {
        "geometry_id": geometry_id,
        "run_id": run.id,
        "dimension": body.dimension,
        "analysis_type": analysis_type,
        "nlgeom": body.nlgeom,
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
                comparison = _analytic_comparison_for(
                    geo, materials, bcs, analysis_type, scalars
                )
                _stress_probe_for(geo, run.id, scalars)
                result["scalars"] = scalars
                if comparison is not None:
                    result["analytic_comparison"] = comparison
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
                discard_solver_input(run)
                result["inp_path"] = None
                result["inp_url"] = None
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
def list_runs(
    template_id: str | None = None,
    doe_study_id: int | None = None,
    include_excluded: bool = True,
    only_excluded: bool = False,
    status: str | None = None,
    limit: int | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Analiz geçmişi — en yeni önce, süzülebilir.

    900'e yakın run birikti ve ikinci şablon girince liste karışıyor.
    Süzgeçler:

    - `template_id`: yalnız o şablonun run'ları. Ankastre kiriş ile delikli
      plaka sonuçları aynı listede karışmasın diye.
    - `doe_study_id`: yalnız o DOE/kalite setinin run'ları — "şu 200'lük
      set" diye bakmak için.
    - `include_excluded` / `only_excluded`: elle dışlanmışları gizle ya da
      YALNIZ onları göster (deneme/mükerrer koşuları gözden geçirmek için).
    - `status`, `limit`: alışıldık süzgeçler.

    Varsayılan davranış eskisiyle aynı: hiçbir parametre verilmezse tüm
    run'lar döner.
    """
    q = db.query(AnalysisRun).options(joinedload(AnalysisRun.geometry))
    if template_id:
        q = q.join(AnalysisRun.geometry).filter(Geometry.template_id == template_id)
    if doe_study_id is not None:
        q = q.filter(AnalysisRun.doe_study_id == doe_study_id)
    if only_excluded:
        q = q.filter(AnalysisRun.excluded.is_(True))
    elif not include_excluded:
        q = q.filter(AnalysisRun.excluded.is_(False))
    if status:
        q = q.filter(AnalysisRun.status == status)
    q = q.order_by(AnalysisRun.created_at.desc())
    if limit is not None and limit > 0:
        q = q.limit(limit)
    runs = q.all()
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
                # Şablondan üretilen geometrilerde hangi parametrelerle
                # üretildiği; DOE taramasında "hangi aralık hangi sonucu verdi"
                # sorusunun cevabı burada. Yüklenen STEP'te None.
                "template_id": r.geometry.template_id if r.geometry else None,
                "template_params": r.geometry.template_params if r.geometry else None,
                "doe_study_id": r.doe_study_id,
                "excluded": bool(r.excluded),
                "exclude_reason": r.exclude_reason,
            }
            for r in runs
        ],
    }


class RunExcludeRequest(BaseModel):
    """Run'ı elle dışla / geri al."""

    excluded: bool
    reason: str | None = Field(
        default=None,
        description="Neden dışlandı: 'deneme', 'mükerrer', 'kalitesiz' vb.",
    )


@router.patch("/runs/{run_id}/exclude")
def set_run_excluded(
    run_id: int,
    body: RunExcludeRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Deneme / mükerrer / kalitesiz koşuyu işaretler.

    SİLMEZ — dosyalar diskte kalır, karar geri alınabilir. Dışlanan run
    korpusa (eğitim setine) girmez; geçmişte istenirse gizlenir ya da
    yalnız dışlananlar listelenebilir.

    Silmek yerine işaretlemenin sebebi: bir run'ın "kalitesiz" olduğu
    kararı sonradan yanlış çıkabilir. Silinen geri gelmez.
    """
    run = db.get(AnalysisRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run bulunamadı: id={run_id}")
    run.excluded = bool(body.excluded)
    run.exclude_reason = body.reason if body.excluded else None
    db.commit()
    return {
        "id": run.id,
        "excluded": run.excluded,
        "exclude_reason": run.exclude_reason,
    }


@router.patch("/runs/exclude-bulk")
def set_runs_excluded_bulk(
    body: dict[str, Any],
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Birden çok run'ı tek seferde işaretler.

    Gövde: {"run_ids": [1,2,3], "excluded": true, "reason": "mükerrer"}
    Bütün bir DOE setini elemek için pratik.
    """
    ids = [int(i) for i in (body.get("run_ids") or [])]
    if not ids:
        raise HTTPException(status_code=400, detail="run_ids boş.")
    excluded = bool(body.get("excluded"))
    reason = body.get("reason") if excluded else None
    n = (
        db.query(AnalysisRun)
        .filter(AnalysisRun.id.in_(ids))
        .update(
            {"excluded": excluded, "exclude_reason": reason},
            synchronize_session=False,
        )
    )
    db.commit()
    return {"updated": n, "excluded": excluded, "reason": reason}


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
        "template_id": run.geometry.template_id if run.geometry else None,
        "template_params": run.geometry.template_params if run.geometry else None,
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
        "analytic_comparison": (run.scalars or {}).get("_analytic_comparison"),
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
