"""Surrogate eğitim ve tahmin API (0.5.6–0.5.9)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
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
from app.ml.graph_data import GraphSample, iter_training_graphs, load_graph
from app.ml.ood import is_out_of_domain
from app.ml.scalar_features import collect_scalar_table, features_from_dict, features_from_run
from app.ml.scalar_rf import (
    DEFAULT_MODEL_PATH,
    load_scalar_rf,
    predict_scalar,
    public_metrics,
    save_scalar_rf,
    train_scalar_rf,
)
from app.models.geometry import Geometry
from app.models.run import AnalysisRun

router = APIRouter(prefix="/surrogate", tags=["surrogate"])


class ScalarPredictBody(BaseModel):
    features: dict[str, float]


class FieldPredictBody(BaseModel):
    run_id: int | None = None
    geometry_id: int | None = None


def _train_npz_for(run_id: int) -> Path:
    return RUNS_DIR / str(run_id) / f"run{run_id}.train.npz"


def _inputs_npz_for(run_id: int) -> Path:
    return RUNS_DIR / str(run_id) / f"run{run_id}.inputs.npz"


@router.get("/status")
def surrogate_status() -> dict[str, Any]:
    rf = load_scalar_rf(DEFAULT_MODEL_PATH)
    gnn = load_gnn(DEFAULT_GNN_PATH)
    return {
        "scalar_rf": public_metrics(rf) if rf else None,
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
def train_scalar(db: Session = Depends(get_db)) -> dict[str, Any]:
    X, y, ids = collect_scalar_table(db)
    try:
        bundle = train_scalar_rf(X, y)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    save_scalar_rf(bundle, DEFAULT_MODEL_PATH)
    out = public_metrics(bundle)
    out["run_ids"] = ids
    return out


@router.post("/scalar/predict")
def scalar_predict(body: ScalarPredictBody) -> dict[str, Any]:
    bundle = load_scalar_rf(DEFAULT_MODEL_PATH)
    if bundle is None:
        raise HTTPException(status_code=404, detail="Skaler model yok; önce eğit.")
    x = features_from_dict(body.features)
    return predict_scalar(bundle, x)


@router.post("/gnn/train")
def train_field_gnn(db: Session = Depends(get_db)) -> dict[str, Any]:
    samples = list(iter_training_graphs(RUNS_DIR))
    runs = {r.id: r for r in db.query(AnalysisRun).all()}
    for s in samples:
        if s.run_id and s.run_id in runs:
            s.element_size = runs[s.run_id].element_size
    try:
        bundle = train_gnn(samples)
    except ValueError as ext:
        raise HTTPException(status_code=422, detail=str(ext)) from ext
    save_gnn(bundle, DEFAULT_GNN_PATH)
    return {
        "kind": "field_gnn",
        "n_samples": bundle["n_samples"],
        "metrics": bundle["metrics"],
        "path": str(DEFAULT_GNN_PATH),
    }


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
