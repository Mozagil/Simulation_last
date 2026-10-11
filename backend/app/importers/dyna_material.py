"""LS-DYNA *MAT_024 → crash malzeme / kanun parametreleri — 1.21c.

Çıktı adaptörün zaten okuduğu alanlar: `materials` (parça başına ρ, E, ν;
SI) ve `parts[].model` (CrashModelParams). Kart yazılmaz.

Eşleme (*MAT_024, piecewise linear plasticity):
- LCSS bir *DEFINE_CURVE ise → LAW36 (tabulated), tek eğri (ε̇ = 0).
- LCSS yok, EPS1..8 / ES1..8 dolu → aynı noktalarla LAW36.
- İkisi de yok → SIGY + ETAN doğrusal sertleşme, LAW2 ile birebir:
  a = SIGY, b = E·ETAN / (E − ETAN), n = 1.
- FAIL (> 0, 1e20 altı) → EPS_p_max. Varsayılan 1e21 / 0 → kopma yok.
Çevrilmeyenler (uyarıyla): Cowper–Symonds C/P, LCSR, LCSS'in tablo
olması, FAIL < 0, TDEL. Hız etkisi eklemek mühendisin kararı.

Birim: keyword dosyası birim taşımaz; kütle / uzunluk / zaman çarpanları
mühendisten gelir, gerilme ve yoğunluk çarpanı bunlardan türetilir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from app.importers.dyna_k import DynaMat024, DynaModel
from app.importers.dyna_mesh import DynaCrashMesh
from app.solvers.crash_params import CrashModelParams

_NO_FAIL = 1.0e20


class DynaMaterialError(ValueError):
    """Birim çarpanları geçersiz."""


@dataclass(frozen=True)
class DynaUnits:
    """Dosya birimi → SI çarpanları (örn. mm–t–s: 1, 1000, 1)."""

    length_to_mm: float
    mass_to_kg: float
    time_to_s: float

    def __post_init__(self) -> None:
        if min(self.length_to_mm, self.mass_to_kg, self.time_to_s) <= 0:
            raise DynaMaterialError("Birim çarpanları (uzunluk, kütle, zaman) pozitif olmalı.")

    @property
    def stress_to_pa(self) -> float:
        return self.mass_to_kg / ((self.length_to_mm * 1e-3) * self.time_to_s**2)

    @property
    def density_to_kgm3(self) -> float:
        return self.mass_to_kg / (self.length_to_mm * 1e-3) ** 3


@dataclass
class DynaMaterialMap:
    materials: list[dict[str, Any]] = field(default_factory=list)
    part_models: dict[int, dict[str, Any]] = field(default_factory=dict)
    parts: list[dict[str, Any]] = field(default_factory=list)  # rapor satırları
    unassigned: list[int] = field(default_factory=list)  # PID
    warnings: list[str] = field(default_factory=list)

    def apply(self, params: dict[str, Any]) -> dict[str, Any]:
        """Adaptör parametrelerine malzemeleri ve parça kanunlarını ekler."""
        params["materials"] = [dict(m) for m in self.materials]
        specs = {int(s["part_id"]): s for s in params.setdefault("parts", [])}
        for part_id, model in self.part_models.items():
            specs.setdefault(part_id, {"part_id": part_id})["model"] = dict(model)
            if specs[part_id] not in params["parts"]:
                params["parts"].append(specs[part_id])
        return params

    def report(self) -> dict[str, Any]:
        return {
            "parts": [dict(p) for p in self.parts],
            "unassigned": list(self.unassigned),
            "warnings": list(self.warnings),
        }


def _hardening(mat: DynaMat024, model: DynaModel, s_mpa: float) -> tuple[dict[str, Any], str]:
    """(model alanları, kaynak açıklaması); çevrilemezse ValueError."""
    if mat.lcss:
        curve = model.curves.get(mat.lcss)
        if curve is None:
            raise ValueError(f"LCSS {mat.lcss} *DEFINE_CURVE değil (tablo desteklenmiyor)")
        pts = [(x, y * s_mpa) for x, y in curve.points]
        return {"law": "tabulated", "tab_curves": [{"eps_dot_per_s": 0.0, "points": pts}]}, (
            f"LCSS eğri {mat.lcss} ({len(pts)} nokta)"
        )
    pts = [(e, s) for i, (e, s) in enumerate(zip(mat.eps, mat.es)) if i == 0 or e or s]
    if len(pts) >= 2 and any(s for _, s in pts):
        pts = [(e, s * s_mpa) for e, s in pts]
        return {"law": "tabulated", "tab_curves": [{"eps_dot_per_s": 0.0, "points": pts}]}, (
            f"EPS/ES ({len(pts)} nokta)"
        )
    if mat.sigy <= 0:
        raise ValueError("akma tanımı yok (LCSS, EPS/ES, SIGY boş)")
    if mat.etan >= mat.e:
        raise ValueError(f"ETAN ({mat.etan:g}) ≥ E ({mat.e:g})")
    b = mat.e * mat.etan / (mat.e - mat.etan)
    return {
        "law": "plastic",
        "sigma_y_pa": mat.sigy * s_mpa * 1e6,
        "harden_b_mpa": b * s_mpa,
        "harden_n": 1.0,
    }, f"SIGY + ETAN doğrusal (b = {b * s_mpa:.6g} MPa)"


def to_crash_materials(
    model: DynaModel, mesh: DynaCrashMesh, units: DynaUnits
) -> DynaMaterialMap:
    """Mesh'teki her part için *MAT_024'ü kanun + malzeme parametrelerine çevirir."""
    out = DynaMaterialMap()
    s_mpa = units.stress_to_pa * 1e-6
    for part in mesh.parts:
        row: dict[str, Any] = {"pid": part.pid, "mid": part.mid, "keyword": None, "law": None}
        out.parts.append(row)
        mat = model.mats_024.get(part.mid)
        if mat is None:
            row["keyword"] = model.mat_keywords.get(part.mid)
            row["note"] = (
                f"*{row['keyword']} çevrilmedi" if row["keyword"] else f"MID {part.mid} dosyada yok"
            )
            out.unassigned.append(part.pid)
            continue
        row["keyword"] = model.mat_keywords[part.mid]
        try:
            fields, source = _hardening(mat, model, s_mpa)
            if 0 < mat.fail < _NO_FAIL:
                fields["eps_p_max"] = mat.fail
            validated = CrashModelParams.model_validate(fields)
        except (ValueError, ValidationError) as exc:
            msg = exc.errors()[0]["msg"] if isinstance(exc, ValidationError) else str(exc)
            row["note"] = f"çevrilemedi: {msg}"
            out.unassigned.append(part.pid)
            continue
        row["law"] = validated.law
        row["note"] = source
        notes = []
        if mat.c or mat.p:
            notes.append(f"Cowper–Symonds C={mat.c:g}, P={mat.p:g}")
        if mat.lcsr:
            notes.append(f"LCSR {mat.lcsr}")
        if mat.fail < 0:
            notes.append(f"FAIL {mat.fail:g} (kullanıcı alt programı)")
        if mat.tdel:
            notes.append(f"TDEL {mat.tdel:g}")
        if notes:
            out.warnings.append(f"part {part.pid} / MID {mat.mid}: çevrilmedi — " + ", ".join(notes))
        out.part_models[part.part_id] = validated.model_dump(include=set(fields) | {"law"})
        out.materials.append(
            {
                "part_id": part.part_id,
                "name": mat.title or f"MAT_024_{mat.mid}",
                "density": mat.ro * units.density_to_kgm3,
                "youngs_modulus": mat.e * units.stress_to_pa,
                "poisson_ratio": mat.pr,
            }
        )
    if out.unassigned:
        out.warnings.append(f"Malzemesi çevrilmeyen part(lar): {out.unassigned}")
    return out
