"""Donmuş eğitim seti (corpus manifest).

`select_training_runs` her çağrıda o anki veritabanına göre seçim yapar; yeni
bir run çözülünce set değişir ve iki eğitimin R²'si kıyaslanamaz. Manifest bu
listeyi dondurur: `run_id`'ler + süzgeç parametreleri + referans malzeme/mesh
değerleri bir JSON dosyasında durur, eğitim bu listeyi okur.

Manuel çözülen run'lar sete kendiliğinden girmez: `evaluate_run` karnesi
gösterilir, ekleme kullanıcının açık isteğiyle olur (`add_runs`). Süzgeci
geçmeyen bir run yalnız `override=True` ile eklenir ve gerekçesi manifeste
yazılır — araç karar vermez, kaydı şeffaf tutar.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.ml.corpus import CorpusSpec, RunVerdict, TrainingCorpus

MANIFEST_DIR = Path("uploads") / "models"
_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class ManifestError(ValueError):
    """Geçersiz manifest adı ya da bulunamayan manifest."""


def manifest_path(name: str, *, root: Path | None = None) -> Path:
    if not _NAME_RE.match(name or ""):
        raise ManifestError(
            "Manifest adı yalnız harf, rakam, nokta, alt çizgi ve tire içerebilir."
        )
    return (root or MANIFEST_DIR) / f"corpus_{name}.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def save_manifest(
    name: str,
    corpus: TrainingCorpus,
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    """Seçimi dondurur. Aynı ad tekrar dondurulursa üzerine yazar."""
    dest = manifest_path(name, root=root)
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "name": name,
        "frozen_at": _now(),
        "source": "auto_filter",
        "run_ids": list(corpus.run_ids),
        "template_id": corpus.template_id,
        "youngs_modulus": corpus.youngs_modulus,
        "poisson_ratio": corpus.poisson_ratio,
        "mesh_ratio_median": corpus.mesh_ratio_median,
        "spec": {
            "analysis_type": corpus.spec.analysis_type,
            "max_u_over_L": corpus.spec.max_u_over_L,
            "mesh_ratio_band": corpus.spec.mesh_ratio_band,
            "require_analytic_ok": corpus.spec.require_analytic_ok,
            "template_id": corpus.spec.template_id,
        },
        "dropped_at_freeze": dict(corpus.dropped),
        "flagged_at_freeze": dict(corpus.flagged),
        "manual_notes": {},
    }
    dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


def load_manifest(name: str, *, root: Path | None = None) -> dict[str, Any]:
    dest = manifest_path(name, root=root)
    if not dest.is_file():
        raise ManifestError(f"Manifest yok: {name}")
    return json.loads(dest.read_text(encoding="utf-8"))


def list_manifests(*, root: Path | None = None) -> list[dict[str, Any]]:
    base = root or MANIFEST_DIR
    if not base.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(base.glob("corpus_*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        out.append(
            {
                "name": data.get("name") or path.stem.removeprefix("corpus_"),
                "frozen_at": data.get("frozen_at"),
                "n_runs": len(data.get("run_ids") or []),
                "template_id": data.get("template_id"),
                "youngs_modulus": data.get("youngs_modulus"),
                "n_manual": len(data.get("manual_notes") or {}),
            }
        )
    return out


def spec_from_manifest(data: dict[str, Any]) -> CorpusSpec:
    raw = data.get("spec") or {}
    base = CorpusSpec()
    return CorpusSpec(
        template_id=raw.get("template_id") or data.get("template_id"),
        analysis_type=str(raw.get("analysis_type") or base.analysis_type),
        max_u_over_L=float(raw.get("max_u_over_L") or base.max_u_over_L),
        mesh_ratio_band=float(raw.get("mesh_ratio_band") or base.mesh_ratio_band),
        require_analytic_ok=bool(
            raw.get("require_analytic_ok")
            if raw.get("require_analytic_ok") is not None
            else base.require_analytic_ok
        ),
    )


def reference_from_manifest(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "template_id": data.get("template_id"),
        "youngs_modulus": data.get("youngs_modulus"),
        "poisson_ratio": data.get("poisson_ratio"),
        "mesh_ratio_median": data.get("mesh_ratio_median"),
    }


def add_runs(
    name: str,
    verdicts: list[RunVerdict],
    *,
    override: bool = False,
    root: Path | None = None,
) -> dict[str, Any]:
    """Karnesi verilen run'ları sete ekler.

    `override=False` iken süzgeci geçmeyenler eklenmez; hepsi `rejected`
    listesinde gerekçesiyle döner.
    """
    data = load_manifest(name, root=root)
    run_ids: list[int] = list(data.get("run_ids") or [])
    notes: dict[str, Any] = dict(data.get("manual_notes") or {})
    added: list[int] = []
    rejected: list[dict[str, Any]] = []
    skipped: list[int] = []

    for verdict in verdicts:
        if verdict.run_id in run_ids:
            skipped.append(verdict.run_id)
            continue
        if not verdict.ok and not override:
            rejected.append({"run_id": verdict.run_id, "reason": verdict.reason})
            continue
        run_ids.append(verdict.run_id)
        added.append(verdict.run_id)
        notes[str(verdict.run_id)] = {
            "added_at": _now(),
            "gate": "pass" if verdict.ok else "override",
            "reason": verdict.reason,
            "u_over_L": verdict.u_over_L,
            "mesh_deviation": verdict.mesh_deviation,
        }

    data["run_ids"] = sorted(run_ids)
    data["manual_notes"] = notes
    data["updated_at"] = _now()
    manifest_path(name, root=root).write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return {
        "name": name,
        "n_runs": len(data["run_ids"]),
        "added": added,
        "rejected": rejected,
        "already_present": skipped,
        "manifest": data,
    }
