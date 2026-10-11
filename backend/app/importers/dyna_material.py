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

*MAT_001 (elastik) → LAW1. DA / DB / K çevrilmez (uyarı).
*MAT_020 (rijit) → part'a /RBODY (`rigid_bodies`, part seçimi) + ρ, E, ν
ile LAW1 (elemanlar deck'te kalır). CMO = 1: CON1 (öteleme) ve CON2
(dönme) kodları global eksende ana düğüme /BCS olur (0 serbest, 1 x,
2 y, 3 z, 4 x+y, 5 y+z, 6 z+x, 7 hepsi). CMO = −1 (yerel sistem) çevrilmez.

Birim: keyword dosyası birim taşımaz; kütle / uzunluk / zaman çarpanları
mühendisten gelir, gerilme ve yoğunluk çarpanı bunlardan türetilir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from app.importers.dyna_k import DynaMat024, DynaMatRigid, DynaModel
from app.importers.dyna_mesh import DynaCrashMesh
from app.solvers.crash_params import CrashModelParams

_NO_FAIL = 1.0e20
# *MAT_020 CON1 / CON2 kodu → kilitli eksenler (x y z)
_CON_DOFS = {0: "000", 1: "100", 2: "010", 3: "001", 4: "110", 5: "011", 6: "101", 7: "111"}


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
    rigid_bodies: list[dict[str, Any]] = field(default_factory=list)
    boundary_conditions: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def apply(self, params: dict[str, Any]) -> dict[str, Any]:
        """Adaptör parametrelerine malzemeleri ve parça kanunlarını ekler."""
        params["materials"] = [dict(m) for m in self.materials]
        specs = {int(s["part_id"]): s for s in params.setdefault("parts", [])}
        for part_id, model in self.part_models.items():
            specs.setdefault(part_id, {"part_id": part_id})["model"] = dict(model)
            if specs[part_id] not in params["parts"]:
                params["parts"].append(specs[part_id])
        params.setdefault("rigid_bodies", []).extend(dict(r) for r in self.rigid_bodies)
        params.setdefault("boundary_conditions", []).extend(
            dict(b) for b in self.boundary_conditions
        )
        return params

    def report(self) -> dict[str, Any]:
        return {
            "parts": [dict(p) for p in self.parts],
            "unassigned": list(self.unassigned),
            "rigid_bodies": [dict(r) for r in self.rigid_bodies],
            "boundary_conditions": [dict(b) for b in self.boundary_conditions],
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


def _rigid(out: DynaMaterialMap, pid: int, part_id: int, rg: DynaMatRigid) -> None:
    name = f"rigid_part_{pid}"
    out.rigid_bodies.append({"name": name, "part_id": part_id})
    if rg.cmo == 1:
        c1, c2 = int(rg.con1), int(rg.con2)
        if c1 != rg.con1 or c2 != rg.con2 or c1 not in _CON_DOFS or c2 not in _CON_DOFS:
            out.warnings.append(f"part {pid}: CON1={rg.con1:g}, CON2={rg.con2:g} çevrilmedi")
            return
        dofs = _CON_DOFS[c1] + _CON_DOFS[c2]
        if "1" in dofs:
            out.boundary_conditions.append(
                {"name": f"{name}_con", "rigid_body": name, "dofs": dofs}
            )
    elif rg.cmo == -1:
        out.warnings.append(f"part {pid}: CMO=-1 (yerel sistem kısıtı) çevrilmedi")
    elif rg.cmo != 0:
        out.warnings.append(f"part {pid}: CMO={rg.cmo:g} çevrilmedi")


def to_crash_materials(
    model: DynaModel, mesh: DynaCrashMesh, units: DynaUnits
) -> DynaMaterialMap:
    """Mesh'teki her part için *MAT_001 / 020 / 024'ü kanun, malzeme, rijit
    gövde ve kısıt parametrelerine çevirir."""
    out = DynaMaterialMap()
    s_mpa = units.stress_to_pa * 1e-6
    for part in mesh.parts:
        row: dict[str, Any] = {
            "pid": part.pid,
            "mid": part.mid,
            "keyword": model.mat_keywords.get(part.mid),
            "law": None,
        }
        out.parts.append(row)
        if part.mid in model.mats_024:
            mat = model.mats_024[part.mid]
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
                out.warnings.append(
                    f"part {part.pid} / MID {mat.mid}: çevrilmedi — " + ", ".join(notes)
                )
            model_fields = validated.model_dump(include=set(fields) | {"law"})
            ro, e, pr, title = mat.ro, mat.e, mat.pr, mat.title
        elif part.mid in model.mats_001:
            el = model.mats_001[part.mid]
            if el.da or el.db or el.k:
                out.warnings.append(
                    f"part {part.pid} / MID {el.mid}: çevrilmedi — "
                    f"DA={el.da:g}, DB={el.db:g}, K={el.k:g}"
                )
            model_fields, source = {"law": "elastic"}, "elastik"
            ro, e, pr, title = el.ro, el.e, el.pr, el.title
        elif part.mid in model.mats_020:
            rg = model.mats_020[part.mid]
            model_fields, source = {"law": "elastic"}, "rijit gövde (/RBODY) + elastik"
            ro, e, pr, title = rg.ro, rg.e, rg.pr, rg.title
            _rigid(out, part.pid, part.part_id, rg)
        else:
            row["note"] = (
                f"*{row['keyword']} çevrilmedi" if row["keyword"] else f"MID {part.mid} dosyada yok"
            )
            out.unassigned.append(part.pid)
            continue
        row["law"] = model_fields["law"]
        row["note"] = source
        out.part_models[part.part_id] = model_fields
        out.materials.append(
            {
                "part_id": part.part_id,
                "name": title or f"{row['keyword']}_{part.mid}",
                "density": ro * units.density_to_kgm3,
                "youngs_modulus": e * units.stress_to_pa,
                "poisson_ratio": pr,
            }
        )
    if out.unassigned:
        out.warnings.append(f"Malzemesi çevrilmeyen part(lar): {out.unassigned}")
    return out
