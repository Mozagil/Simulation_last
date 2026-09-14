"""FEA skalerleri ile şablonun kapalı form çözümünü karşılaştırır (0.4.5).

Karşılaştırma mühendise öneri üretmez: sapmayı ve eşiğin aşılıp aşılmadığını
gösterir. Eşik, mesh yetersizliği veya yanlış BC'yi erken yakalamak içindir.
"""

from __future__ import annotations

import math
from typing import Any

from pydantic import ValidationError

from app.templates import UnknownTemplateError, get_template
from app.templates.base import AnalyticInput

#: Göreli sapma eşiği (abs(FEA-analitik)/|analitik|).
#: Deplasman: referans ankastre vakada ~%0.5.
#: von Mises: köşe tekilliği nedeniyle aynı vakada ~%10; eşiği onun üstünde.
REL_WARN_THRESHOLD: dict[str, float] = {
    "max_displacement": 0.10,
    "max_von_mises": 0.20,
}

_METRIC_META: dict[str, tuple[str, str]] = {
    "max_displacement": ("Max deplasman", "mm"),
    "max_von_mises": ("Max von Mises", "MPa"),
}

_COMPARE_KEYS = tuple(_METRIC_META)


def cload_resultant_n(bcs: list[dict[str, Any]]) -> float | None:
    """CLOAD kuvvetlerinin büyüklük toplamı (N). CLOAD yoksa None."""
    total = 0.0
    found = False
    for bc in bcs:
        if str(bc.get("type") or "").lower() != "cload":
            continue
        fx = float(bc.get("fx") or 0.0)
        fy = float(bc.get("fy") or 0.0)
        fz = float(bc.get("fz") or 0.0)
        mag = math.sqrt(fx * fx + fy * fy + fz * fz)
        if mag == 0.0:
            raw = bc.get("magnitude")
            if raw is not None:
                mag = abs(float(raw))
        if mag > 0.0:
            found = True
            total += mag
    return total if found else None


def first_pressure_mpa(bcs: list[dict[str, Any]]) -> float | None:
    """İlk Pressure BC büyüklüğü (MPa = N/mm²). Pressure yoksa None."""
    for bc in bcs:
        if str(bc.get("type") or "").lower() != "pressure":
            continue
        raw = bc.get("magnitude")
        if raw is None:
            continue
        mag = abs(float(raw))
        if mag > 0.0:
            return mag
    return None


def _youngs_and_poisson(materials: list[dict[str, Any]]) -> tuple[float | None, float]:
    if not materials:
        return None, 0.3
    first = materials[0]
    e = first.get("youngs_modulus")
    nu = first.get("poisson_ratio")
    e_val = float(e) if e is not None else None
    nu_val = float(nu) if nu is not None else 0.3
    if e_val is not None and e_val <= 0:
        e_val = None
    return e_val, nu_val


def _rel_error(fea: float, analytic: float) -> float | None:
    if analytic == 0.0:
        return 0.0 if fea == 0.0 else None
    return abs(fea - analytic) / abs(analytic)


def _skip(template_id: str, reason: str) -> dict[str, Any]:
    return {
        "template_id": template_id,
        "skipped": True,
        "reason": reason,
        "warned": False,
        "metrics": [],
    }


def build_analytic_comparison(
    *,
    template_id: str | None,
    template_params: dict[str, Any] | None,
    materials: list[dict[str, Any]],
    bcs: list[dict[str, Any]],
    analysis_type: str,
    fea_scalars: dict[str, Any],
) -> dict[str, Any] | None:
    """Karşılaştırma sözlüğü veya gösterilecek bir şey yoksa None.

    None: şablon yok / analitik yok / modal / FEA skalerleri yok.
    skipped=True: şablon var ama CLOAD/Pressure/E eksik veya parametre geçersiz.
    """
    if not template_id:
        return None
    try:
        template = get_template(template_id)
    except UnknownTemplateError:
        return None
    if template.analytic is None:
        return None
    if (analysis_type or "static").lower() == "modal":
        return None
    if not any(k in fea_scalars for k in _COMPARE_KEYS):
        return None

    force = cload_resultant_n(bcs)
    press = first_pressure_mpa(bcs)
    if force is None and press is None:
        return _skip(template_id, "Analitik karşılaştırma için CLOAD veya Pressure gerekli.")
    e_pa, nu = _youngs_and_poisson(materials)
    if e_pa is None:
        return _skip(template_id, "Analitik karşılaştırma için malzeme E değeri gerekli.")

    try:
        params = template.parse_params(template_params or {})
    except ValidationError as exc:
        return _skip(template_id, f"Şablon parametreleri geçersiz: {exc}")

    analytic = template.analytic(
        params,
        AnalyticInput(
            force_n=force or 0.0,
            youngs_modulus_pa=e_pa,
            poisson_ratio=nu,
            pressure_mpa=press or 0.0,
        ),
    )

    metrics: list[dict[str, Any]] = []
    warned = False
    for key in _COMPARE_KEYS:
        if key not in analytic or key not in fea_scalars:
            continue
        try:
            ana_v = float(analytic[key])
            fea_v = float(fea_scalars[key])
        except (TypeError, ValueError):
            continue
        rel = _rel_error(fea_v, ana_v)
        if rel is None:
            continue
        threshold = REL_WARN_THRESHOLD[key]
        warn = rel > threshold
        warned = warned or warn
        label, unit = _METRIC_META[key]
        metrics.append(
            {
                "key": key,
                "label": label,
                "unit": unit,
                "analytic": ana_v,
                "fea": fea_v,
                "rel_error": rel,
                "threshold": threshold,
                "warn": warn,
            }
        )

    if not metrics:
        return None
    return {
        "template_id": template_id,
        "skipped": False,
        "reason": None,
        "warned": warned,
        "metrics": metrics,
    }


def store_comparison_on_scalars(
    scalars: dict[str, Any],
    comparison: dict[str, Any] | None,
) -> None:
    if comparison is not None:
        scalars["_analytic_comparison"] = comparison
