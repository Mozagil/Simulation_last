"""DOE sonuçlarında analitik sapma ve kaba aykırı değer taraması (0.5.5).

Sayıları gösterir; mesh/BC önerisi üretmez.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.doe import DoeCase, DoeStudy
from app.models.run import AnalysisRun

#: Rijit cisim / yakınsamama: referans vakada ~24 mm.
RIGID_DISP_MM = 1.0e5
#: Çok seyrek mesh göstergesi (tet10 referans ~7k düğüm; bunun altı dejenere).
MIN_NODES = 30


def classify_case(case: DoeCase, run: AnalysisRun | None) -> str:
    if case.status == "failed":
        return "failed"
    if case.status == "pending":
        return "pending"
    if run is None:
        return "missing_run"
    scalars = run.scalars or {}
    disp = scalars.get("max_displacement")
    nodes = scalars.get("node_count")
    try:
        if disp is not None and float(disp) > RIGID_DISP_MM:
            return "rigid_body"
    except (TypeError, ValueError):
        return "bad_scalars"
    try:
        if nodes is not None and float(nodes) < MIN_NODES:
            return "degenerate_mesh"
    except (TypeError, ValueError):
        return "bad_scalars"
    cmp_ = scalars.get("_analytic_comparison")
    if isinstance(cmp_, dict):
        if cmp_.get("skipped"):
            return "analytic_skipped"
        if cmp_.get("warned"):
            return "analytic_warn"
    if case.status in ("solved", "inp_only"):
        if case.status == "inp_only":
            return "inp_only"
        return "ok"
    return case.status or "unknown"


def scan_study(db: Session, study: DoeStudy) -> dict[str, Any]:
    cases = sorted(study.cases, key=lambda c: c.index)
    run_ids = [c.run_id for c in cases if c.run_id is not None]
    runs: dict[int, AnalysisRun] = {}
    if run_ids:
        for r in db.query(AnalysisRun).filter(AnalysisRun.id.in_(run_ids)):
            runs[r.id] = r

    flags: dict[str, list[int]] = {}
    for case in cases:
        run = runs.get(case.run_id) if case.run_id is not None else None
        label = classify_case(case, run)
        flags.setdefault(label, []).append(case.index)

    n = len(cases)
    n_ok = len(flags.get("ok", []))
    return {
        "study_id": study.id,
        "n_cases": n,
        "n_ok": n_ok,
        "counts": {k: len(v) for k, v in sorted(flags.items())},
        "flagged": {k: v for k, v in flags.items() if k != "ok"},
    }
