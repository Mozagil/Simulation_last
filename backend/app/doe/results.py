"""DOE çalışmasının skaler sonuç tablosu (0.5.5 okuma tarafı).

Tek tek run'lara girip deformasyon/von Mises konturuna bakmak bir örnek için
yeterli; 200 örneklik bir sette hangi parametre bölgesinin ne ürettiğini ancak
tablo halinde görmek mümkün. Bu modül her örnek için TEK SATIR üretir:
parametreler + skalerler + analitik sapma + kalite etiketi.

DB'ye yazmaz, türetilmiş görünümdür — kalite etiketi `quality.classify_case`
ile aynı sınıflandırmayı kullanır ki tablo ile özet sayılar çelişmesin.
"""

from __future__ import annotations

import math
from typing import Any

from sqlalchemy.orm import Session

from app.doe.quality import classify_case
from app.models.doe import DoeCase, DoeStudy
from app.models.run import AnalysisRun

#: Tabloda gösterilen skalerler: anahtar -> başlık
SCALAR_COLUMNS = {
    "max_displacement": "Deplasman maks [mm]",
    "max_von_mises": "VM maks [MPa]",
    "node_count": "Düğüm",
}


def _num(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _analytic(scalars: dict[str, Any]) -> dict[str, Any]:
    """Analitik karşılaştırmayı `_analytic_comparison.metrics`'ten okur.

    Yapı (bkz. `templates/compare.py`):
        {"skipped": bool, "reason": str|None, "warned": bool,
         "metrics": [{"key": "max_displacement", "analytic": …, "fea": …,
                      "rel_error": 0.167, ...}]}

    `rel_error` İŞARETSİZDİR; tabloda yönü görmek istiyoruz (FEA analitikten
    yukarıda mı aşağıda mı), o yüzden işaretli sapmayı analytic/fea'den
    yeniden hesaplıyoruz.
    """
    out: dict[str, Any] = {
        "dev_displacement_pct": None,
        "dev_von_mises_pct": None,
        "analytic_skipped": None,
    }
    cmp_ = scalars.get("_analytic_comparison")
    if not isinstance(cmp_, dict):
        return out
    if cmp_.get("skipped"):
        out["analytic_skipped"] = cmp_.get("reason") or "karşılaştırma atlandı"
        return out

    field = {"max_displacement": "dev_displacement_pct", "max_von_mises": "dev_von_mises_pct"}
    for metric in cmp_.get("metrics") or []:
        target = field.get(metric.get("key"))
        if target is None:
            continue
        ana = _num(metric.get("analytic"))
        fea = _num(metric.get("fea"))
        if ana not in (None, 0.0) and fea is not None:
            out[target] = (fea - ana) / ana * 100.0
        else:
            # Analitik sıfır/okunamaz: işaretsiz göreli hatayı kullan.
            rel = _num(metric.get("rel_error"))
            out[target] = rel * 100.0 if rel is not None else None
    return out


def study_results(db: Session, study: DoeStudy) -> dict[str, Any]:
    cases: list[DoeCase] = sorted(study.cases, key=lambda c: c.index)
    run_ids = [c.run_id for c in cases if c.run_id is not None]
    runs: dict[int, AnalysisRun] = {}
    if run_ids:
        for r in db.query(AnalysisRun).filter(AnalysisRun.id.in_(run_ids)):
            runs[r.id] = r

    # Parametre sütunları: örnekler arasında DEĞİŞENLER önce gelsin — sabit
    # tutulan parametreyi her satırda okumak tabloyu gereksiz genişletiyor.
    all_keys: list[str] = []
    for case in cases:
        for key in case.geometry_params or {}:
            if key not in all_keys:
                all_keys.append(key)
    varying = [
        k for k in all_keys if len({str((c.geometry_params or {}).get(k)) for c in cases}) > 1
    ]
    constant = {
        k: (cases[0].geometry_params or {}).get(k) for k in all_keys if k not in varying
    } if cases else {}

    rows: list[dict[str, Any]] = []
    for case in cases:
        run = runs.get(case.run_id) if case.run_id is not None else None
        scalars = (run.scalars if run else None) or {}
        row: dict[str, Any] = {
            "index": case.index,
            "run_id": case.run_id,
            "geometry_id": case.geometry_id,
            "status": case.status,
            "quality": classify_case(case, run),
            "element_size": case.element_size,
            "material_id": case.material_id,
            "scenario": case.scenario_name,
            "params": {k: (case.geometry_params or {}).get(k) for k in varying},
            "scalars": {k: _num(scalars.get(k)) for k in SCALAR_COLUMNS},
            "message": case.message,
        }
        row.update(_analytic(scalars))
        rows.append(row)

    return {
        "study_id": study.id,
        "template_id": study.template_id,
        "param_columns": varying,
        "constant_params": constant,
        "scalar_columns": dict(SCALAR_COLUMNS),
        "rows": rows,
        "stats": _stats(rows),
    }


def _stats(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Sütun başına min / ortalama / maks — dağılımı bir bakışta görmek için.

    Yalnız sayısal ve dolu değerler; çözülmemiş örnekler ortalamayı bozmasın
    diye None'lar atlanır.
    """
    out: dict[str, dict[str, float]] = {}
    keys = list(SCALAR_COLUMNS) + ["dev_displacement_pct", "dev_von_mises_pct"]
    for key in keys:
        values = [
            v
            for r in rows
            for v in [r["scalars"].get(key) if key in SCALAR_COLUMNS else r.get(key)]
            if isinstance(v, float)
        ]
        if not values:
            continue
        out[key] = {
            "min": min(values),
            "mean": sum(values) / len(values),
            "max": max(values),
            "n": float(len(values)),
        }
    return out
