"""Mesh yakınsama taraması API'si (Faz 0.6).

Akış: POST /convergence → merdiven DB'ye yazılır, çözüm arka planda başlar.
GET /convergence/{id} → tablo + yakınsama kararı + önerilen element_ratio.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.solve import RUNS_DIR
from app.db.session import SessionLocal, get_db
from app.doe.convergence import ConvergenceSpec, element_size_ladder
from app.doe.convergence_runner import (
    CONVERGENCE_KIND,
    convergence_report,
    persist_convergence,
    run_convergence,
)
from app.models.doe import DoeStudy
from app.postprocess.stress_probe import DEFAULT_STANDOFF_RATIO, recompute_from_sample
from app.models.material import Material
from app.templates import UnknownTemplateError

router = APIRouter(prefix="/convergence", tags=["convergence"])


def _run_in_background(study_id: int) -> None:
    db = SessionLocal()
    try:
        run_convergence(db, study_id)
    finally:
        db.close()


@router.post("")
def start_convergence(
    spec: ConvergenceSpec,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict:
    if db.get(Material, spec.material_id) is None:
        raise HTTPException(status_code=400, detail="Malzeme bulunamadı.")
    try:
        sizes = element_size_ladder(spec)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        study = persist_convergence(db, spec)
    except UnknownTemplateError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    background.add_task(_run_in_background, study.id)
    return {
        "study_id": study.id,
        "element_sizes": sizes,
        "status": study.status,
        "message": f"{len(sizes)} basamak kuyruğa alındı.",
    }


@router.get("")
def list_convergence(db: Session = Depends(get_db)) -> list[dict]:
    rows = (
        db.query(DoeStudy)
        .order_by(DoeStudy.id.desc())
        .limit(50)
        .all()
    )
    return [
        {
            "study_id": s.id,
            "name": s.name,
            "template_id": s.template_id,
            "status": s.status,
            "message": s.message,
        }
        for s in rows
        if (s.spec or {}).get("kind") == CONVERGENCE_KIND
    ]


@router.post("/backfill-stress-probe")
def backfill_stress_probe(
    standoff_ratio: float = DEFAULT_STANDOFF_RATIO,
    limit: int = 500,
    db: Session = Depends(get_db),
) -> dict:
    """Mevcut çözülmüş run'lara maskeli gerilme skalerini geriye dönük ekler.

    Çözüm tekrarlanmaz — diskteki `.train.npz` okunur. Şablonsuz run'lar
    atlanır (karakteristik uzunluk bilinmiyor). DOE'yi koşmadan ÖNCE bir
    kez çalıştırılmalı ki eski ve yeni örnekler aynı hedefi taşısın.
    """
    from app.models.geometry import Geometry
    from app.models.run import AnalysisRun
    from app.templates import get_template

    runs = (
        db.query(AnalysisRun)
        .filter(AnalysisRun.status == "solved")
        .order_by(AnalysisRun.id.desc())
        .limit(limit)
        .all()
    )
    updated = skipped = failed = 0
    for run in runs:
        sc = dict(run.scalars or {})
        if "max_von_mises_away" in sc:
            skipped += 1
            continue
        geo = db.get(Geometry, run.geometry_id)
        if geo is None or not geo.template_id or not geo.template_params:
            skipped += 1
            continue
        try:
            tpl = get_template(geo.template_id)
            if tpl.characteristic_length is None:
                skipped += 1
                continue
            char_len = float(tpl.characteristic_length(tpl.parse_params(geo.template_params)))
            probe = recompute_from_sample(
                RUNS_DIR / str(run.id) / f"run{run.id}.train.npz",
                characteristic_length=char_len,
                standoff_ratio=standoff_ratio,
            )
            if not probe or probe.get("max_von_mises_away") is None:
                skipped += 1
                continue
            sc["max_von_mises_away"] = probe["max_von_mises_away"]
            sc["stress_probe_standoff_mm"] = probe["standoff_mm"]
            sc["stress_probe_fraction_used"] = probe["fraction_used"]
            run.scalars = sc
            updated += 1
        except Exception:  # noqa: BLE001
            failed += 1
    db.commit()
    return {
        "updated": updated,
        "skipped": skipped,
        "failed": failed,
        "standoff_ratio": standoff_ratio,
    }


@router.get("/{study_id}")
def get_convergence(study_id: int, db: Session = Depends(get_db)) -> dict:
    return convergence_report(db, study_id)


@router.get("/{study_id}/stress-probe")
def stress_probe(
    study_id: int,
    standoff_ratio: float = DEFAULT_STANDOFF_RATIO,
    db: Session = Depends(get_db),
) -> dict:
    """Kısıttan uzakta ölçülen gerilmeyi basamak basamak yeniden hesaplar.

    HİÇBİR ÇÖZÜMÜ TEKRARLAMAZ — diskteki `.train.npz` örneklerini okur.
    Amaç: max σ'nın mesh gürültüsü (ölçtük: %5.6) maskeli ölçümde ne
    kadar düşüyor, görmek. Farklı `standoff_ratio` değerleriyle çağırıp
    karşılaştırılabilir.
    """
    report = convergence_report(db, study_id)
    char_len = float(report.get("characteristic_length") or 0.0)
    if char_len <= 0:
        raise HTTPException(
            status_code=400, detail="Çalışmada karakteristik uzunluk yok."
        )

    rows: list[dict] = []
    values: list[float] = []
    for step in report["table"]:
        run_id = step.get("run_id")
        probe = None
        if run_id is not None:
            probe = recompute_from_sample(
                RUNS_DIR / str(run_id) / f"run{run_id}.train.npz",
                characteristic_length=char_len,
                standoff_ratio=standoff_ratio,
            )
        row = {
            "element_size": step.get("element_size"),
            "run_id": run_id,
            "max_von_mises_all": step.get("max_von_mises"),
            "max_von_mises_away": (probe or {}).get("max_von_mises_away"),
            "n_nodes_used": (probe or {}).get("n_nodes_used"),
            "fraction_used": (probe or {}).get("fraction_used"),
            "warning": (probe or {}).get("warning"),
        }
        rows.append(row)
        if row["max_von_mises_away"] is not None:
            values.append(row["max_von_mises_away"])

    def _band(vals: list[float]) -> float | None:
        tail = vals[-4:]
        if len(tail) < 2:
            return None
        mean = sum(tail) / len(tail)
        return (max(tail) - min(tail)) / abs(mean) if mean else None

    raw = [
        s["max_von_mises"] for s in report["table"] if s.get("max_von_mises") is not None
    ]
    return {
        "study_id": study_id,
        "standoff_ratio": standoff_ratio,
        "standoff_mm": char_len * standoff_ratio,
        "table": rows,
        "noise_floor_masked": _band(values),
        "noise_floor_raw": _band(raw),
    }
