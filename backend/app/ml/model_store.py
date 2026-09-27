"""Skaler surrogate modellerinin ŞABLON BAŞINA saklanması.

NEDEN: modeller eskiden tek, global dosyadaydı (`uploads/models/
scalar_rf.joblib`, `scalar_loglinear.joblib`). Delikli plakayla "eğit"
demek kiriş modelinin ÜZERİNE YAZIYORDU — ve özellik vektörleri şablona
göre farklı olduğu için eski model başka şablonun girdisini okuyamaz.

Düzen: `uploads/models/<template_id>/scalar_<tür>.joblib`.

ESKİ DOSYALAR SİLİNMEZ, TAŞINMAZ. Şablon klasöründe model yoksa ve eski
global dosyanın korpusu O şablona aitse (bundle `corpus.template_id`),
eski dosya salt okunur yedek olarak döner. Bugünkü diskte eski dosyaların
ikisi de `kiris-v2` korpusundan, yani yalnız `cantilever_beam` için.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import joblib

MODELS_ROOT = Path("uploads") / "models"

#: tür -> dosya adı. Eski global dosyalarla AYNI adlar (yedek okuma için).
KIND_FILES: dict[str, str] = {
    "rf": "scalar_rf.joblib",
    "loglinear": "scalar_loglinear.joblib",
    "hybrid": "scalar_hybrid.joblib",
}

_TEMPLATE_RE = re.compile(r"^[a-z0-9_]{1,64}$")


class ModelStoreError(ValueError):
    """Geçersiz şablon adı ya da model türü."""


def _check(template_id: str, kind: str) -> None:
    if not _TEMPLATE_RE.match(template_id or ""):
        raise ModelStoreError(f"Geçersiz şablon adı: {template_id!r}")
    if kind not in KIND_FILES:
        raise ModelStoreError(
            f"Bilinmeyen model türü {kind!r} (geçerli: {', '.join(KIND_FILES)})"
        )


#: NLGEOM (büyük deformasyon) modelleri lineerden AYRI klasörde: iki farklı
#: fizik, aynı dosyaya yazılsa biri diğerini ezer (TODO 4).
NLGEOM_DIR = "nlgeom"


def model_path(
    template_id: str, kind: str, *, root: Path | None = None, nlgeom: bool = False
) -> Path:
    _check(template_id, kind)
    base = (root or MODELS_ROOT) / template_id
    if nlgeom:
        base = base / NLGEOM_DIR
    return base / KIND_FILES[kind]


def save_model(
    template_id: str,
    kind: str,
    bundle: dict[str, Any],
    *,
    root: Path | None = None,
    nlgeom: bool = False,
) -> Path:
    dest = model_path(template_id, kind, root=root, nlgeom=nlgeom)
    dest.parent.mkdir(parents=True, exist_ok=True)
    bundle["template_id"] = template_id
    bundle["nlgeom"] = bool(nlgeom)
    joblib.dump(bundle, dest)
    return dest


def _bundle_template(bundle: dict[str, Any]) -> str | None:
    if bundle.get("template_id"):
        return str(bundle["template_id"])
    corpus = bundle.get("corpus") or {}
    return corpus.get("template_id")


def load_model(
    template_id: str, kind: str, *, root: Path | None = None, nlgeom: bool = False
) -> dict[str, Any] | None:
    """Şablonun modeli; yoksa ve eşleşiyorsa eski global dosya; yoksa None.

    NLGEOM modeli yalnız kendi klasöründen okunur — lineer dosyaya DÜŞMEZ:
    sessizce yanlış fiziğin modelini kullanmak, "model yok"tan kötü.
    """
    dest = model_path(template_id, kind, root=root, nlgeom=nlgeom)
    if dest.is_file():
        return joblib.load(dest)
    if nlgeom:
        return None
    legacy = (root or MODELS_ROOT) / KIND_FILES[kind]
    if legacy.is_file():
        bundle = joblib.load(legacy)
        if _bundle_template(bundle) == template_id:
            bundle.setdefault("legacy_path", str(legacy))
            return bundle
    return None


def list_models(*, root: Path | None = None) -> dict[str, list[str]]:
    """Şablon -> mevcut model türleri (eski dosyalar dahil)."""
    base = root or MODELS_ROOT
    out: dict[str, list[str]] = {}
    if base.is_dir():
        for sub in sorted(p for p in base.iterdir() if p.is_dir()):
            if not _TEMPLATE_RE.match(sub.name):
                continue
            kinds = [k for k, f in KIND_FILES.items() if (sub / f).is_file()]
            if kinds:
                out[sub.name] = kinds
            nl = [k for k, f in KIND_FILES.items() if (sub / NLGEOM_DIR / f).is_file()]
            if nl:
                out[f"{sub.name}/{NLGEOM_DIR}"] = nl
        for kind, fname in KIND_FILES.items():
            legacy = base / fname
            if not legacy.is_file():
                continue
            tpl = _bundle_template(joblib.load(legacy))
            if tpl and _TEMPLATE_RE.match(tpl) and kind not in out.get(tpl, []):
                out.setdefault(tpl, []).append(kind)
    return out


# --- Alan modeli (GNN) --------------------------------------------------------
# Aynı sorun GNN'de de vardı (TODO 1.3b "kapsam"): `/gnn/train` şablona göre
# süzüyor ama sonucu hep `uploads/models/field_gnn.npz`'ye yazıyordu — plaka
# eğitimi kiriş modelini eziyordu. Dosya biçimi joblib değil `.npz` + `.json`
# (`ml/gnn.save_gnn`); düzen skalerlerle aynı: `<template_id>/field_gnn.npz`.

GNN_FILE = "field_gnn.npz"


def gnn_path(template_id: str, *, root: Path | None = None) -> Path:
    if not _TEMPLATE_RE.match(template_id or ""):
        raise ModelStoreError(f"Geçersiz şablon adı: {template_id!r}")
    return (root or MODELS_ROOT) / template_id / GNN_FILE


def load_template_gnn(
    template_id: str, *, root: Path | None = None
) -> dict[str, Any] | None:
    """Şablonun GNN'i; yoksa ve eşleşiyorsa eski global dosya; yoksa None.

    Eski global dosya YALNIZ meta'sındaki şablon bu şablonsa döner. Şablon
    kaydı olmayan eski dosya hiçbir şablona verilmez — hangi veriyle
    eğitildiği bilinmiyor.
    """
    from app.ml.gnn import load_gnn

    dest = gnn_path(template_id, root=root)
    if dest.is_file():
        return load_gnn(dest)
    legacy = (root or MODELS_ROOT) / GNN_FILE
    bundle = load_gnn(legacy) if legacy.is_file() else None
    if bundle is not None and _bundle_template(bundle) == template_id:
        bundle.setdefault("legacy_path", str(legacy))
        return bundle
    return None
