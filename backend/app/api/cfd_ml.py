"""CFD DOE + vekil model — Faz 2.9 (crash 1.19 deseni; `/cfd/ml`).

DOE (``POST /cfd/ml/doe``): roket şablonu; taranan değişkenler şablon
parametreleri ve/veya ``mach`` / ``alpha_deg`` (LHS, tohumlu). Her örnek:
şablondan geometri → CFD mesh (aynı tünel / mesh ayarları) → R3 roket koşusu
(aynı çözücü — mühendisin seçimi). Sıralı, arka planda; durum
``uploads/cfd_doe/<id>/doe.json``. Örnek hatası taramayı durdurmaz.

Model (``/corpus``, ``/train``, ``/models``, ``/predict``): korpus
``app.ml.cfd.corpus`` (çözücü başına ayrı), hedef başına Random Forest + K-fold
CV (crash vekil kodu). Model ``uploads/models/cfd/rocket/<çözücü>.joblib``.
Kabul eşiği / öneri yok: CV metrikleri gösterilir.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import numpy as np
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.api.cfd_mesh import CfdMeshRequest, cfd_mesh
from app.api.cfd_rocket import RocketSolveRequest, rocket_solve
from app.db.session import SessionLocal, get_db
from app.doe.sampling import latin_hypercube
from app.mesh.cfd_mesher import SnappyParams, TunnelParams
from app.ml.cfd.corpus import SOLVERS, TARGETS, load_cfd_corpus
from app.ml.crash import surrogate
from app.ml.crash.surrogate import CrashModelError
from app.postprocess.rocket_aero import speed_of_sound
from app.templates.rocket import RocketParams
from app.templates.service import create_geometry_from_template

router = APIRouter(prefix="/cfd/ml", tags=["cfd-ml"])

DOE_DIR = Path("uploads") / "cfd_doe"
MODELS_ROOT = Path("uploads") / "models" / "cfd"
FLOW_VARS = ("mach", "alpha_deg")
_lock = threading.Lock()

Solver = Literal["simpleFoam", "rhoSimpleFoam", "rhoCentralFoam"]


# ------------------------------------------------------------------ DOE


class CfdDoeRequest(BaseModel):
    name: str | None = Field(None, max_length=200)
    #: Sabit şablon parametreleri (taranmayanlar); eksikler şablon varsayılanı.
    template_params: dict[str, Any] = Field(default_factory=dict)
    #: Taranan değişken → [alt, üst]. Şablon sayısal parametresi ya da mach / alpha_deg.
    ranges: dict[str, tuple[float, float]] = Field(min_length=1)
    n_samples: int = Field(8, ge=2, le=200)
    seed: int = 2026
    #: Sabit akış değerleri (taranmıyorsa)
    mach: float = Field(0.3, gt=0)
    alpha_deg: float = Field(4.0, ge=-30, le=30)
    mesher: Literal["snappy", "cfmesh"] = "snappy"
    tunnel: TunnelParams
    snappy: SnappyParams = Field(default_factory=SnappyParams)
    #: R3 koşu ayarları (mesh_id, hız, α, ad hariç kullanılır)
    solve: dict[str, Any] = Field(default_factory=dict)
    wait: bool = False

    @model_validator(mode="after")
    def _vars(self) -> "CfdDoeRequest":
        numeric = {k for k, v in RocketParams.model_fields.items() if v.annotation in (float, int)}
        bad = [k for k in self.ranges if k not in numeric and k not in FLOW_VARS]
        if bad:
            raise ValueError(f"Taranamayan değişken: {', '.join(bad)} (sayısal şablon parametresi ya da mach / alpha_deg)")
        for k, (lo, hi) in self.ranges.items():
            if not hi >= lo:
                raise ValueError(f"{k}: üst sınır alt sınırdan küçük")
        RocketSolveRequest.model_validate({**self.solve, "mesh_id": "x", "speed_m_s": 1.0})
        return self


def _doe_path(doe_id: str) -> Path:
    return DOE_DIR / doe_id / "doe.json"


def _write_doe(data: dict[str, Any]) -> None:
    p = _doe_path(data["doe_id"])
    p.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        p.write_text(json.dumps(data, indent=1), encoding="utf-8")


def read_doe(doe_id: str) -> dict[str, Any] | None:
    p = _doe_path(doe_id)
    if not p.is_file():
        return None
    with _lock:
        return json.loads(p.read_text(encoding="utf-8"))


def sample_doe(body: CfdDoeRequest) -> list[dict[str, Any]]:
    keys = list(body.ranges)
    u = latin_hypercube(body.n_samples, len(keys), np.random.default_rng(body.seed))
    out = []
    for i in range(body.n_samples):
        vals = {k: float(body.ranges[k][0] + u[i, j] * (body.ranges[k][1] - body.ranges[k][0])) for j, k in enumerate(keys)}
        geom = {**body.template_params, **{k: round(v, 3) for k, v in vals.items() if k not in FLOW_VARS}}
        if "fin_count" in geom:
            geom["fin_count"] = int(round(geom["fin_count"]))
        out.append({
            "index": i,
            "template_params": geom,
            "mach": vals.get("mach", body.mach),
            "alpha_deg": vals.get("alpha_deg", body.alpha_deg),
            "status": "pending",
        })
    return out


def run_doe(doe_id: str, body: CfdDoeRequest) -> None:
    data = read_doe(doe_id) or {}
    data["status"] = "running"
    _write_doe(data)
    base = {k: v for k, v in body.solve.items() if k not in ("mesh_id", "speed_m_s", "alpha_deg", "wait", "name")}
    temp = float(base.get("temperature_k", 288.15))
    for s in data["samples"]:
        db = SessionLocal()
        try:
            s["status"] = "geometry"
            _write_doe(data)
            geo, _, _ = create_geometry_from_template(db, "rocket", s["template_params"])
            s["geometry_id"] = geo.id
            s["status"] = "mesh"
            _write_doe(data)
            mesh = cfd_mesh(
                CfdMeshRequest(geometry_id=geo.id, mesher=body.mesher, tunnel=body.tunnel, snappy=body.snappy, wait=True),
                BackgroundTasks(),
                db,
            )
            s["mesh_id"] = mesh["mesh_id"]
            s["cells"] = (mesh.get("check") or {}).get("cells")
            if mesh.get("status") != "meshed":
                raise RuntimeError(f"mesh: {mesh.get('message')}")
            s["status"] = "solve"
            _write_doe(data)
            out = rocket_solve(
                RocketSolveRequest(
                    **base,
                    mesh_id=mesh["mesh_id"],
                    speed_m_s=s["mach"] * speed_of_sound(temp),
                    alpha_deg=s["alpha_deg"],
                    wait=True,
                    name=f"{body.name or 'CFD DOE'} #{s['index'] + 1}",
                ),
                BackgroundTasks(),
                db,
            )
            s["job_id"] = out.get("job_id")
            s["status"] = out.get("status")
            s["message"] = out.get("message")
            a = out.get("rocket_aero") or {}
            s["aero"] = {k: a.get(k) for k, _, _ in TARGETS}
        except Exception as e:  # noqa: BLE001 — örnek hatası taramayı durdurmaz
            s["status"] = "failed"
            s["message"] = f"{type(e).__name__}: {getattr(e, 'detail', e)}"
        finally:
            db.close()
        _write_doe(data)
    ok = sum(1 for s in data["samples"] if s["status"] == "solved")
    data["status"] = "done"
    data["message"] = f"{ok}/{len(data['samples'])} örnek çözüldü"
    _write_doe(data)


@router.post("/doe")
def create_doe(body: CfdDoeRequest, background_tasks: BackgroundTasks) -> dict[str, Any]:
    doe_id = str(uuid.uuid4())
    data = {
        "doe_id": doe_id,
        "name": body.name,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "solver": body.solve.get("solver", "simpleFoam"),
        "request": body.model_dump(mode="json"),
        "samples": sample_doe(body),
    }
    _write_doe(data)
    if body.wait:
        run_doe(doe_id, body)
    else:
        background_tasks.add_task(run_doe, doe_id, body)
    return read_doe(doe_id) or data


@router.get("/doe")
def list_does() -> dict[str, Any]:
    out = []
    for p in sorted(DOE_DIR.glob("*/doe.json"), key=lambda p: p.stat().st_mtime, reverse=True) if DOE_DIR.is_dir() else []:
        d = json.loads(p.read_text(encoding="utf-8"))
        out.append({k: d.get(k) for k in ("doe_id", "name", "status", "message", "created_at", "solver")} | {"n_samples": len(d.get("samples") or [])})
    return {"does": out}


@router.get("/doe/{doe_id}")
def get_doe(doe_id: str) -> dict[str, Any]:
    d = read_doe(doe_id)
    if d is None:
        raise HTTPException(status_code=404, detail="CFD DOE yok")
    return d


# ------------------------------------------------------------------ model


class CorpusQuery(BaseModel):
    application: Solver = "simpleFoam"
    doe_id: str | None = None


class TrainRequest(CorpusQuery):
    seed: int = 2026
    n_folds: int = Field(default=surrogate.DEFAULT_FOLDS, ge=2, le=20)


class PredictRequest(BaseModel):
    application: Solver = "simpleFoam"
    inputs: dict[str, float]


def _corpus(db: Session, q: CorpusQuery):
    job_ids = None
    if q.doe_id:
        d = read_doe(q.doe_id)
        if d is None:
            raise HTTPException(status_code=404, detail="CFD DOE yok")
        job_ids = [s["job_id"] for s in d["samples"] if s.get("job_id")]
    c = load_cfd_corpus(db, q.application, job_ids=job_ids)
    return c


def _public(bundle: dict[str, Any]) -> dict[str, Any]:
    return {
        "application": bundle.get("application"),
        "doe_id": bundle.get("doe_id"),
        "n_runs": len(bundle.get("run_ids") or []),
        "feature_keys": bundle["feature_keys"],
        "dropped_features": bundle.get("dropped_features", []),
        "constant_features": bundle.get("constant_features", {}),
        "bounds": bundle["bounds"],
        "targets": [
            {"key": k, "label": label, "unit": unit, "trained": bundle["models"].get(k) is not None, "cv": bundle["metrics_cv"].get(k)}
            for k, label, unit in TARGETS
        ],
        "seed": bundle.get("seed"),
    }


def _load(application: str) -> dict[str, Any] | None:
    return surrogate.load_crash_model("rocket", application.lower(), root=MODELS_ROOT)


@router.get("/targets")
def list_targets() -> dict[str, Any]:
    return {"targets": [{"key": k, "label": l, "unit": u} for k, l, u in TARGETS], "solvers": list(SOLVERS)}


@router.post("/corpus")
def corpus_summary(q: CorpusQuery, db: Session = Depends(get_db)) -> dict[str, Any]:
    return {**_corpus(db, q).summary(), "application": q.application, "doe_id": q.doe_id}


@router.post("/train")
def train(body: TrainRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    corpus = _corpus(db, body)
    try:
        bundle = surrogate.train_crash_surrogate(corpus, seed=body.seed, n_folds=body.n_folds)
        bundle["application"] = body.application
        bundle["doe_id"] = body.doe_id
        path = surrogate.save_crash_model(bundle, root=MODELS_ROOT)
    except CrashModelError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {**_public(bundle), "path": str(path), "corpus": corpus.summary()}


@router.get("/models")
def list_models() -> dict[str, Any]:
    out = []
    for s in SOLVERS:
        try:
            b = _load(s)
        except Exception:  # noqa: BLE001
            out.append({"application": s, "error": "okunamadı"})
            continue
        if b is not None:
            out.append(_public(b))
    return {"models": out}


@router.post("/predict")
def predict(body: PredictRequest) -> dict[str, Any]:
    b = _load(body.application)
    if b is None:
        raise HTTPException(status_code=404, detail=f"Model yok: {body.application}")
    try:
        return surrogate.predict(b, body.inputs)
    except CrashModelError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
