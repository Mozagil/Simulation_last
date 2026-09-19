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


def model_path(template_id: str, kind: str, *, root: Path | None = None) -> Path:
    _check(template_id, kind)
    return (root or MODELS_ROOT) / template_id / KIND_FILES[kind]


def save_model(
    template_id: str, kind: str, bundle: dict[str, Any], *, root: Path | None = None
) -> Path:
    dest = model_path(template_id, kind, root=root)
    dest.parent.mkdir(parents=True, exist_ok=True)
    bundle["template_id"] = template_id
    joblib.dump(bundle, dest)
    return dest


def _bundle_template(bundle: dict[str, Any]) -> str | None:
    if bundle.get("template_id"):
        return str(bundle["template_id"])
    corpus = bundle.get("corpus") or {}
    return corpus.get("template_id")


def load_model(
    template_id: str, kind: str, *, root: Path | None = None
) -> dict[str, Any] | None:
    """Şablonun modeli; yoksa ve eşleşiyorsa eski global dosya; yoksa None."""
    dest = model_path(template_id, kind, root=root)
    if dest.is_file():
        return joblib.load(dest)
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
        for kind, fname in KIND_FILES.items():
            legacy = base / fname
            if not legacy.is_file():
                continue
            tpl = _bundle_template(joblib.load(legacy))
            if tpl and _TEMPLATE_RE.match(tpl) and kind not in out.get(tpl, []):
                out.setdefault(tpl, []).append(kind)
    return out
