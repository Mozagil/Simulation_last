"""Mesh yakınsama taraması (0.6.1).

Aynı geometri, artan çözünürlükte mesh: skaler hedeflerin (uç deplasmanı,
maks. von Mises) düğüm sayısıyla nasıl değiştiğini gösterir.

NEDEN AYRI BİR YOL: DOE (`doe/sampling.py`) geometriyi TARAR ve eleman
boyutunu LHS ile örnekler; yakınsama tam tersini ister — geometri sabit,
eleman boyutu verilen listeden sırayla. İkisini tek tabloya sıkıştırmak iki
farklı soruyu karıştırırdı. Ayrıca yakınsama tek bir Geometry kaydını
yeniden meshler (aynı OCC katısı), DOE ise her örnek için yeni geometri kurar
— aradaki fark yakınsama için kritiktir: geometri de değişirse ölçülen şey
mesh hatası olmaz.

NEDEN SURROGATE İÇİN ÖNEMLİ: `element_size` şu an skaler modelin girdi
vektöründe (`ml/scalar_features.py`). Yakınsamamış bir bantta veri
toplanırsa model ayrıklaştırma hatasını fizik sanıp öğrenir. Bu tarama,
DOE aralığını seçmeden önce hangi oran bandının kararlı olduğunu ÖLÇER.

Araç yakınsama KARARI vermez: ardışık sapmayı, en ince mesh'e göre sapmayı
ve (şablonda varsa) analitik referansı gösterir. Hangi mesh'in yeterli
olduğuna mühendis bakar.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.api.geometry import GenerateMeshRequest, generate_mesh
from app.api.solve import SolveBC, SolveRequest, solve_geometry
from app.doe.regions import bind_scenario_bcs, groups_by_name
from app.doe.runner import _NoopBackground
from app.models.material import Material, MaterialAssignment
from app.models.run import AnalysisRun
from app.templates import get_template
from app.templates.service import create_geometry_from_template

logger = logging.getLogger(__name__)

#: Yakınsaması izlenen skaler hedefler — surrogate'in de öğrendiği ikisi.
CONVERGENCE_TARGETS = ("max_displacement", "max_von_mises")


class ConvergenceError(ValueError):
    """Tarama tanımı bu şablonla çalıştırılamaz."""


class ConvergenceSpec(BaseModel):
    """Tek geometri + birden fazla mesh boyutu.

    `element_ratios` verilirse boyutlar şablonun karakteristik uzunluğuyla
    çarpılır (ankastre kirişte kesit kalınlığı) — geometri değişse bile aynı
    göreli çözünürlük anlamına gelir, DOE'nin `element_ratio` alanıyla aynı
    sözleşme.
    """

    template_id: str
    params: dict[str, Any] = Field(default_factory=dict)
    material_id: int
    #: Mutlak mm. `element_ratios` ile birlikte verilemez.
    element_sizes: list[float] | None = None
    #: es / karakteristik uzunluk. `element_sizes` ile birlikte verilemez.
    element_ratios: list[float] | None = None
    dimension: int = 3
    element_scheme: str = "tet"
    #: Bölge adıyla bağlı BC listesi. Verilmezse şablonun `default_bcs`'i.
    bcs: list[dict[str, Any]] | None = None
    name: str | None = None

    @model_validator(mode="after")
    def _check(self) -> "ConvergenceSpec":
        if (self.element_sizes is None) == (self.element_ratios is None):
            raise ValueError(
                "element_sizes VEYA element_ratios verilmeli (ikisi birden değil)."
            )
        values = self.element_sizes if self.element_sizes is not None else self.element_ratios
        assert values is not None
        if len(values) < 2:
            raise ValueError("Yakınsama için en az 2 mesh boyutu gerekir.")
        if any(v <= 0 for v in values):
            raise ValueError("Mesh boyutu/oranı pozitif olmalı.")
        if len(set(values)) != len(values):
            raise ValueError("Mesh boyutları birbirinden farklı olmalı.")
        if self.dimension not in (2, 3):
            raise ValueError("dimension 2 veya 3 olmalı.")
        if self.element_scheme.lower() not in ("tet", "quad", "mix"):
            raise ValueError("element_scheme tet | quad | mix olmalı.")
        return self


def resolve_steps(spec: ConvergenceSpec) -> list[dict[str, float | None]]:
    """Tarama basamakları, KABADAN İNCEYE sıralı.

    Sıra rastgele değil: `build_report` ardışık sapmayı bu sıraya göre
    hesaplar ve "en ince mesh" listenin sonudur.
    """
    template = get_template(spec.template_id)
    if spec.element_sizes is not None:
        steps = [{"ratio": None, "element_size": float(v)} for v in spec.element_sizes]
    else:
        params = template.parse_params(spec.params)
        steps = []
        for ratio in spec.element_ratios or []:
            size = template.element_size_for(params, float(ratio))
            if size is None:
                raise ConvergenceError(
                    f"Şablon '{spec.template_id}' karakteristik uzunluk tanımlamıyor; "
                    "element_ratios yerine element_sizes verin."
                )
            steps.append({"ratio": float(ratio), "element_size": float(size)})
    return sorted(steps, key=lambda s: -float(s["element_size"]))


def _pct(value: float | None, ref: float | None) -> float | None:
    if value is None or ref is None or abs(ref) < 1e-12:
        return None
    return 100.0 * (value - ref) / abs(ref)


def _target(row: dict[str, Any], key: str) -> float | None:
    raw = (row.get("scalars") or {}).get(key)
    try:
        return float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def build_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Kabadan inceye sıralı satırlara sapma sütunlarını ekler.

    İki sapma birden veriliyor çünkü ikisi farklı soruyu cevaplıyor:
    `delta_prev_pct` "bir adım incelttiğimde cevap ne kadar oynadı",
    `delta_finest_pct` "bu mesh en ince meshten ne kadar uzakta". Çözülemeyen
    satırlar (`status != solved`) sapma hesabında atlanır, satır olarak kalır.
    """
    solved = [r for r in rows if r.get("status") == "solved"]
    finest = solved[-1] if solved else None

    out_rows: list[dict[str, Any]] = []
    prev: dict[str, Any] | None = None
    for row in rows:
        enriched = dict(row)
        deltas: dict[str, dict[str, float | None]] = {}
        for key in CONVERGENCE_TARGETS:
            value = _target(row, key)
            deltas[key] = {
                "value": value,
                "delta_prev_pct": _pct(value, _target(prev, key)) if prev else None,
                "delta_finest_pct": (
                    _pct(value, _target(finest, key)) if finest is not None else None
                ),
            }
        enriched["targets"] = deltas
        out_rows.append(enriched)
        if row.get("status") == "solved":
            prev = row

    summary: dict[str, Any] = {}
    for key in CONVERGENCE_TARGETS:
        finest_value = _target(finest, key) if finest is not None else None
        # En ince iki mesh arasındaki sapma: taramanın bittiği noktadaki
        # belirsizliğin doğrudan ölçüsü.
        last_step_pct = None
        if len(solved) >= 2:
            last_step_pct = _pct(_target(solved[-1], key), _target(solved[-2], key))
        summary[key] = {
            "finest": finest_value,
            "finest_element_size": finest.get("element_size") if finest else None,
            "finest_node_count": finest.get("node_count") if finest else None,
            "last_step_delta_pct": last_step_pct,
        }

    return {
        "n_steps": len(rows),
        "n_solved": len(solved),
        "targets": list(CONVERGENCE_TARGETS),
        "summary": summary,
        "rows": out_rows,
    }


def _scaled_bcs(spec: ConvergenceSpec) -> list[dict[str, Any]]:
    template = get_template(spec.template_id)
    raw = spec.bcs if spec.bcs is not None else list(template.default_bcs)
    if not raw:
        raise ConvergenceError(
            f"Şablon '{spec.template_id}' varsayılan sınır koşulu tanımlamıyor; "
            "`bcs` alanını doldurun."
        )
    return [dict(bc) for bc in raw]


def run_convergence(db: Session, spec: ConvergenceSpec) -> dict[str, Any]:
    """Geometriyi bir kez kurar, her basamakta yeniden meshleyip çözer.

    Bir basamak patlarsa tarama durmaz — satır `failed` olarak kalır ve
    kalan basamaklar denenir (DOE runner'ıyla aynı davranış).
    """
    template = get_template(spec.template_id)
    steps = resolve_steps(spec)
    bcs_raw = _scaled_bcs(spec)

    mat = db.get(Material, spec.material_id)
    if mat is None:
        raise ConvergenceError(f"Malzeme yok: id={spec.material_id}")

    geo, _regions, _tess = create_geometry_from_template(db, spec.template_id, spec.params)
    db.add(MaterialAssignment(geometry_id=geo.id, part_id=0, material_id=spec.material_id))
    db.commit()

    groups = groups_by_name(db, geo.id)
    bound = bind_scenario_bcs(groups, bcs_raw)

    rows: list[dict[str, Any]] = []
    for i, step in enumerate(steps):
        size = float(step["element_size"])  # type: ignore[arg-type]
        row: dict[str, Any] = {
            "index": i,
            "element_size": size,
            "ratio": step["ratio"],
            "run_id": None,
            "status": "failed",
            "message": None,
            "node_count": None,
            "element_count": None,
            "scalars": {},
            "analytic": None,
        }
        try:
            mesh = generate_mesh(
                geo.id,
                GenerateMeshRequest(
                    element_size=size,
                    dimension=spec.dimension,
                    element_scheme=spec.element_scheme,
                ),
                db,
            )
            row["node_count"] = mesh.get("node_count")
            row["element_count"] = mesh.get("element_count")

            body = SolveRequest(
                dimension=spec.dimension,
                run_solver=True,
                wait=True,
                name=f"{spec.name or 'yakinsama'} · es={size:.3g}",
                element_size=size,
                element_scheme=spec.element_scheme,
                analysis_type="static",
                bcs=[SolveBC.model_validate(bc) for bc in bound],
            )
            result = solve_geometry(geo.id, body, _NoopBackground(), db)  # type: ignore[arg-type]
            row["run_id"] = result.get("run_id")
            row["status"] = str(result.get("status") or "failed")
            row["message"] = result.get("message")

            run = db.get(AnalysisRun, row["run_id"]) if row["run_id"] else None
            if run is not None:
                scalars = dict(run.scalars or {})
                row["analytic"] = scalars.pop("_analytic_comparison", None)
                row["scalars"] = scalars
                if scalars.get("node_count") is not None:
                    row["node_count"] = scalars["node_count"]
        except Exception as exc:  # noqa: BLE001 — bir basamak taramayı düşürmesin
            logger.warning("Yakınsama basamağı es=%.4g hata: %s", size, exc)
            row["message"] = str(exc)
        rows.append(row)

    report = build_report(rows)
    report["geometry_id"] = geo.id
    report["template_id"] = spec.template_id
    report["template_params"] = geo.template_params
    report["material"] = {
        "id": mat.id,
        "name": mat.name,
        "youngs_modulus": mat.youngs_modulus,
    }
    report["bcs"] = bound
    report["name"] = spec.name
    return report
