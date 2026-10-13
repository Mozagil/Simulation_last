"""LS-DYNA *MAT_024 → crash malzeme / kanun parametreleri — 1.21c.

Çıktı adaptörün zaten okuduğu alanlar: `materials` (parça başına ρ, E, ν;
SI) ve `parts[].model` (CrashModelParams). Kart yazılmaz.

Eşleme (*MAT_024, piecewise linear plasticity):
- LCSS bir *DEFINE_CURVE ise → LAW36 (tabulated), tek eğri (ε̇ = 0).
- LCSS yok, EPS1..8 / ES1..8 dolu → aynı noktalarla LAW36.
- İkisi de yok → SIGY + ETAN doğrusal sertleşme, LAW2 ile birebir:
  a = SIGY, b = E·ETAN / (E − ETAN), n = 1.
- FAIL (> 0, 1e20 altı) → EPS_p_max. Varsayılan 1e21 / 0 → kopma yok.
- Hız etkisi (1.21c-3): mühendis şekil değiştirme hızlarını (1/s) verirse
  LAW36 çok eğri olur: ε̇ = 0'da statik eğri, her hızda σ·k(ε̇).
  LCSR verilmişse k = LCSR(ε̇) (doğrusal ara/dış değer; C/P yok sayılır),
  yoksa Cowper–Symonds k = 1 + (ε̇/C)^(1/P). SIGY + ETAN'lı malzeme bu
  durumda iki noktalı eğri olur: (0, SIGY), (1, SIGY + b). VP 0 → LAW36
  toplam hız, VP 1 → plastik hız. Hız listesi yoksa C/P / LCSR uyarıya düşer.
Çevrilmeyenler (uyarıyla): LCSS'in tablo olması, FAIL < 0, TDEL, VP ∉ {0, 1}.

*MAT_001 (elastik) → LAW1. DA / DB / K çevrilmez (uyarı).
*MAT_020 (rijit) → part'a /RBODY (`rigid_bodies`, part seçimi) + ρ, E, ν
ile LAW1 (elemanlar deck'te kalır). CMO = 1: CON1 (öteleme) ve CON2
(dönme) kodları global eksende ana düğüme /BCS olur (0 serbest, 1 x,
2 y, 3 z, 4 x+y, 5 y+z, 6 z+x, 7 hepsi). CMO = −1 (yerel sistem) çevrilmez.

Birim: keyword dosyası birim taşımaz; kütle / uzunluk / zaman çarpanları
mühendisten gelir, gerilme ve yoğunluk çarpanı bunlardan türetilir.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
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


def _interp(points: list[tuple[float, float]], x: float) -> float:
    """Doğrusal ara değer; aralık dışında uç parçalardan doğrusal uzatma."""
    if len(points) == 1:
        return points[0][1]
    pts = sorted(points)
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x <= x1 or (x1, y1) == pts[-1]:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return pts[-1][1]  # erişilmez


def _rate_curves(
    mat: DynaMat024,
    model: DynaModel,
    fields: dict[str, Any],
    rates_per_s: Sequence[float],
    units: DynaUnits,
    s_mpa: float,
) -> tuple[dict[str, Any], str]:
    """Statik kanunu hızlara göre LAW36 çok eğriye açar; çevrilemezse ValueError."""
    if fields["law"] == "tabulated":
        base = list(fields["tab_curves"][0]["points"])
    else:
        sy = fields["sigma_y_pa"] * 1e-6
        base = [(0.0, sy), (1.0, sy + fields["harden_b_mpa"])]
    if mat.lcsr:
        curve = model.curves.get(mat.lcsr)
        if curve is None or not curve.points:
            raise ValueError(f"LCSR {mat.lcsr} *DEFINE_CURVE değil")
        # Eğri apsisi dosya biriminde hız (1/zaman)
        def k(r: float) -> float:
            return _interp(curve.points, r * units.time_to_s)
        how = f"LCSR {mat.lcsr}"
    else:
        c_per_s = mat.c / units.time_to_s

        def k(r: float) -> float:
            return 1.0 + (r / c_per_s) ** (1.0 / mat.p)
        how = f"Cowper–Symonds C={c_per_s:g} 1/s, P={mat.p:g}"
    curves = [{"eps_dot_per_s": 0.0, "points": base}]
    for r in rates_per_s:
        factor = k(r)
        if not math.isfinite(factor) or factor <= 0:
            raise ValueError(f"ε̇ = {r:g} 1/s için ölçek {factor:g}")
        curves.append({"eps_dot_per_s": r, "points": [(x, y * factor) for x, y in base]})
    out = {key: v for key, v in fields.items() if key not in ("sigma_y_pa", "harden_b_mpa", "harden_n")}
    out.update({"law": "tabulated", "tab_curves": curves, "tab_vp": int(mat.vp)})
    rates = ", ".join(f"{r:g}" for r in rates_per_s)
    return out, f"{how}; {len(curves)} eğri (ε̇ = 0, {rates} 1/s)"


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
    model: DynaModel,
    mesh: DynaCrashMesh,
    units: DynaUnits,
    rates_per_s: Sequence[float] = (),
) -> DynaMaterialMap:
    """Mesh'teki her part için *MAT_001 / 020 / 024'ü kanun, malzeme, rijit
    gövde ve kısıt parametrelerine çevirir. `rates_per_s`: hız etkisi olan
    *MAT_024'ler için LAW36 eğri hızları (mühendis girer; boş = hız etkisi yok)."""
    rates = sorted({float(r) for r in rates_per_s})
    if any(not math.isfinite(r) or r <= 0 for r in rates):
        raise DynaMaterialError("Şekil değiştirme hızları pozitif olmalı (1/s).")
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
            has_rate = bool(mat.lcsr or (mat.c > 0 and mat.p > 0))
            try:
                fields, source = _hardening(mat, model, s_mpa)
                if 0 < mat.fail < _NO_FAIL:
                    fields["eps_p_max"] = mat.fail
                if has_rate and rates and mat.vp in (0, 1):
                    fields, rate_note = _rate_curves(mat, model, fields, rates, units, s_mpa)
                    source = f"{source} + {rate_note}"
                validated = CrashModelParams.model_validate(fields)
            except (ValueError, ValidationError) as exc:
                msg = exc.errors()[0]["msg"] if isinstance(exc, ValidationError) else str(exc)
                row["note"] = f"çevrilemedi: {msg}"
                out.unassigned.append(part.pid)
                continue
            notes = []
            if has_rate and not rates:
                notes.append(
                    (f"LCSR {mat.lcsr}" if mat.lcsr else f"Cowper–Symonds C={mat.c:g}, P={mat.p:g}")
                    + " (hız listesi verilmedi — hız etkisi yok)"
                )
            elif has_rate and mat.vp not in (0, 1):
                notes.append(f"hız etkisi VP={mat.vp:g} ile (yalnız 0 / 1)")
            elif mat.lcsr and (mat.c or mat.p):
                notes.append(f"C={mat.c:g}, P={mat.p:g} (LCSR öncelikli)")
            elif not has_rate and (mat.c or mat.p):
                notes.append(f"Cowper–Symonds C={mat.c:g}, P={mat.p:g} (eksik)")
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
