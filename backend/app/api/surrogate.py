"""Surrogate eğitim ve tahmin API (0.5.6–0.5.9)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.solve import RUNS_DIR
from app.db.session import get_db
from app.ml.gnn import (
    DEFAULT_GNN_PATH,
    global_features_for_ood,
    load_gnn,
    predict_field,
    save_gnn,
    train_gnn,
)
from app.ml.graph_data import GraphSample, load_graph
from app.ml.ood import domain_violations, is_out_of_domain
from app.postprocess.stress_probe import DEFAULT_STANDOFF_RATIO
from app.ml.corpus import CorpusSpec, TrainingCorpus, evaluate_run, select_training_runs
from app.ml.manifest import (
    ManifestError,
    add_runs,
    list_manifests,
    load_manifest,
    reference_from_manifest,
    save_manifest,
    spec_from_manifest,
)
from app.ml.scalar_features import FEATURE_KEYS, collect_scalar_table, features_from_dict, features_from_run
from app.ml.scalar_rf import (
    DEFAULT_MODEL_PATH,
    MIN_SAMPLES,
    load_scalar_rf,
    predict_scalar,
    public_metrics,
    save_scalar_rf,
    train_scalar_rf,
)
from app.ml.scalar_loglinear import (
    DEFAULT_LOGLIN_PATH,
    load_scalar_loglinear,
    predict_scalar_loglinear,
    public_metrics_loglinear,
    save_scalar_loglinear,
    train_scalar_loglinear,
)
from app.models.geometry import Geometry
from app.models.material import Material
from app.models.run import AnalysisRun

router = APIRouter(prefix="/surrogate", tags=["surrogate"])


class ScalarPredictBody(BaseModel):
    features: dict[str, float]


class ParamPredictBody(BaseModel):
    """Yeni tasarım: şablon parametreleri + yük. Geometri/run zorunlu değil."""

    length: float = Field(..., gt=0)
    thickness: float = Field(..., gt=0)
    width: float = Field(..., gt=0)
    element_size: float = Field(default=8.0, gt=0)
    youngs_modulus: float = Field(default=210e9, gt=0)
    poisson_ratio: float = Field(default=0.3, gt=0, lt=0.5)
    load_fx: float = 0.0
    load_fy: float = 0.0
    load_fz: float = 0.0
    pressure_mpa: float = 0.0
    dimension: int = Field(default=3, ge=2, le=3)
    compare_run_id: int | None = None
    #: Akma kontrolü için. Verilirse tahmin edilen σ malzemenin akma
    #: sınırıyla karşılaştırılır; verilmezse bu kontrol atlanır.
    material_id: int | None = None
    #: Akmanın kaçta kaçına kadar "güvenli" sayılsın (0.8 = %20 marj).
    yield_utilisation: float = Field(default=0.8, gt=0, le=2.0)


def _deviation_pct(pred: float, fea: float) -> float | None:
    if abs(fea) < 1e-12:
        return None
    return 100.0 * (pred - fea) / fea


class FieldPredictBody(BaseModel):
    run_id: int | None = None
    geometry_id: int | None = None


class RunIdsBody(BaseModel):
    run_ids: list[int] = Field(default_factory=list)
    override: bool = False


def _corpus_run_ids(db: Session, name: str | None, template_id: str | None) -> tuple[
    list[int] | None, TrainingCorpus | None, dict[str, Any] | None
]:
    """Donmuş manifest varsa onun listesi, yoksa canlı süzgeç."""
    if name:
        try:
            data = load_manifest(name)
        except ManifestError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        ids = [int(v) for v in (data.get("run_ids") or [])]
        return ids, None, data
    corpus = select_training_runs(db, CorpusSpec(template_id=template_id))
    return corpus.run_ids, corpus, None


def _frozen_summary(data: dict[str, Any], n_used: int) -> dict[str, Any]:
    return {
        "source": "manifest",
        "name": data.get("name"),
        "frozen_at": data.get("frozen_at"),
        "n_kept": n_used,
        "run_ids": list(data.get("run_ids") or []),
        "template_id": data.get("template_id"),
        "youngs_modulus": data.get("youngs_modulus"),
        "poisson_ratio": data.get("poisson_ratio"),
        "mesh_ratio_median": data.get("mesh_ratio_median"),
        "dropped": dict(data.get("dropped_at_freeze") or {}),
        "flagged": dict(data.get("flagged_at_freeze") or {}),
        "n_manual": len(data.get("manual_notes") or {}),
    }


def _too_few_frozen(kind: str, n: int, minimum: int, summary: dict[str, Any]) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail={
            "message": f"{kind}: donmuş sette {n} örnek var (en az {minimum}).",
            "corpus": summary,
        },
    )


def _too_few(kind: str, n: int, minimum: int, corpus: TrainingCorpus) -> HTTPException:
    dropped = corpus.dropped or {}
    bits = ", ".join(f"{k}={v}" for k, v in sorted(dropped.items()) if v)
    extra = f" Atılan: {bits}." if bits else ""
    return HTTPException(
        status_code=422,
        detail={
            "message": (
                f"{kind}: süzgeç sonrası {n} örnek kaldı (en az {minimum}).{extra}"
            ),
            "corpus": corpus.as_public(),
        },
    )


def _train_npz_for(run_id: int) -> Path:
    return RUNS_DIR / str(run_id) / f"run{run_id}.train.npz"


def _inputs_npz_for(run_id: int) -> Path:
    return RUNS_DIR / str(run_id) / f"run{run_id}.inputs.npz"



#: Skaler model türleri. "auto" varsa log-log'u seçer — ölçüldü, aynı
#: korpusta doğrulama MAPE'si %16.15 yerine %0.09. Hangi türün kullanıldığı
#: yanıtta `model_kind` ile DAİMA bildirilir; araç sessizce model değiştirmez.
SCALAR_MODELS = ("rf", "loglinear")


def _load_scalar_model(model: str) -> tuple[str, dict[str, Any]] | None:
    """(tür, bundle) ya da None. `auto`: loglinear varsa o, yoksa rf."""
    if model not in ("auto",) + SCALAR_MODELS:
        raise HTTPException(
            status_code=422,
            detail=f"model 'auto', {' veya '.join(repr(m) for m in SCALAR_MODELS)} olmalı.",
        )
    if model in ("auto", "loglinear"):
        bundle = load_scalar_loglinear(DEFAULT_LOGLIN_PATH)
        if bundle is not None:
            return "loglinear", bundle
        if model == "loglinear":
            return None
    bundle = load_scalar_rf(DEFAULT_MODEL_PATH)
    return ("rf", bundle) if bundle is not None else None


def _predict_with(kind: str, bundle: dict[str, Any], x) -> dict[str, Any]:
    return (
        predict_scalar_loglinear(bundle, x)
        if kind == "loglinear"
        else predict_scalar(bundle, x)
    )


@router.get("/status")
def surrogate_status() -> dict[str, Any]:
    rf = load_scalar_rf(DEFAULT_MODEL_PATH)
    gnn = load_gnn(DEFAULT_GNN_PATH)
    loglin = load_scalar_loglinear(DEFAULT_LOGLIN_PATH)
    return {
        "scalar_rf": public_metrics(rf) if rf else None,
        "scalar_loglinear": public_metrics_loglinear(loglin) if loglin else None,
        "field_gnn": (
            {
                "kind": gnn["kind"],
                "n_samples": gnn.get("n_samples"),
                "metrics": gnn.get("metrics"),
            }
            if gnn
            else None
        ),
    }


@router.post("/scalar/train")
def train_scalar(
    db: Session = Depends(get_db),
    template_id: str | None = None,
    corpus_name: str | None = None,
    model: str = "rf",
) -> dict[str, Any]:
    """Skaler surrogate eğitimi. `model`: "rf" | "loglinear".

    İki tür AYNI korpustan, aynı metrik tanımıyla eğitilir; ikisi de kendi
    dosyasına yazılır, biri diğerini silmez. Hangisinin kullanılacağı
    tahmin anında seçilir.
    """
    if model not in SCALAR_MODELS:
        raise HTTPException(
            status_code=422,
            detail=f"model {' veya '.join(repr(m) for m in SCALAR_MODELS)} olmalı.",
        )
    label = "RF" if model == "rf" else "log-log"
    run_ids, corpus, frozen = _corpus_run_ids(db, corpus_name, template_id)
    X, y, ids = collect_scalar_table(db, run_ids=run_ids)
    if len(ids) < MIN_SAMPLES:
        if frozen is not None:
            raise _too_few_frozen(label, len(ids), MIN_SAMPLES, _frozen_summary(frozen, len(ids)))
        assert corpus is not None
        raise _too_few(label, len(ids), MIN_SAMPLES, corpus)
    try:
        bundle = (
            train_scalar_rf(X, y) if model == "rf" else train_scalar_loglinear(X, y)
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    bundle["corpus"] = (
        _frozen_summary(frozen, len(ids)) if frozen is not None else corpus.as_public()
    )
    if model == "rf":
        save_scalar_rf(bundle, DEFAULT_MODEL_PATH)
        out = public_metrics(bundle)
    else:
        save_scalar_loglinear(bundle, DEFAULT_LOGLIN_PATH)
        out = public_metrics_loglinear(bundle)
    out["model_kind"] = model
    out["run_ids"] = ids
    return out


@router.post("/scalar/predict")
def scalar_predict(body: ScalarPredictBody, model: str = "auto") -> dict[str, Any]:
    loaded = _load_scalar_model(model)
    if loaded is None:
        raise HTTPException(status_code=404, detail="Skaler model yok; önce eğit.")
    kind, bundle = loaded
    out = _predict_with(kind, bundle, features_from_dict(body.features))
    out["model_kind"] = kind
    return out


@router.post("/predict/params")
def predict_from_params(
    body: ParamPredictBody,
    db: Session = Depends(get_db),
    model: str = "auto",
) -> dict[str, Any]:
    """ccx ve mesh yok: L/T/W + yük → skaler tahmin. İsteğe bağlı FEA kıyası.

    `model`: "auto" (loglinear varsa o) | "rf" | "loglinear". Kullanılan tür
    yanıtta `model_kind` ile döner.
    """
    loaded = _load_scalar_model(model)
    if loaded is None:
        raise HTTPException(status_code=404, detail="Skaler model yok; önce eğit.")
    model_kind, bundle = loaded
    features = {
        "length": body.length,
        "thickness": body.thickness,
        "width": body.width,
        "element_size": body.element_size,
        "youngs_modulus": body.youngs_modulus,
        "poisson_ratio": body.poisson_ratio,
        "load_fx": body.load_fx,
        "load_fy": body.load_fy,
        "load_fz": body.load_fz,
        "pressure_mpa": body.pressure_mpa,
        "dimension": float(body.dimension),
    }
    vec = features_from_dict(features)
    pred = _predict_with(model_kind, bundle, vec)

    # HANGİ özellik uzay dışında — yalnız "uzay dışı" demek kullanıcıya
    # neyi düzelteceğini söylemiyor. Ölçülen vaka: 20×2 kesit, L=100 mm →
    # beş özellikten dördü kutunun dışındaydı, sadece yük içerideydi.
    pred["domain_violations"] = domain_violations(
        vec, bundle.get("bounds") or {}, tuple(FEATURE_KEYS)
    )

    # Akma kontrolü. OOD'den AYRI bir şey: OOD istatistikseldir ("bu
    # noktayı görmedim"), akma fizikseldir ("sonuç doğru hesaplansa bile
    # malzeme plastik davranıyorsa geçersiz"). Biri diğerini yakalamaz.
    # Aynı ölçülen vakada tahmin teoriyle birebir tuttu (375.0 MPa) ama
    # S235'in akması 235 → tasarım zaten geçersizdi.
    # Bu kontrol DOE elemesinde vardı (`doe/screening.py`), tahmin
    # tarafında yoktu.
    pred["yield_check"] = None
    if body.material_id is not None:
        mat = db.get(Material, body.material_id)
        if mat is not None and mat.yield_strength:
            yield_mpa = float(mat.yield_strength) / 1e6
            limit = yield_mpa * float(body.yield_utilisation)
            preds = pred.get("predictions") or {}
            sigma = preds.get("max_von_mises_away")
            source = "max_von_mises_away"
            if sigma is None:
                sigma = preds.get("max_von_mises")
                source = "max_von_mises"
            if sigma is not None:
                pred["yield_check"] = {
                    "material": mat.name,
                    "sigma_mpa": float(sigma),
                    "yield_mpa": yield_mpa,
                    "limit_mpa": limit,
                    "utilisation": float(sigma) / yield_mpa if yield_mpa else None,
                    "exceeds_yield": float(sigma) > yield_mpa,
                    "exceeds_limit": float(sigma) > limit,
                    "source": source,
                }

    fea: dict[str, Any] | None = None
    deviation: dict[str, float | None] | None = None
    if body.compare_run_id is not None:
        run = db.get(AnalysisRun, body.compare_run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Kıyas run yok.")
        scalars = run.scalars or {}
        try:
            fea_disp = float(scalars["max_displacement"])
            fea_vm = float(scalars["max_von_mises"])
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=422, detail="Kıyas run'da FEA skalerleri yok."
            ) from exc
        fea = {
            "run_id": run.id,
            "geometry_id": run.geometry_id,
            "max_displacement": fea_disp,
            "max_von_mises": fea_vm,
        }
        preds = pred["predictions"]
        deviation = {
            "max_displacement_pct": _deviation_pct(preds["max_displacement"], fea_disp),
            "max_von_mises_pct": _deviation_pct(preds["max_von_mises"], fea_vm),
        }
    ood = bool(pred["out_of_domain"])
    return {
        "kind": "scalar",
        "model_kind": model_kind,
        "source": "surrogate",
        "out_of_domain": ood,
        "predictions": pred["predictions"],
        "features": features,
        "fea": fea,
        "deviation_pct": deviation,
        "message": (
            f"Tahmin ({'log-log' if model_kind == 'loglinear' else 'RF'})"
            " — ccx çalışmadı, tam çözüm değil."
            + (" Eğitim uzayı dışı." if ood else "")
            + (" FEA kıyası eklendi." if fea else "")
        ),
    }


@router.post("/gnn/train")
def train_field_gnn(
    db: Session = Depends(get_db),
    template_id: str | None = None,
    corpus_name: str | None = None,
) -> dict[str, Any]:
    run_ids, corpus, frozen = _corpus_run_ids(db, corpus_name, template_id)
    runs = {r.id: r for r in db.query(AnalysisRun).all()}
    samples: list[GraphSample] = []
    missing = 0
    for rid in run_ids or []:
        sample = load_graph(_train_npz_for(rid), run_id=rid)
        if sample is None or sample.node_outputs is None:
            missing += 1
            continue
        run = runs.get(rid)
        if run is not None:
            sample.element_size = run.element_size
        samples.append(sample)

    if frozen is not None:
        summary = _frozen_summary(frozen, len(samples))
        if missing:
            summary["dropped"] = dict(summary["dropped"]) | {"missing_graph": missing}
        if len(samples) < 2:
            raise _too_few_frozen("GNN", len(samples), 2, summary)
    else:
        assert corpus is not None
        if missing:
            corpus.dropped["missing_graph"] = missing
            corpus.n_kept = len(samples)
        if len(samples) < 2:
            raise _too_few("GNN", len(samples), 2, corpus)
        summary = corpus.as_public()

    try:
        bundle = train_gnn(samples)
    except ValueError as ext:
        raise HTTPException(status_code=422, detail=str(ext)) from ext
    bundle["corpus"] = summary
    save_gnn(bundle, DEFAULT_GNN_PATH)
    return {
        "kind": "field_gnn",
        "n_samples": bundle["n_samples"],
        "metrics": bundle["metrics"],
        "path": str(DEFAULT_GNN_PATH),
        "corpus": summary,
    }


@router.post("/corpus/freeze")
def freeze_corpus(
    name: str,
    db: Session = Depends(get_db),
    template_id: str | None = None,
    study_id: int | None = None,
) -> dict[str, Any]:
    """Canlı süzgeç seçimini isimli bir manifeste dondurur.

    `study_id` verilirse yalnız o DOE çalışmasının run'ları taranır. Süzgeçler
    "tutarsız mı" diye bakar, "planladığım kutudan mı" diye bakmaz; elle
    çözülen doğrulama koşuları süzgeci geçip eğitim kutusunu tek noktayla
    genişletebilir (bkz. `CorpusSpec.study_id`).
    """
    corpus = select_training_runs(
        db, CorpusSpec(template_id=template_id, study_id=study_id)
    )
    try:
        payload = save_manifest(name, corpus)
    except ManifestError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"manifest": payload, "corpus": corpus.as_public()}


@router.get("/corpus")
def corpus_index() -> dict[str, Any]:
    return {"manifests": list_manifests()}


@router.get("/corpus/{name}")
def corpus_detail(name: str) -> dict[str, Any]:
    try:
        return load_manifest(name)
    except ManifestError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/corpus/{name}/membership")
def corpus_membership(name: str) -> dict[str, Any]:
    """Geçmiş rozetleri için: hangi run otomatik, hangisi elle eklendi."""
    try:
        data = load_manifest(name)
    except ManifestError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    notes: dict[str, Any] = data.get("manual_notes") or {}
    run_ids = [int(v) for v in (data.get("run_ids") or [])]
    manual_pass: list[int] = []
    manual_override: list[int] = []
    for raw, note in notes.items():
        try:
            rid = int(raw)
        except (TypeError, ValueError):
            continue
        if rid not in run_ids:
            continue
        if str((note or {}).get("gate")) == "override":
            manual_override.append(rid)
        else:
            manual_pass.append(rid)
    manual = set(manual_pass) | set(manual_override)
    return {
        "name": name,
        "frozen_at": data.get("frozen_at"),
        "auto": sorted(rid for rid in run_ids if rid not in manual),
        "manual_pass": sorted(manual_pass),
        "manual_override": sorted(manual_override),
        "notes": notes,
    }


@router.post("/corpus/{name}/evaluate")
def corpus_evaluate(
    name: str,
    body: RunIdsBody,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Manuel run'ların karnesi. Hiçbir şey eklemez, yalnız sayı gösterir."""
    try:
        data = load_manifest(name)
    except ManifestError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    spec = spec_from_manifest(data)
    ref = reference_from_manifest(data)
    verdicts = [evaluate_run(db, rid, spec, reference=ref) for rid in body.run_ids]
    return {
        "name": name,
        "already_present": [
            rid for rid in body.run_ids if rid in (data.get("run_ids") or [])
        ],
        "verdicts": [v.as_public() for v in verdicts],
    }


@router.post("/corpus/{name}/add")
def corpus_add(
    name: str,
    body: RunIdsBody,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Açık onayla ekleme. Süzgeci geçmeyen run yalnız override ile girer."""
    try:
        data = load_manifest(name)
        spec = spec_from_manifest(data)
        ref = reference_from_manifest(data)
        verdicts = [evaluate_run(db, rid, spec, reference=ref) for rid in body.run_ids]
        result = add_runs(name, verdicts, override=body.override)
    except ManifestError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    result["verdicts"] = [v.as_public() for v in verdicts]
    return result


def _preview_from_prediction(sample: GraphSample, yhat: np.ndarray) -> dict[str, Any]:
    mag = np.linalg.norm(yhat[:, :3], axis=1)
    vm = yhat[:, 3]
    crit_i = int(np.argmax(vm)) if vm.size else 0
    crit = int(sample.node_ids[crit_i]) if sample.node_ids.size else None
    return {
        "node_ids": [int(v) for v in sample.node_ids.tolist()],
        "nodes": sample.node_inputs[:, :3].tolist(),
        "displacement_vectors": yhat[:, :3].tolist(),
        "displacement_magnitude": mag.tolist(),
        "von_mises": vm.tolist(),
        "max_displacement": float(mag.max()) if mag.size else 0.0,
        "max_von_mises": float(vm.max()) if vm.size else 0.0,
        "critical_node_id": crit,
        "modes": [],
        "source": "surrogate",
    }


def _resolve_run(db: Session, body: FieldPredictBody) -> AnalysisRun:
    if body.run_id is not None:
        run = db.get(AnalysisRun, body.run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Run yok.")
        return run
    if body.geometry_id is None:
        raise HTTPException(status_code=422, detail="run_id veya geometry_id gerekli.")
    run = (
        db.query(AnalysisRun)
        .filter(AnalysisRun.geometry_id == body.geometry_id)
        .order_by(AnalysisRun.id.desc())
        .first()
    )
    if run is None:
        raise HTTPException(status_code=404, detail="Bu geometride run yok.")
    return run


@router.post("/predict")
def predict(body: FieldPredictBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Alan tahmini (GNN) veya skaler yedek (RF). Viewer preview JSON şeması."""
    run = _resolve_run(db, body)
    geo = db.get(Geometry, run.geometry_id)
    gnn = load_gnn(DEFAULT_GNN_PATH)
    rf = load_scalar_rf(DEFAULT_MODEL_PATH)
    if gnn is None and rf is None:
        raise HTTPException(status_code=404, detail="Eğitilmiş model yok.")

    sample = load_graph(_train_npz_for(run.id), run_id=run.id)
    if sample is None:
        sample = load_graph(_inputs_npz_for(run.id), run_id=run.id)

    ood = False
    field_metrics: dict[str, Any] | None = None
    preview: dict[str, Any] | None = None
    kind = "scalar"

    if gnn is not None and sample is not None:
        kind = "field"
        yhat = predict_field(gnn, sample)
        preview = _preview_from_prediction(sample, yhat)
        ood = is_out_of_domain(
            global_features_for_ood(sample.node_inputs), gnn.get("bounds") or {}
        )
        if sample.node_outputs is not None:
            diff = yhat - sample.node_outputs
            mag_t = np.linalg.norm(sample.node_outputs[:, :3], axis=1)
            mag_p = np.linalg.norm(yhat[:, :3], axis=1)
            field_metrics = {
                "node_rmse": float(np.sqrt((diff**2).mean())),
                "max_displacement_true": float(mag_t.max()),
                "max_displacement_pred": float(mag_p.max()),
                "max_von_mises_true": float(sample.node_outputs[:, 3].max()),
                "max_von_mises_pred": float(yhat[:, 3].max()),
            }
    elif rf is not None:
        x = features_from_run(run, geo)
        if x is None:
            raise HTTPException(status_code=422, detail="Bu run için skaler özellik çıkarılamadı.")
        scalar = predict_scalar(rf, x)
        ood = bool(scalar["out_of_domain"])
        preview = {
            "node_ids": [],
            "nodes": [],
            "displacement_vectors": [],
            "displacement_magnitude": [],
            "von_mises": [],
            "max_displacement": scalar["predictions"]["max_displacement"],
            "max_von_mises": scalar["predictions"]["max_von_mises"],
            "critical_node_id": None,
            "modes": [],
            "source": "surrogate_scalar",
        }
        kind = "scalar"

    if preview is None:
        raise HTTPException(status_code=422, detail="Tahmin için mesh/eğitim dosyası yok.")

    return {
        "kind": kind,
        "source": "surrogate",
        "out_of_domain": ood,
        "run_id": run.id,
        "geometry_id": run.geometry_id,
        "field_metrics": field_metrics,
        "preview": preview,
        "message": (
            "Tahmin — tam çözüm değil."
            + (" Eğitim uzayı dışı." if ood else "")
            + (" Alan yok; skaler baseline." if kind == "scalar" else "")
        ),
    }


@router.post("/backfill-stress-probe")
def backfill_stress_probe(
    standoff_ratio: float = DEFAULT_STANDOFF_RATIO,
    limit: int = 500,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Mevcut çözülmüş run'lara maskeli gerilme skalerini geriye dönük ekler.

    Çözüm TEKRARLANMAZ — diskteki `.train.npz` okunur.

    NEDEN: ham `max_von_mises` ankastre köşe gibi TEKİL noktalardan
    okunuyor ve mesh'ten mesh'e oynuyor. Ölçtük (ankastre kiriş, 8
    basamaklı tarama): ham gürültü tabanı %5.57 ve teoriden +%10 sapma;
    kısıttan 1×T uzakta ölçülünce %1.20 ve −%0.8. Üstel de düzeliyor:
    thickness −1.919 → −2.011 (teori −2).

    Şablonsuz run'lar atlanır (karakteristik uzunluk bilinmiyor).
    Yeni DOE koşusundan ÖNCE bir kez çalıştırılmalı ki eski ve yeni
    örnekler aynı hedefi taşısın.
    """
    from app.api.solve import RUNS_DIR
    from app.models.geometry import Geometry
    from app.postprocess.stress_probe import recompute_from_sample
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
            char_len = float(
                tpl.characteristic_length(tpl.parse_params(geo.template_params))
            )
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
