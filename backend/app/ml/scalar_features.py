"""Çözülmüş run'lardan skaler eğitim tablosu (0.5.6).

Girdiler şablon parametreleri + eleman boyutu + malzeme + yük; hedefler
`max_displacement` ve `max_von_mises`. Alan modeli değildir.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from sqlalchemy.orm import Session

from app.models.geometry import Geometry
from app.models.run import AnalysisRun

#: Şablondan bağımsız kuyruk: mesh, malzeme, yük, boyut. Her şablonun
#: özellik vektörü = kendi sayısal parametreleri + (varsa) kategorik
#: göstergeleri + bu kuyruk.
COMMON_KEYS = (
    "element_size",
    "youngs_modulus",
    "poisson_ratio",
    "load_fx",
    "load_fy",
    "load_fz",
    "pressure_mpa",
    "dimension",
)

#: Kirişin şema alanları (length, thickness, width) + ortak kuyruk. Eski
#: global vektörle BİREBİR aynı — bu yüzden kaydedilmiş kiriş modelleri
#: ve `feature_keys` taşımayan eski bundle'lar bununla okunur.
#:
#: NEDEN ŞABLONA ÖZGÜ: eskiden bu vektör TÜM şablonlar için kullanılıyordu.
#: Delikli plakada `length=0` oluyor, `diameter` ve `height` hiç özellik
#: değildi — model delik çapını GÖREMİYORDU (plakada σ'yı belirleyen ana
#: parametre). Ölçüldü: şablona uygun özelliklerle log-log + RF artık
#: u'da %0.60 MAPE verdi (study 5, 198 örnek).
FEATURE_KEYS = ("length", "thickness", "width") + COMMON_KEYS


def template_param_keys(template_id: str | None) -> tuple[str, ...]:
    """Şablonun geometri özellikleri: sayısal alanlar (şema sırasıyla) +
    kategorik alanlar için `ad=seçenek` 0/1 göstergeleri.

    Şablon yoksa/bilinmiyorsa eski kiriş anahtarları (geriye uyum)."""
    if not template_id:
        return FEATURE_KEYS[:3]
    try:
        from app.templates import get_template

        props = get_template(template_id).params_schema().get("properties") or {}
    except Exception:  # noqa: BLE001 — bilinmeyen şablon: eski yol
        return FEATURE_KEYS[:3]
    keys: list[str] = [
        name for name, prop in props.items() if prop.get("type") in ("number", "integer")
    ]
    for name, prop in props.items():
        for option in prop.get("enum") or []:
            keys.append(f"{name}={option}")
    return tuple(keys)


def feature_keys_for(template_id: str | None) -> tuple[str, ...]:
    """Şablonun tam özellik vektörü anahtarları."""
    return template_param_keys(template_id) + COMMON_KEYS

#: Hedefler. `max_von_mises_away` kısıttan 1×T uzakta ölçülen gerilme
#: (bkz. postprocess/stress_probe.py). Ham `max_von_mises` ankastre
#: köşedeki TEKİLLİKTEN okunuyor; ölçtük: gürültü tabanı %5.57 ve
#: teoriden +%10 sapıyor. Maskeli ölçüm: %1.20 ve −%0.8. Ham değer
#: geriye uyumluluk ve karşılaştırma için tutuluyor.
TARGET_KEYS = ("max_displacement", "max_von_mises", "max_von_mises_away")


def _cload_components(bcs: list[dict[str, Any]]) -> tuple[float, float, float]:
    fx = fy = fz = 0.0
    for bc in bcs:
        if str(bc.get("type") or "").lower() != "cload":
            continue
        fx += float(bc.get("fx") or 0.0)
        fy += float(bc.get("fy") or 0.0)
        fz += float(bc.get("fz") or 0.0)
    return fx, fy, fz


def _pressure(bcs: list[dict[str, Any]]) -> float:
    for bc in bcs:
        if str(bc.get("type") or "").lower() != "pressure":
            continue
        raw = bc.get("magnitude")
        if raw is None:
            continue
        mag = abs(float(raw))
        if mag > 0.0:
            return mag
    return 0.0


def feature_values_from_run(
    run: AnalysisRun, geometry: Geometry | None
) -> dict[str, float] | None:
    """Run'ın tüm aday özellik değerleri (ad -> sayı). Malzeme E yoksa None."""
    params = (geometry.template_params if geometry is not None else None) or {}
    mats = run.materials_snapshot or []
    if not mats:
        return None
    m0 = mats[0]
    e = m0.get("youngs_modulus")
    nu = m0.get("poisson_ratio")
    if e is None:
        return None
    fx, fy, fz = _cload_components(list(run.bcs or []))
    values: dict[str, float] = {}
    for name, raw in params.items():
        if isinstance(raw, bool):
            continue
        if isinstance(raw, (int, float)):
            values[name] = float(raw)
        elif isinstance(raw, str):
            values[f"{name}={raw}"] = 1.0  # kategorik gösterge
    values.update(
        {
            "element_size": float(run.element_size or 0.0),
            "youngs_modulus": float(e),
            "poisson_ratio": float(nu if nu is not None else 0.3),
            "load_fx": fx,
            "load_fy": fy,
            "load_fz": fz,
            "pressure_mpa": _pressure(list(run.bcs or [])),
            "dimension": float(run.dimension),
        }
    )
    return values


def features_from_run(
    run: AnalysisRun,
    geometry: Geometry | None,
    keys: tuple[str, ...] | list[str] | None = None,
) -> np.ndarray | None:
    """Tek run için özellik vektörü; eksik malzeme varsa None.

    `keys` verilmezse run'ın ŞABLONUNUN anahtarları kullanılır. Anahtar
    run'da yoksa 0 (ör. seçilmemiş kategorik gösterge).
    """
    values = feature_values_from_run(run, geometry)
    if values is None:
        return None
    if keys is None:
        keys = feature_keys_for(geometry.template_id if geometry is not None else None)
    return np.asarray([float(values.get(k, 0.0)) for k in keys], dtype=np.float64)


def targets_from_run(run: AnalysisRun) -> np.ndarray | None:
    scalars = run.scalars or {}
    try:
        disp = float(scalars["max_displacement"])
        vm = float(scalars["max_von_mises"])
    except (KeyError, TypeError, ValueError):
        return None
    # Maskeli gerilme yoksa NaN — run TAMAMEN düşmesin. Şablonsuz ya da
    # backfill öncesi run'larda bu skaler olmayabilir; eğitim tarafı
    # hedef bazında maskeliyor, diğer iki hedef yine kullanılır.
    try:
        away = float(scalars["max_von_mises_away"])
    except (KeyError, TypeError, ValueError):
        away = float("nan")
    return np.asarray([disp, vm, away], dtype=np.float64)


def collect_scalar_table(
    db: Session,
    run_ids: list[int] | None = None,
    keys: tuple[str, ...] | None = None,
) -> tuple[np.ndarray, np.ndarray, list[int]]:
    """Çözülmüş statik run'lar → X, Y, run_id listesi.

    `run_ids` verilirse yalnız o küme (eğitim korpusu) alınır. `keys`
    verilmezse eski kiriş anahtarları — şablona özgü tablo için
    `collect_template_table` kullan.
    """
    keys = FEATURE_KEYS if keys is None else keys
    q = (
        db.query(AnalysisRun, Geometry)
        .join(Geometry, Geometry.id == AnalysisRun.geometry_id)
        .filter(AnalysisRun.status == "solved")
    )
    if run_ids is not None:
        if not run_ids:
            return (
                np.zeros((0, len(keys)), dtype=np.float64),
                np.zeros((0, len(TARGET_KEYS)), dtype=np.float64),
                [],
            )
        q = q.filter(AnalysisRun.id.in_(run_ids))
    rows = q.order_by(AnalysisRun.id).all()
    xs: list[np.ndarray] = []
    ys: list[np.ndarray] = []
    ids: list[int] = []
    for run, geo in rows:
        if (geo.template_id or "") == "":
            continue
        x = features_from_run(run, geo, keys)
        y = targets_from_run(run)
        if x is None or y is None:
            continue
        xs.append(x)
        ys.append(y)
        ids.append(run.id)
    if not xs:
        return (
            np.zeros((0, len(keys)), dtype=np.float64),
            np.zeros((0, len(TARGET_KEYS)), dtype=np.float64),
            [],
        )
    return np.vstack(xs), np.vstack(ys), ids


def features_from_dict(
    values: dict[str, Any], keys: tuple[str, ...] | list[str] | None = None
) -> np.ndarray:
    """Ad->değer sözlüğünden vektör. `keys` yoksa eski kiriş anahtarları."""
    keys = FEATURE_KEYS if keys is None else keys
    return np.asarray([float(values.get(k) or 0.0) for k in keys], dtype=np.float64)


class MixedTemplateError(ValueError):
    """Tek tabloda birden çok şablon — özellik vektörleri uyuşmaz."""


def collect_template_table(
    db: Session, run_ids: list[int]
) -> tuple[np.ndarray, np.ndarray, list[int], tuple[str, ...], str | None]:
    """Korpus → (X, Y, run_ids, feature_keys, template_id).

    Anahtarlar korpusun ŞABLONUNDAN gelir. Korpus tek şablonlu olmak
    zorunda (`select_training_runs` öyle seçer); karışıksa hata — farklı
    şablonların vektörleri aynı sütunları taşımaz.
    """
    templates = {
        t
        for (t,) in db.query(Geometry.template_id)
        .join(AnalysisRun, AnalysisRun.geometry_id == Geometry.id)
        .filter(AnalysisRun.id.in_(list(run_ids) or [-1]))
        .distinct()
        if t
    }
    if len(templates) > 1:
        raise MixedTemplateError(f"Korpusta birden çok şablon var: {sorted(templates)}")
    template_id = next(iter(templates), None)
    keys = feature_keys_for(template_id)
    X, Y, ids = collect_scalar_table(db, run_ids=run_ids, keys=keys)
    return X, Y, ids, keys, template_id
