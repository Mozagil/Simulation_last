"""Crash vekil modeli API — 1.19e (`/crash/ml`).

Yeni crash yolu; `/solve` ve durability `/surrogate` uçlarına dokunmaz.
Korpus özeti → eğitim (K-fold CV, model dosyası) → tahmin (+ aralık dışı
girdiler). Model seçimi / kabul eşiği yok: metrikler mühendise gösterilir.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.ml.crash import surrogate
from app.ml.crash.corpus import load_crash_corpus
from app.ml.crash.surrogate import CrashModelError
from app.postprocess.crash_targets import TARGETS

router = APIRouter(prefix="/crash/ml", tags=["crash-ml"])


class CorpusQuery(BaseModel):
    template_id: str
    scenario: str = "rigid_wall"
    study_id: int | None = Field(default=None, description="Yalnız bu crash DOE çalışmasının koşuları")


class TrainRequest(CorpusQuery):
    seed: int = 2026
    n_folds: int = Field(default=surrogate.DEFAULT_FOLDS, ge=2, le=20)


class PredictRequest(BaseModel):
    template_id: str
    scenario: str = "rigid_wall"
    inputs: dict[str, float]


def _public(bundle: dict[str, Any]) -> dict[str, Any]:
    """Model dosyasının JSON'a giden kısmı (ağaçlar hariç)."""
    return {
        "template_id": bundle["template_id"],
        "scenario": bundle["scenario"],
        "study_id": bundle.get("study_id"),
        "n_runs": len(bundle.get("run_ids") or []),
        "feature_keys": bundle["feature_keys"],
        "dropped_features": bundle.get("dropped_features", []),
        "constant_features": bundle.get("constant_features", {}),
        "bounds": bundle["bounds"],
        "targets": [
            {"key": t.key, "label": t.label, "unit": t.unit, "definition": t.definition,
             "trained": bundle["models"].get(t.key) is not None,
             "cv": bundle["metrics_cv"].get(t.key)}
            for t in TARGETS
        ],
        "seed": bundle.get("seed"),
    }


def _load_or_404(template_id: str, scenario: str) -> dict[str, Any]:
    try:
        bundle = surrogate.load_crash_model(template_id, scenario)
    except CrashModelError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if bundle is None:
        raise HTTPException(status_code=404, detail=f"Model yok: {template_id} / {scenario}")
    return bundle


@router.get("/targets")
def list_targets() -> dict[str, Any]:
    return {"targets": [t.__dict__ for t in TARGETS]}


@router.post("/corpus")
def corpus_summary(q: CorpusQuery, db: Session = Depends(get_db)) -> dict[str, Any]:
    return load_crash_corpus(db, q.template_id, q.scenario, study_id=q.study_id).summary()


@router.post("/train")
def train(body: TrainRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    corpus = load_crash_corpus(db, body.template_id, body.scenario, study_id=body.study_id)
    try:
        bundle = surrogate.train_crash_surrogate(corpus, seed=body.seed, n_folds=body.n_folds)
        path = surrogate.save_crash_model(bundle)
    except CrashModelError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {**_public(bundle), "path": str(path), "corpus": corpus.summary()}


@router.get("/models")
def list_models() -> dict[str, Any]:
    root = surrogate.MODELS_ROOT
    out = []
    for p in sorted(root.glob("*/*.joblib")) if root.is_dir() else []:
        try:
            out.append(_public(surrogate.load_crash_model(p.parent.name, p.stem)))
        except Exception:  # noqa: BLE001 — bozuk dosya listeyi düşürmez
            out.append({"template_id": p.parent.name, "scenario": p.stem, "error": "okunamadı"})
    return {"models": out}


@router.get("/models/{template_id}/{scenario}")
def get_model(template_id: str, scenario: str) -> dict[str, Any]:
    return _public(_load_or_404(template_id, scenario))


@router.post("/predict")
def predict(body: PredictRequest) -> dict[str, Any]:
    bundle = _load_or_404(body.template_id, body.scenario)
    try:
        return surrogate.predict(bundle, body.inputs)
    except CrashModelError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
