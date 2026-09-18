"""Eğitim korpusu: RF / GNN / sonraki modeller aynı süzgeçten geçer.

Gürültü model hiperparametresinden gelmez; karışık aile, karışık malzeme,
analitik uyumsuz etiket, büyük deplasman (lineer olmayan fizik) ve aşırı
farklı göreli mesh oranı tek modele girince test R² bozulur.

Bu modül mühendislik önerisi üretmez: mevcut kayıttaki tutarsız örnekleri
ayırır ve neyin neden düştüğünü sayar. Yeni bir solver ailesi aynı
`select_training_runs` + `CorpusSpec` ile eğitilir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.doe.quality import MIN_NODES, RIGID_DISP_MM
from app.ml.scalar_features import features_from_run, targets_from_run
from app.ml.scalar_rf import MIN_SAMPLES
from app.models.geometry import Geometry
from app.models.run import AnalysisRun

#: Lineer etiket kapısı: u / karakteristik uzunluk. Üstü büyük deformasyon;
#: o koşular ayrı modele aittir (0.6.5).
DEFAULT_MAX_U_OVER_L = 0.10
#: Göreli eleman boyutu (es / kalınlık veya L) medyandan sapma üstü.
DEFAULT_MESH_RATIO_BAND = 0.50


@dataclass
class CorpusSpec:
    template_id: str | None = None
    analysis_type: str = "static"
    max_u_over_L: float = DEFAULT_MAX_U_OVER_L
    mesh_ratio_band: float = DEFAULT_MESH_RATIO_BAND
    require_analytic_ok: bool = True
    #: Verilirse yalnız bu DOE çalışmasının run'ları taranır.
    #:
    #: NEDEN: süzgeçler "tutarsız mı" diye bakar, "planladığım kutudan mı"
    #: diye bakmaz. Elle çözülen tek tük doğrulama koşuları (bir T=20, bir
    #: F=1000 N) süzgeci geçer ama eğitim kutusunu tek noktayla genişletir.
    #: OOD koruması min–maks kutusu olduğu için (`ml/ood.py`) bu, korumayı
    #: tam gerektiği yerde işlevsizleştirir: F=1000'de tek örnek varken
    #: F=900 "eğitim uzayı içinde" sayılır. Ölçüldü: study 3 kutusu
    #: F ≤ 220 N iken, süzgeç F=1000 N'lik bir koşuyu sete almıştı.
    study_id: int | None = None


@dataclass
class TrainingCorpus:
    run_ids: list[int]
    template_id: str | None
    youngs_modulus: float | None
    poisson_ratio: float | None
    dropped: dict[str, int]
    flagged: dict[str, int]
    n_scanned: int
    n_kept: int
    mesh_ratio_median: float | None = None
    spec: CorpusSpec = field(default_factory=CorpusSpec)

    def as_public(self) -> dict[str, Any]:
        return {
            "n_scanned": self.n_scanned,
            "n_kept": self.n_kept,
            "run_ids": list(self.run_ids),
            "template_id": self.template_id,
            "youngs_modulus": self.youngs_modulus,
            "poisson_ratio": self.poisson_ratio,
            "mesh_ratio_median": self.mesh_ratio_median,
            "dropped": dict(self.dropped),
            "flagged": dict(self.flagged),
            "max_u_over_L": self.spec.max_u_over_L,
            "mesh_ratio_band": self.spec.mesh_ratio_band,
            "analysis_type": self.spec.analysis_type,
            "study_id": self.spec.study_id,
        }


@dataclass
class RunVerdict:
    """Tek run'ın süzgeç karnesi. Karar kullanıcıya ait; bu yapı sayı gösterir."""

    run_id: int
    ok: bool
    reason: str | None
    u_over_L: float | None
    mesh_ratio: float | None
    mesh_deviation: float | None
    template_id: str | None
    youngs_modulus: float | None
    poisson_ratio: float | None

    def as_public(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "ok": self.ok,
            "reason": self.reason,
            "u_over_L": self.u_over_L,
            "mesh_ratio": self.mesh_ratio,
            "mesh_deviation": self.mesh_deviation,
            "template_id": self.template_id,
            "youngs_modulus": self.youngs_modulus,
            "poisson_ratio": self.poisson_ratio,
        }


def _drop(dropped: dict[str, int], reason: str, n: int = 1) -> None:
    dropped[reason] = dropped.get(reason, 0) + n


def _analysis_type(run: AnalysisRun) -> str:
    raw = (run.scalars or {}).get("_analysis_type")
    if raw:
        return str(raw).lower()
    return "static"


def _char_length(geo: Geometry) -> float:
    params = geo.template_params or {}
    best = 0.0
    for key in ("length", "width", "height", "span"):
        try:
            val = float(params.get(key) or 0.0)
        except (TypeError, ValueError):
            continue
        if val > best:
            best = val
    return best


def _u_over_L(run: AnalysisRun, geo: Geometry) -> float | None:
    L = _char_length(geo)
    if L <= 0:
        return None
    try:
        disp = float((run.scalars or {}).get("max_displacement"))
    except (TypeError, ValueError):
        return None
    return abs(disp) / L


def _mesh_ratio(run: AnalysisRun, geo: Geometry) -> float | None:
    es = run.element_size
    if es is None or es <= 0:
        return None
    params = geo.template_params or {}
    try:
        thick = float(params.get("thickness") or 0.0)
    except (TypeError, ValueError):
        thick = 0.0
    denom = thick if thick > 0 else _char_length(geo)
    if denom <= 0:
        return None
    return float(es) / denom


def _material_key(run: AnalysisRun) -> tuple[float, float]:
    mats = run.materials_snapshot or []
    m0 = mats[0] if mats else {}
    e = float(m0.get("youngs_modulus") or 0.0)
    nu = float(m0.get("poisson_ratio") if m0.get("poisson_ratio") is not None else 0.3)
    return (round(e, -6), round(nu, 3))


def _row_reject(run: AnalysisRun, geo: Geometry, spec: CorpusSpec) -> str | None:
    if (geo.template_id or "") == "":
        return "no_template"
    if _analysis_type(run) != spec.analysis_type:
        return "wrong_analysis"
    if features_from_run(run, geo) is None or targets_from_run(run) is None:
        return "missing_features"
    scalars = run.scalars or {}
    disp = scalars.get("max_displacement")
    try:
        if disp is not None and float(disp) > RIGID_DISP_MM:
            return "rigid_body"
    except (TypeError, ValueError):
        return "bad_scalars"
    nodes = scalars.get("node_count")
    try:
        if nodes is not None and float(nodes) < MIN_NODES:
            return "degenerate_mesh"
    except (TypeError, ValueError):
        return "bad_scalars"
    if spec.require_analytic_ok:
        cmp_ = scalars.get("_analytic_comparison")
        if isinstance(cmp_, dict) and cmp_.get("warned"):
            return "analytic_warn"
    return None


def _keep_majority(
    rows: list[tuple[AnalysisRun, Geometry]],
    key_fn: Callable[[tuple[AnalysisRun, Geometry]], Any],
    reason: str,
    dropped: dict[str, int],
) -> list[tuple[AnalysisRun, Geometry]]:
    if not rows:
        return []
    keys = [key_fn(row) for row in rows]
    counts: dict[Any, int] = {}
    for k in keys:
        counts[k] = counts.get(k, 0) + 1
    winner = sorted(counts.items(), key=lambda kv: (-kv[1], str(kv[0])))[0][0]
    kept: list[tuple[AnalysisRun, Geometry]] = []
    for row, k in zip(rows, keys):
        if k == winner:
            kept.append(row)
        else:
            _drop(dropped, reason)
    return kept


def _soft_drop_large(
    kept: list[tuple[AnalysisRun, Geometry]],
    spec: CorpusSpec,
    dropped: dict[str, int],
    min_keep: int,
) -> list[tuple[AnalysisRun, Geometry]]:
    scored: list[tuple[float, AnalysisRun, Geometry]] = []
    for run, geo in kept:
        ratio = _u_over_L(run, geo)
        scored.append((ratio if ratio is not None else 0.0, run, geo))
    scored.sort(key=lambda t: t[0], reverse=True)
    remain = list(scored)
    while remain and len(remain) > min_keep and remain[0][0] > spec.max_u_over_L:
        remain.pop(0)
        _drop(dropped, "large_displacement")
    return [(run, geo) for _, run, geo in remain]


def _soft_drop_mesh(
    kept: list[tuple[AnalysisRun, Geometry]],
    spec: CorpusSpec,
    dropped: dict[str, int],
    min_keep: int,
) -> list[tuple[AnalysisRun, Geometry]]:
    if not kept:
        return []
    ratios = [_mesh_ratio(run, geo) for run, geo in kept]
    valid = [r for r in ratios if r is not None]
    if not valid:
        return kept
    med = float(np.median(np.asarray(valid, dtype=np.float64)))
    if med <= 0:
        return kept

    def _dev(ratio: float | None) -> float:
        if ratio is None:
            return 0.0
        return abs(ratio - med) / med

    ranked = sorted(
        zip(kept, ratios, strict=True),
        key=lambda item: _dev(item[1]),
        reverse=True,
    )
    remain = list(ranked)
    while remain and len(remain) > min_keep:
        (run, geo), ratio = remain[0]
        if _dev(ratio) > spec.mesh_ratio_band:
            remain.pop(0)
            _drop(dropped, "mesh_outlier")
            continue
        break
    return [row for row, _ in remain]


def select_training_runs(
    db: Session,
    spec: CorpusSpec | None = None,
    *,
    min_keep: int = MIN_SAMPLES,
) -> TrainingCorpus:
    spec = spec or CorpusSpec()
    dropped: dict[str, int] = {}
    query = (
        db.query(AnalysisRun, Geometry)
        .join(Geometry, Geometry.id == AnalysisRun.geometry_id)
        .filter(AnalysisRun.status == "solved")
    )
    if spec.study_id is not None:
        from app.models.doe import DoeCase

        study_runs = (
            db.query(DoeCase.run_id)
            .filter(DoeCase.study_id == spec.study_id, DoeCase.run_id.isnot(None))
            .subquery()
        )
        query = query.filter(AnalysisRun.id.in_(select(study_runs.c.run_id)))
    rows = query.order_by(AnalysisRun.id).all()
    n_scanned = len(rows)
    kept: list[tuple[AnalysisRun, Geometry]] = []
    for run, geo in rows:
        reason = _row_reject(run, geo, spec)
        if reason:
            _drop(dropped, reason)
            continue
        kept.append((run, geo))

    if spec.template_id:
        filtered: list[tuple[AnalysisRun, Geometry]] = []
        for run, geo in kept:
            if (geo.template_id or "") == spec.template_id:
                filtered.append((run, geo))
            else:
                _drop(dropped, "other_template")
        kept = filtered
    else:
        kept = _keep_majority(
            kept, lambda rg: rg[1].template_id or "", "other_template", dropped
        )

    family = kept[0][1].template_id if kept else spec.template_id
    kept = _keep_majority(kept, lambda rg: _material_key(rg[0]), "other_material", dropped)

    kept = _soft_drop_large(kept, spec, dropped, min_keep)
    kept = _soft_drop_mesh(kept, spec, dropped, min_keep)

    flagged: dict[str, int] = {}
    n_over = 0
    for run, geo in kept:
        ratio = _u_over_L(run, geo)
        if ratio is not None and ratio > spec.max_u_over_L:
            n_over += 1
    if n_over:
        flagged["large_displacement"] = n_over

    kept.sort(key=lambda rg: rg[0].id)

    e: float | None = None
    nu: float | None = None
    if kept:
        mats = kept[0][0].materials_snapshot or []
        m0 = mats[0] if mats else {}
        if m0.get("youngs_modulus") is not None:
            e = float(m0["youngs_modulus"])
        if m0.get("poisson_ratio") is not None:
            nu = float(m0["poisson_ratio"])

    kept_ratios = [r for r in (_mesh_ratio(run, geo) for run, geo in kept) if r is not None]
    med_ratio = float(np.median(np.asarray(kept_ratios, dtype=np.float64))) if kept_ratios else None

    return TrainingCorpus(
        run_ids=[run.id for run, _ in kept],
        template_id=family,
        youngs_modulus=e,
        poisson_ratio=nu,
        dropped=dropped,
        flagged=flagged,
        n_scanned=n_scanned,
        n_kept=len(kept),
        mesh_ratio_median=med_ratio,
        spec=spec,
    )


def evaluate_run(
    db: Session,
    run_id: int,
    spec: CorpusSpec | None = None,
    *,
    reference: dict[str, Any] | None = None,
) -> RunVerdict:
    """Manuel çözülmüş bir run'ı donmuş setin ölçütlerine göre değerlendirir.

    `reference` manifest özeti: `template_id`, `youngs_modulus`,
    `poisson_ratio`, `mesh_ratio_median`. Verilirse aile/malzeme/mesh kıyası
    canlı çoğunluk yerine donmuş sete göre yapılır.
    """
    spec = spec or CorpusSpec()
    ref = reference or {}
    row = (
        db.query(AnalysisRun, Geometry)
        .join(Geometry, Geometry.id == AnalysisRun.geometry_id)
        .filter(AnalysisRun.id == run_id)
        .one_or_none()
    )
    if row is None:
        return RunVerdict(run_id, False, "missing_run", None, None, None, None, None, None)
    run, geo = row

    ratio = _u_over_L(run, geo)
    mesh_ratio = _mesh_ratio(run, geo)
    e, nu = _material_key(run)
    med = ref.get("mesh_ratio_median")
    deviation: float | None = None
    if mesh_ratio is not None and med:
        deviation = abs(mesh_ratio - float(med)) / float(med)

    def verdict(ok: bool, reason: str | None) -> RunVerdict:
        return RunVerdict(
            run_id=run.id,
            ok=ok,
            reason=reason,
            u_over_L=ratio,
            mesh_ratio=mesh_ratio,
            mesh_deviation=deviation,
            template_id=geo.template_id,
            youngs_modulus=e or None,
            poisson_ratio=nu,
        )

    if run.status != "solved":
        return verdict(False, "not_solved")
    reason = _row_reject(run, geo, spec)
    if reason:
        return verdict(False, reason)

    want_template = ref.get("template_id") or spec.template_id
    if want_template and (geo.template_id or "") != want_template:
        return verdict(False, "other_template")

    ref_e = ref.get("youngs_modulus")
    if ref_e is not None and round(float(ref_e), -6) != e:
        return verdict(False, "other_material")

    if ratio is not None and ratio > spec.max_u_over_L:
        return verdict(False, "large_displacement")
    if deviation is not None and deviation > spec.mesh_ratio_band:
        return verdict(False, "mesh_outlier")
    return verdict(True, None)
