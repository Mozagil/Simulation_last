"""Crash eğitim testleri PDF raporu — `crash_training_runs.py` sonuçlarından (training_runs.json).

Bölümler: özellik dizini (hangi kart / sınır koşulu hangi testte, hangi değerle) → model başına
Modelleme (geometri, mesh + görüntü, malzeme, parçalar, sınır koşulları, temas, kızak, yay, sönüm,
çarpma, çözüm / çıktı) → test başına adımlar, kurulum farkı, skaler tablo, kuvvet eğrileri üst üste,
fiziksel okuma (ne oldu + impuls / enerji / hourglass / kütle tutarlılık kontrolleri, sayılarla; öneri yok),
koşu başına enerji (toplam / kinetik / iç / temas / hourglass) ve son biçim görüntüsü.

    python -m scripts.crash_training_report [--api http://localhost:8001] [--out rapor.pdf]
"""

from __future__ import annotations

import argparse
import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.shapes import Drawing, Line, Polygon, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    CondPageBreak,
    KeepTogether,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.postprocess.cfd_report import _fonts
from scripts.crash_training_runs import MODELS, OUT, Api, plan

REPO = Path(__file__).resolve().parents[2]
TRAINING_TS = REPO / "frontend" / "src" / "docs" / "crashTraining.ts"
PALETTE = ["#1f77b4", "#d62728", "#2ca02c", "#ff7f0e", "#9467bd", "#8c564b", "#17becf", "#7f7f7f"]
PART_COLORS = ["#9ec5e8", "#f2b48a", "#a8d5a2", "#d9b8e8", "#f0d48a", "#c9c9c9"]

# Skaler tablo satırları: (anahtar, etiket, birim, ölçek)
SCALARS = [
    ("rwall_force_max", "Duvar Fmax", "kN", 1.0),
    ("rwall_impulse_final", "Duvar impulsu", "N·s", 1.0),
    ("internal_energy_final", "IE son", "J", 1.0),
    ("kinetic_energy_final", "KE son", "J", 1.0),
    ("kinetic_energy_max", "KE maks", "J", 1.0),
    ("contact_energy_final", "Temas enerjisi son", "J", 1.0),
    ("hourglass_energy_final", "HG son", "J", 1.0),
    ("hourglass_ratio", "HG / IE", "%", 100.0),
    ("energy_balance_rel", "Enerji dengesi (göreli)", "%", 100.0),
    ("elements_deleted", "Silinen eleman", "", 1.0),
    ("crush_max_mm", "Ezilme δ_maks", "mm", 1.0),
    ("mean_crush_force_kn", "Ort. ezilme kuvveti ∫F dδ/δ", "kN", 1.0),
    ("mean_crush_force_ie_kn", "Ort. ezilme kuvveti IE/δ", "kN", 1.0),
    ("model_disp_peak_mm", "Tepe |u|", "mm", 1.0),
    ("model_disp_peak_t_ms", "Tepe |u| zamanı", "ms", 1.0),
    ("springback_mm", "Geri sekme (mutlak)", "mm", 1.0),
    ("springback_def_mm", "Geri sekme (öteleme çıkarılmış)", "mm", 1.0),
    ("timestep_min", "Zaman adımı min", "ms", 1.0),
    ("mass_added_rel", "Eklenen kütle (göreli)", "%", 100.0),
]
#: Arial'da olmayan alt simge karakterleri
SUBS = str.maketrans({"ₚ": "p", "₀": "0", "₁": "1", "₂": "2", "ₜ": "t", "ₘ": "m"})
ENERGY = [("total_energy", "Toplam"), ("kinetic_energy", "Kinetik"), ("internal_energy", "İç"),
          ("contact_energy", "Temas"), ("hourglass_energy", "Hourglass")]


# ── Belge metni (Belgeler → Eğitim) ───────────────────────────────────────
def training_texts() -> dict[str, dict[str, str]]:
    """crashTraining.ts → {id: {title, area, learn, change, expect}} (adım listeleri betikte)."""
    src = TRAINING_TS.read_text(encoding="utf-8")
    out: dict[str, dict[str, str]] = {}
    for chunk in re.split(r'\n\s*id: "', src)[1:]:
        tid = chunk.split('"', 1)[0]
        rec = {"id": tid}
        for f in ("title", "area", "learn", "change", "expect", "observe"):
            mt = re.search(rf'\n\s*{f}: "((?:[^"\\]|\\.)*)"', chunk)
            if mt:
                rec[f] = mt.group(1).replace('\\"', '"')
        out[tid] = rec
    return out


# ── Biçim yardımcıları ────────────────────────────────────────────────────
def f(v: Any, d: int = 4) -> str:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        return "—"
    if v != 0 and (abs(v) >= 1e5 or abs(v) < 1e-3):
        return f"{v:.3g}"
    return f"{v:.{d}g}"


def vec(v: Any) -> str:
    return "(" + ", ".join(f(x, 4) for x in v) + ")" if isinstance(v, (list, tuple)) else "—"


def target(o: dict[str, Any]) -> str:
    if o.get("rigid_body"):
        return f"rijit gövde '{o['rigid_body']}' ana düğümü"
    if o.get("region"):
        return f"bölge '{o['region']}'"
    if o.get("part_id") is not None:
        return f"parça #{o['part_id']}"
    if o.get("point"):
        return f"nokta {vec(o['point'])}"
    return "tüm model"


ROLE = {"moving": "Hareketli (ilk hız)", "fixed": "Sabit (/BCS 111111)", "free": "Serbest"}
LAW = {"elastic": "LAW1 elastik", "plastic": "LAW2 Johnson–Cook", "tabulated": "LAW36 tablo"}


def material_text(mdl: dict[str, Any]) -> str:
    law = mdl.get("law", "plastic")
    s = LAW.get(law, law)
    if law == "plastic":
        a = mdl.get("sigma_y_pa")
        s += (f" · a = {f(a / 1e6) if a else 'kütüphane σy'} MPa · b = {f(mdl.get('harden_b_mpa', 0))} MPa"
              f" · n = {f(mdl.get('harden_n', 1))}")
        if mdl.get("jc_c"):
            s += f" · c = {f(mdl['jc_c'])}, ε̇₀ = {f(mdl.get('jc_eps_dot0_per_s', 0))} 1/s"
        if mdl.get("jc_m"):
            s += (f" · m = {f(mdl['jc_m'])}, T_melt = {f(mdl.get('jc_t_melt_k', 0))} K, "
                  f"T_r = {f(mdl.get('jc_t_r_k', 0))} K, ρCp = {f(mdl.get('jc_rho_cp', 0))}")
        if mdl.get("eps_p_max"):
            s += f" · EPS_p_max = {f(mdl['eps_p_max'])}"
    if law == "tabulated":
        for c in mdl.get("tab_curves") or []:
            s += " · σ–εₚ: " + " / ".join(f"{f(p[0])} {f(p[1])}" for p in c.get("points", []))
    fail = mdl.get("fail") or {}
    if fail.get("tensstrain"):
        t = fail["tensstrain"]
        s += f" · /FAIL/TENSSTRAIN ε_t1 {f(t.get('eps_t1', 0))}, ε_f1 {f(t.get('eps_f1', 0))}"
    if fail.get("johnson"):
        s += " · /FAIL/JOHNSON"
    sh = mdl.get("shell") or {}
    if sh.get("ishell"):
        s += f" · Ishell {sh['ishell']}"
    return s


def features(req: dict[str, Any]) -> list[tuple[str, str]]:
    """İstekteki her kart / sınır koşulu → (özellik, ayrıntı). Deck'e giden ne ise o."""
    out: list[tuple[str, str]] = []
    b = req.get("barrier") or {}
    if req.get("use_rigid_wall", True) and b.get("wall"):
        w = b["wall"]
        kind = "silindirik /RWALL/CYL" if w.get("kind") == "cyl" else "düzlem /RWALL"
        out.append(("Rijit duvar", f"{kind} · nokta {vec(w.get('point'))} · normal {vec(w.get('normal'))}"
                    + (f" · Ø {f(w.get('diameter_mm'))} mm" if w.get("diameter_mm") else "")
                    + (f" · açı {f(b.get('angle_deg'))}°" if b.get("angle_deg") else "")))
    elif not req.get("use_rigid_wall", True):
        out.append(("Duvarsız mod", "çarpışma yalnız temasla"))
    if b.get("speed_m_s") and not req.get("initial_velocities") and any(
            p.get("role") == "moving" for p in req.get("parts", [])):
        out.append(("İlk hız (/INIVEL)", f"{f(b['speed_m_s'])} m/s → Hareketli parçalar"
                    + (f" · yön {vec(b.get('direction'))}" if b.get("direction") else " · duvara dik")))
    for iv in req.get("initial_velocities") or []:
        out.append(("Parçaya ayrı ilk hız", f"{iv.get('name')}: {target(iv)} · {f(iv.get('speed_m_s'))} m/s · "
                    f"yön {vec(iv.get('direction'))}"))
    for p in req.get("parts") or []:
        if p.get("role") in ("fixed", "free"):
            out.append((f"Parça rolü: {ROLE[p['role']]}", f"parça #{p['part_id']}"))
        if p.get("model"):
            out.append(("Parça başına malzeme kartı", f"parça #{p['part_id']}: {material_text(p['model'])}"))
    for rb in req.get("rigid_bodies") or []:
        out.append(("Kızak / rijit gövde (/RBODY + kütle)", f"'{rb.get('name')}': {target(rb)} · ek kütle "
                    f"{f(rb.get('mass_kg', 0))} kg" + (" · HIC ivme kanalı" if rb.get("th_accel") else "")))
    for bc in req.get("boundary_conditions") or []:
        dofs = bc.get("dofs", "")
        name = "Ray (kızak yönlendirme, /BCS)" if bc.get("rigid_body") and dofs.count("0") == 1 else "Sınır koşulu (/BCS)"
        out.append((name, f"{bc.get('name')}: {target(bc)} · DOF {dofs} (Tx Ty Tz Rx Ry Rz; 1 = kilitli)"))
    for iv in req.get("imposed_velocities") or []:
        out.append(("Sabit hız (/IMPVEL)", f"{iv.get('name')}: {target(iv)} · {iv.get('direction')} "
                    f"{f(iv.get('velocity_m_s'))} m/s"))
    for am in req.get("added_masses") or []:
        out.append(("Ek kütle (/ADMAS)", f"{am.get('name')}: {target(am)} · {f(am.get('mass_kg'))} kg"))
    for c in req.get("contacts") or []:
        if c.get("all_parts"):
            out.append((f"Temas TYPE{c.get('type')} — Tüm model", "genel temas (öz temas dahil)"
                        + (f" · Iedge {c['iedge']}" if c.get("iedge") else "")))
        else:
            out.append((f"Temas TYPE{c.get('type')}",
                        f"ana #{c.get('master_part')} ↔ bağımlı #{c.get('slave_part')}"
                        + (" (öz temas)" if c.get("master_part") == c.get("slave_part") else "")
                        + (f" · μ {f(c['fric'])}" if c.get("fric") else "")))
    for s in req.get("springs") or []:
        out.append(("Yay (/SPRING + /PROP/TYPE4)", f"{s.get('name')}: A {target(s.get('end_a') or {})} ↔ "
                    f"B {target(s.get('end_b') or {})}{' sabit' if (s.get('end_b') or {}).get('fixed') else ''} · "
                    f"K {f(s.get('k_n_per_mm'))} N/mm · C {f(s.get('c_n_s_per_mm', 0))} N·s/mm"))
    d = req.get("damping")
    if d:
        out.append(("Rayleigh sönüm (/DAMP)", f"α {f(d.get('alpha_per_s', 0))} 1/s · β {f(d.get('beta_s', 0))} s · "
                    f"parçalar {d.get('part_ids') or 'tümü'} · {f(d.get('t_start_ms', 0))}–"
                    f"{f(d.get('t_stop_ms', 0)) if d.get('t_stop_ms') else 'son'} ms"))
    if req.get("crush_ref"):
        out.append(("Ezilme referansı (/TH/NODE)", target(req["crush_ref"])))
    for s in req.get("sections") or []:
        out.append(("Kesit kuvveti (/SECT)", f"{s.get('name')}: O {vec(s.get('origin'))}, M1 {vec(s.get('corner1'))}, "
                    f"M2 {vec(s.get('corner2'))}"))
    if req.get("gravity"):
        g = req["gravity"]
        out.append(("Yerçekimi (/GRAV)", f"{f(g.get('accel_m_s2'))} m/s² · {g.get('direction')}"))
    for s in req.get("sph_projectiles") or []:
        out.append(("SPH mermi (/SPHCEL)", ", ".join(f"{k} {f(v) if isinstance(v, (int, float)) else v}"
                                                     for k, v in s.items() if not isinstance(v, (list, dict)))))
    for bl in req.get("blast_loads") or []:
        out.append(("Patlama yükü (/LOAD/PBLAST)", ", ".join(f"{k} {v}" for k, v in bl.items()
                                                             if not isinstance(v, (list, dict)))))
    for pl in req.get("pressure_loads") or []:
        out.append(("Basınç yükü (Friedlander)", ", ".join(f"{k} {v}" for k, v in pl.items()
                                                            if not isinstance(v, (list, dict)))))
    eng = req.get("engine") or {}
    if eng.get("th_dt_ms"):
        out.append(("Çıktı: TH aralığı", f"{f(eng['th_dt_ms'])} ms"))
    flt = req.get("filters") or {}
    if flt.get("force_cfc") or flt.get("acc_cfc"):
        out.append(("CFC filtresi", f"kuvvet {flt.get('force_cfc') or '—'} · ivme {flt.get('acc_cfc') or '—'}"))
    sh = (req.get("model") or {}).get("shell") or {}
    if sh.get("ishell"):
        out.append(("Kabuk formülasyonu (Ishell)", str(sh["ishell"])))
    fail = (req.get("model") or {}).get("fail") or {}
    if fail.get("tensstrain") or fail.get("johnson") or (req.get("model") or {}).get("eps_p_max"):
        out.append(("Kopma / eleman silme", material_text(req["model"]).split(" · ", 1)[-1]))
    return out


def flatten(d: Any, pre: str = "") -> dict[str, Any]:
    if isinstance(d, dict):
        out: dict[str, Any] = {}
        for k, v in d.items():
            if k in ("name", "run_solver", "wait", "geometry_id"):
                continue
            out.update(flatten(v, f"{pre}.{k}" if pre else k))
        return out
    return {pre: d}


def diff(base: dict[str, Any], req: dict[str, Any]) -> list[str]:
    a, b = flatten(base), flatten(req)
    rows = []
    for k in sorted(set(a) | set(b)):
        if a.get(k) != b.get(k):
            rows.append(f"{k}: {json.dumps(a.get(k), ensure_ascii=False)} → {json.dumps(b.get(k), ensure_ascii=False)}")
    return rows


# ── Fiziksel okuma: ne oldu + tutarlılık kontrolleri (sayılarla; öneri yok) ──
#: (skaler, etiket, eşik) — eğitim raporu için yaygın kullanılan kabul sınırları
LIMITS = [("energy_balance_rel", "Enerji dengesi |ΔE|/E₀", 0.05), ("hourglass_ratio", "HG / IE", 0.10),
          ("mass_added_rel", "Eklenen kütle", 0.02)]


def momentum_clean(req: dict[str, Any]) -> bool:
    """Duvar impulsu tek dış kuvvet mi — impuls ≈ momentum değişimi kontrolü yalnız o zaman anlamlı."""
    b = req.get("barrier") or {}
    if not (req.get("use_rigid_wall", True) and b.get("wall") and b.get("speed_m_s")) or b.get("angle_deg"):
        return False
    if any(req.get(k) for k in ("springs", "imposed_velocities", "initial_velocities", "gravity", "added_masses",
                                "blast_loads", "pressure_loads", "sph_projectiles")):
        return False
    if any(p.get("role") in ("fixed", "free") for p in req.get("parts") or []):
        return False
    # kızak rayı (tek serbest öteleme) duvar normalindeki momentumu değiştirmez; diğer /BCS değiştirir
    return all(bc.get("rigid_body") and bc.get("dofs", "").count("0") == 1 for bc in req.get("boundary_conditions") or [])


def contact_end_ms(time: list[float], force: list[float], frac: float = 0.01) -> float | None:
    """Duvar kuvvetinin Fmax'ın `frac` katının üstünde kaldığı son an; koşu sonuna kadar sürüyorsa None."""
    fa = [abs(v) for v in force]
    if not fa or max(fa) <= 0 or len(time) != len(fa):
        return None
    lim = frac * max(fa)
    last = max(i for i, v in enumerate(fa) if v > lim)
    # son %5'lik dilimde hâlâ kuvvet varsa temas sürüyor
    return None if time[last] >= time[0] + 0.95 * (time[-1] - time[0]) else time[last]


def lateral_peak_mm(anim: dict[str, Any], normal: list[float]) -> float | None:
    """Son karede düğümlerin duvar normaline dik en büyük yer değiştirmesi (mm) — global eğilme / yana kayma."""
    fr = anim.get("frames") or []
    if len(fr) < 2 or not normal:
        return None
    n = math.sqrt(sum(c * c for c in normal)) or 1.0
    nx = [c / n for c in normal]
    a, b = fr[0].get("positions") or [], fr[-1].get("positions") or []
    best = 0.0
    for i in range(0, min(len(a), len(b)) - 2, 3):
        d = [b[i + k] - a[i + k] for k in range(3)]
        dn = sum(d[k] * nx[k] for k in range(3))
        best = max(best, math.sqrt(max(sum(x * x for x in d) - dn * dn, 0.0)))
    return best


def physical_reading(sc: dict[str, Any], req: dict[str, Any], ke0: float | None = None,
                     t_contact_end: float | None = None, lateral_mm: float | None = None) -> tuple[str, list[str]]:
    """Skalerlerden (davranış, kontrol satırları). KE₀ verilmezse ½·m·v² (m = model kütlesi; yalnız tüm model
    aynı hızla başlıyorsa), değilse KE maks. `t_contact_end`: duvar kuvvetinin bittiği an (contact_end_ms)."""
    num = lambda k: sc.get(k) if isinstance(sc.get(k), (int, float)) else None  # noqa: E731
    v = (req.get("barrier") or {}).get("speed_m_s")
    m = num("mass_model")
    if not ke0:
        ke0 = 0.5 * m * v * v if m and v and momentum_clean(req) else num("kinetic_energy_max")
    ke, ie = num("kinetic_energy_final"), num("internal_energy_final")
    checks: list[str] = []
    if ke0 and ke0 > 0:
        checks.append(f"KE₀ {f(ke0)} J")
        if ie is not None:
            checks.append(f"IE son / KE₀ = %{ie / ke0 * 100:.1f}")
        if ke is not None:
            checks.append(f"KE son / KE₀ = %{ke / ke0 * 100:.1f}")
    ratio = None
    imp = num("rwall_impulse_final")
    if imp is not None and ke0 and v and momentum_clean(req):
        p0 = 2 * ke0 / v  # m·v (kg·m/s = N·s)
        ratio = abs(imp) / p0
        checks.append(f"Duvar impulsu / p₀ = {ratio:.2f} (p₀ = m·v = {f(p0)} N·s; tam durma 1, elastik sekme 2)")
    for k, lab, lim in LIMITS:
        x = num(k)
        if x is not None:
            checks.append(f"{lab} = %{abs(x) * 100:.1f} — sınır %{lim * 100:g}: "
                          + ("içinde" if abs(x) <= lim else "AŞIYOR"))
    ke_r = ke / ke0 if ke is not None and ke0 else None
    ie_r = ie / ke0 if ie is not None and ke0 else None
    ie_max = num("internal_energy_max")
    if t_contact_end is not None:
        checks.append(f"Duvar kuvveti t = {f(t_contact_end)} ms sonrası ≈ 0 (< %1 Fmax), t_end {f(req.get('t_end_ms'))} ms")
    if lateral_mm is not None:
        checks.append(f"Duvar normaline dik en büyük yer değiştirme (son kare) {f(lateral_mm)} mm")
    if ratio is not None and ke_r is not None and t_contact_end is not None and ratio < 0.9 and ke_r > 0.02:
        what = (f"Duvardan ayrıldı: duvar kuvveti t = {f(t_contact_end)} ms'den sonra ≈ 0, impuls {ratio:.2f}·p₀ "
                f"< 1; KE son = %{ke_r * 100:.0f} · KE₀ duvara aktarılmadan kaldı.")
        if ie is not None and ie_max and ie >= 0.98 * ie_max:
            what += " IE son ≈ IE maks: elastik enerji geri verilmedi (elastik sekme değil)."
        if lateral_mm is not None:
            what += f" Son karede duvar normaline dik yer değiştirme {f(lateral_mm)} mm."
    elif ratio is not None and ke_r is not None:
        if ratio >= 1.5:
            what = (f"Geri sekti: impuls {ratio:.2f}·p₀, yani hız ters döndü (e ≈ {ratio - 1:.2f}); "
                    f"koşu sonunda KE = %{ke_r * 100:.0f} · KE₀.")
        elif ratio < 0.9 and ke_r > 0.02:
            what = (f"Çarpma bitmedi: impuls {ratio:.2f}·p₀ < 1 ve KE son = %{ke_r * 100:.0f} · KE₀; "
                    f"t_end = {f(req.get('t_end_ms'))} ms anında gövde hâlâ duvara doğru hareket ediyor.")
        else:
            what = (f"Durdu: impuls {ratio:.2f}·p₀ ≈ 1; IE son = %{(ie_r or 0) * 100:.0f} · KE₀ "
                    f"(geri sekme katsayısı e ≈ {max(ratio - 1, 0):.2f}).")
    elif ie_r is not None and ke_r is not None:
        if ke_r > 0.5:
            what = f"Kinetik enerjinin çoğu duruyor: KE son = %{ke_r * 100:.0f} · KE₀, IE son = %{ie_r * 100:.0f} · KE₀."
        else:
            what = f"Kinetik enerji harcandı: KE son = %{ke_r * 100:.0f} · KE₀, IE son = %{ie_r * 100:.0f} · KE₀."
        what += " (Duvar dışı kuvvet / kısıt var: impuls–momentum kontrolü yapılmadı.)"
    else:
        what = "Enerji skalerleri yok — okuma yapılmadı."
    extra = []
    if (num("crush_max_mm") or 0) > 0:
        extra.append(f"ezilme δ_maks {f(num('crush_max_mm'))} mm")
    if (num("springback_mm") or 0) > 0:
        extra.append(f"geri yaylanma {f(num('springback_mm'))} mm")
    if (num("elements_deleted") or 0) > 0:
        extra.append(f"{int(num('elements_deleted'))} eleman silindi")
    if extra:
        what += " " + "; ".join(extra).capitalize() + "."
    return what, checks


# ── Grafikler ─────────────────────────────────────────────────────────────
def line_chart(title: str, series: list[tuple[str, list[float], list[float]]], font: str, xlab: str, ylab: str,
               w: float = 170, h: float = 62) -> Drawing | None:
    data, names = [], []
    for name, xs, ys in series:
        pts = [(x, y) for x, y in zip(xs, ys) if isinstance(y, (int, float)) and math.isfinite(y)]
        if len(pts) > 1:
            step = max(1, len(pts) // 500)
            data.append(pts[::step])
            names.append(name)
    if not data:
        return None
    d = Drawing(w * mm, h * mm)
    lp = LinePlot()
    lp.x, lp.y, lp.width, lp.height = 16 * mm, 9 * mm, (w - 62) * mm, (h - 17) * mm
    lp.data = data
    for i in range(len(data)):
        lp.lines[i].strokeColor = colors.HexColor(PALETTE[i % len(PALETTE)])
        lp.lines[i].strokeWidth = 0.9
    for ax in (lp.xValueAxis, lp.yValueAxis):
        ax.labels.fontName = font
        ax.labels.fontSize = 6.5
    lp.yValueAxis.labelTextFormat = lambda v: f"{v:.4g}"
    if ylab.startswith("E ") and all(y >= 0 for ser in data for _, y in ser):
        lp.yValueAxis.valueMin = 0  # enerji eksenleri sıfırdan
    lp.xValueAxis.labelTextFormat = lambda v: f"{v:.4g}"
    d.add(lp)
    d.add(String(16 * mm, (h - 5) * mm, title + (f"   [{ylab}]" if ylab else ""), fontName=font, fontSize=8.5))
    d.add(String((16 + (w - 62) / 2) * mm, 1.5 * mm, xlab, fontName=font, fontSize=7, textAnchor="middle"))
    for i, n in enumerate(names):
        d.add(String((w - 44) * mm, (h - 12 - 4.2 * i) * mm, f"— {n}"[:34], fontName=font, fontSize=6.5,
                     fillColor=colors.HexColor(PALETTE[i % len(PALETTE)])))
    return d


def mesh_drawing(anim: dict[str, Any], frame: int, font: str, title: str, req: dict[str, Any] | None = None,
                 w: float = 82, h: float = 58, color_by: str = "part") -> Drawing | None:
    """Mesh görüntüsü: izometrik izdüşüm, ressam algoritması; parça renkli (ya da plastik gerinim)."""
    frames = anim.get("frames") or []
    faces = anim.get("faces") or []
    if not frames or not faces:
        return None
    fr = frames[frame if frame >= 0 else len(frames) - 1]
    pos = fr["positions"]
    P = [(pos[i], pos[i + 1], pos[i + 2]) for i in range(0, len(pos), 3)]
    a, e = math.radians(35), math.radians(25)

    def proj(p: tuple[float, float, float]) -> tuple[float, float, float]:
        x, y, z = p
        X = x * math.cos(a) - z * math.sin(a)
        Zr = x * math.sin(a) + z * math.cos(a)
        Y = y * math.cos(e) - Zr * math.sin(e)
        D = y * math.sin(e) + Zr * math.cos(e)
        return X, Y, D

    Q = [proj(p) for p in P]
    xs = [q[0] for q in Q]
    ys = [q[1] for q in Q]
    extra_pts: list[tuple[str, list[tuple[float, float, float]]]] = []
    if req:
        w_ = (req.get("barrier") or {}).get("wall")
        if req.get("use_rigid_wall", True) and w_ and w_.get("kind", "plane") == "plane":
            pt, nv = w_["point"], w_["normal"]
            # duvar düzlemi: modelin boyutunda bir kare
            span = max(max(xs) - min(xs), max(ys) - min(ys)) * 0.35
            u = (0.0, 1.0, 0.0) if abs(nv[1]) < 0.9 else (1.0, 0.0, 0.0)
            v = (nv[1] * u[2] - nv[2] * u[1], nv[2] * u[0] - nv[0] * u[2], nv[0] * u[1] - nv[1] * u[0])
            corners = [tuple(pt[k] + s1 * span * u[k] + s2 * span * v[k] for k in range(3))
                       for s1, s2 in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
            extra_pts.append(("wall", [proj(c) for c in corners]))
            extra_pts.append(("normal", [proj(tuple(pt)), proj(tuple(pt[k] + span * 0.8 * nv[k] for k in range(3)))]))
        for s in req.get("springs") or []:
            ea, eb = s.get("end_a") or {}, s.get("end_b") or {}
            if eb.get("point"):
                # A ucu: kızak bölgesinin yaklaşık merkezi = modelin en büyük x'i (kutu_arka)
                ax = max(P, key=lambda p: p[0])
                cy = sum(p[1] for p in P) / len(P)
                cz = sum(p[2] for p in P) / len(P)
                extra_pts.append(("spring", [proj((ax[0], cy, cz)), proj(tuple(eb["point"]))]))
    allx = xs + [q[0] for _, qs in extra_pts for q in qs]
    ally = ys + [q[1] for _, qs in extra_pts for q in qs]
    x0, x1, y0, y1 = min(allx), max(allx), min(ally), max(ally)
    sc = min((w - 4) * mm / max(x1 - x0, 1e-9), (h - 10) * mm / max(y1 - y0, 1e-9))

    def S(q: tuple[float, float, float]) -> tuple[float, float]:
        return 2 * mm + (q[0] - x0) * sc, 2 * mm + (q[1] - y0) * sc

    d = Drawing(w * mm, h * mm)
    parts = anim.get("face_part") or [0] * len(faces)
    eps = None
    emax = 1.0
    alive = fr.get("face_alive") or [1] * len(faces)
    if color_by == "eps":
        for key in ("2DELEM_Plastic_Strain", "3DELEM_Plastic_Strain"):
            sv = (fr.get("face") or {}).get(key)
            if sv and len(sv) == len(faces):
                eps = sv
                emax = float((anim.get("scalars") or {}).get(key, {}).get("max") or max(sv) or 1.0)
                break
    order = sorted(range(len(faces)), key=lambda i: sum(Q[n][2] for n in faces[i]) / len(faces[i]))
    if len(order) > 9000:
        order = order[:: len(order) // 9000 + 1]
    for name, qs in extra_pts:
        if name == "wall":
            d.add(Polygon([c for q in qs for c in S(q)], fillColor=colors.Color(0.55, 0.55, 0.6, 0.35),
                          strokeColor=colors.HexColor("#555555"), strokeWidth=0.4))
    for i in order:
        if not alive[i]:
            continue
        pts = [c for n in faces[i] for c in S(Q[n])]
        if eps is not None:
            t = max(0.0, min(1.0, (eps[i] or 0.0) / emax if emax > 0 else 0.0))
            fill = colors.Color(0.2 + 0.8 * t, 0.35 + 0.4 * (1 - abs(2 * t - 1)), 0.9 - 0.8 * t)
        else:
            fill = colors.HexColor(PART_COLORS[(parts[i] or 0) % len(PART_COLORS)])
        d.add(Polygon(pts, fillColor=fill, strokeColor=colors.Color(0.25, 0.25, 0.25), strokeWidth=0.08))
    for name, qs in extra_pts:
        if name == "normal":
            (ax_, ay_), (bx_, by_) = S(qs[0]), S(qs[1])
            d.add(Line(ax_, ay_, bx_, by_, strokeColor=colors.HexColor("#444444"), strokeWidth=0.8))
        if name == "spring":
            (ax_, ay_), (bx_, by_) = S(qs[0]), S(qs[1])
            d.add(Line(ax_, ay_, bx_, by_, strokeColor=colors.HexColor("#d62728"), strokeWidth=1.2,
                       strokeDashArray=[2, 1.5]))
            d.add(String(bx_, by_ + 2, "yay", fontName=font, fontSize=6, fillColor=colors.HexColor("#d62728")))
    d.add(String(2 * mm, (h - 4) * mm, title, fontName=font, fontSize=7.5))
    if eps is not None:
        for k in range(20):
            t = k / 19
            d.add(Polygon([(w - 30 + k * 1.2) * mm, 3 * mm, (w - 28.8 + k * 1.2) * mm, 3 * mm,
                           (w - 28.8 + k * 1.2) * mm, 6 * mm, (w - 30 + k * 1.2) * mm, 6 * mm],
                          fillColor=colors.Color(0.2 + 0.8 * t, 0.35 + 0.4 * (1 - abs(2 * t - 1)), 0.9 - 0.8 * t),
                          strokeColor=None))
        d.add(String((w - 30) * mm, 7 * mm, f"εp 0 … {emax:.3g}", fontName=font, fontSize=6))
        n_dead = sum(1 for a_ in alive if not a_)
        if n_dead:
            d.add(String(2 * mm, 3 * mm, f"silinen eleman: {n_dead}", fontName=font, fontSize=6))
    return d


# ── Veri ──────────────────────────────────────────────────────────────────
class Cache:
    def __init__(self, api: Api):
        self.api = api
        self.runs: dict[int, dict[str, Any]] = {}
        self.anims: dict[int, dict[str, Any]] = {}

    def run(self, rid: int | None) -> dict[str, Any]:
        if not rid:
            return {}
        if rid not in self.runs:
            try:
                self.runs[rid] = self.api.get(f"/crash/runs/{rid}")
            except Exception:  # noqa: BLE001
                self.runs[rid] = {}
        return self.runs[rid]

    def deck(self, req: dict[str, Any] | None) -> "Deck | None":
        if not req or not req.get("geometry_id"):
            return None
        key = json.dumps(req, sort_keys=True)
        if not hasattr(self, "decks"):
            self.decks: dict[str, Deck | None] = {}
        if key not in self.decks:
            try:
                self.decks[key] = Deck(self.api.post("/crash/deck/preview",
                                                     {**req, "run_solver": False, "wait": False}, timeout=300))
            except Exception:  # noqa: BLE001
                self.decks[key] = None
        return self.decks[key]

    def anim(self, rid: int | None) -> dict[str, Any]:
        if not rid:
            return {}
        if rid not in self.anims:
            try:
                self.anims[rid] = self.api.get(f"/crash/runs/{rid}/animation")
            except Exception:  # noqa: BLE001
                self.anims[rid] = {}
        return self.anims[rid]


def force_curve(curves: dict[str, Any]) -> tuple[str, list[float]] | None:
    """Duvar kuvveti; duvarsız modelde temas (arayüz) normal kuvvet büyüklüğü."""
    if curves.get("rwall_force") and max(abs(v) for v in curves["rwall_force"]) > 0:
        return "Duvar kuvveti (kN)", [abs(v) for v in curves["rwall_force"]]
    for pref in ("th_inter_", "th_sect_", "th_spring_"):
        keys = sorted(k for k in curves if k.startswith(pref) and k[-3:] in ("FNX", "FNY", "FNZ", "_FX", "_FY", "_FZ"))
        if keys:
            groups: dict[str, list[str]] = {}
            for k in keys:
                groups.setdefault(k.rsplit("_", 1)[0], []).append(k)
            g, ks = next(iter(groups.items()))
            n = len(curves[ks[0]])
            mag = [math.sqrt(sum(curves[k][i] ** 2 for k in ks)) for i in range(n)]
            return f"{g.replace('th_', '')} |F| (kN)", mag
    return None


# ── Deck: ham kartlar, LS-DYNA karşılığı, renkli işaretler ────────────────
DYNA_TS = REPO / "frontend" / "src" / "lib" / "dynaKeywords.ts"
#: Özellik (features() adı öneki) → (renk, Radioss kartı)
FEATURE_STYLE: list[tuple[str, str | None, str]] = [
    ("Rijit duvar", "#8c8c99", "/RWALL"),
    ("Duvarsız mod", None, "—"),
    ("İlk hız", "#1f77b4", "/INIVEL"),
    ("Parçaya ayrı ilk hız", "#1f77b4", "/INIVEL"),
    ("Parça rolü", None, "/BCS (Sabit) · —"),
    ("Parça başına malzeme", None, "/MAT + /PART"),
    ("Kızak", "#ff7f0e", "/RBODY"),
    ("Ray", "#d62728", "/BCS"),
    ("Sınır koşulu", "#d62728", "/BCS"),
    ("Sabit hız", "#00897b", "/IMPVEL"),
    ("Ek kütle", "#7f7f7f", "/ADMAS"),
    ("Temas TYPE7", "#8c564b", "/INTER/TYPE7"),
    ("Temas TYPE24", "#8c564b", "/INTER/TYPE24"),
    ("Yay", "#9467bd", "/SPRING"),
    ("Rayleigh sönüm", "#e377c2", "/DAMP"),
    ("Ezilme referansı", "#2ca02c", "/TH/NODE"),
    ("Kesit kuvveti", "#17becf", "/TH/SECTIO"),
    ("Yerçekimi", "#bcbd22", "/GRAV"),
    ("SPH", "#e6550d", "/SPHCEL"),
    ("Patlama", None, "/LOAD/PBLAST"),
    ("Basınç", None, "/PLOAD"),
    ("Çıktı: TH", None, "/TFILE"),
    ("CFC", None, "— (post-process)"),
    ("Kabuk formülasyonu", None, "/PROP/TYPE1"),
    ("Kopma", None, "/FAIL/TENSSTRAIN · LAW2 EPS_p_max"),
]
#: Koşuların ortaya çıkardığı hatalar / belgede olmayan test girdileri (veri; öneri değil)
FINDINGS = [
    ("T22 yay (/SPRING)", "Starter ERROR 60/178/179/229 (#410–#412): /PART satırında prop_ID–mat_ID yer "
     "değiştirmiş, /PROP/TYPE4 sıfır kütleyi reddediyor.", "Düzeltildi — fix/crash-spring-deck (5a3e49e); #413, #416, #417"),
    ("T22 girdi", "Belgede yay kütlesi yok; kütle artık zorunlu (> 0). Testte 0.1 kg girildi.", "Belgede eksik"),
    ("T24 JC seti (7075-T6)", "Kütüphane setinde ε̇₀ ve T_melt / T_r boş: seti uygulayıp çöz → 422 (c > 0 iken "
     "ε̇₀ > 0; m > 0 iken T_melt > T_r). Testte ε̇₀ = 1 1/s elle, m = 0 (sıcaklık terimi kapalı). Belgedeki "
     "6061-T6 / DP600 setleri kütüphanede yok (doğrulanmış kaynak yalnız 7075-T6).", "Açık — arayüz / belge"),
    ("T29 .k içe aktarma", "*MAT_PLASTIC_KINEMATIC çevrilmiyor; part malzemesiz kalınca çözüm sessizce varsayılan "
     "LAW1 'STEEL' ile koşuyordu (#448).", "Düzeltildi — fix/crash-import-unassigned-mat (006a770): artık 422"),
    ("T13 / T14 plaka delinme", "Senaryo varsayılanlarıyla küre KE ≈ 3 J (kabuk 1 mm, ek kütle 0, 10 m/s, 4 ms): "
     "plaka 11 mm çöker, eleman silinmez; kopma ve LAW1 ayarı sonucu değiştirmez (#422–#425 aynı).",
     "Açık — senaryo değerleri mühendisin"),
    ("T6c yanlış yön", "Belge 'kuvvet ≈ 0' bekliyor; ölçülen Fmax 133 kN, IE 4997 J (#395). Normal −X iken kutu "
     "duvarın yasak tarafında başlar (tüm düğümler başta 'içeride') ve duvar onları iter — kuvvet sıfır olmaz.",
     "Belge beklentisi ≠ veri"),
    ("Model 2 Fmax", "T8–T22 koşularının hepsinde duvar Fmax 81.7 kN: ilk temas anındaki elastik tepe; "
     "temas / ray / yay ayarları IE ve platoyu değiştirir.", "Veri"),
]
#: Galeride yalnız ana modeller (varyantlar kendi bölümünde)
GALLERY_SKIP = {"M1_7075", "M6_30", "M5_bird_fine", "M5_pole_thin"}
MESH_CARDS = ("/NODE", "/SHELL", "/SH3N", "/BRICK", "/TETRA4", "/TETRA10", "/BEGIN", "/END")


def short_title(t: str) -> str:
    """Galeri başlığı: 'Model N' ya da senaryo adının ilk sözcükleri."""
    if t.startswith("Model"):
        return t.split(" — ")[0]
    head = t.split(" (")[0]
    return head if len(head) <= 24 else head[:23] + "…"


def mono_font() -> str:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    for path in ("C:/Windows/Fonts/consola.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"):
        if Path(path).is_file():
            if "TrMono" not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont("TrMono", path))
            return "TrMono"
    return "Courier"


def feature_style(name: str) -> tuple[str | None, str]:
    for pre, col, card in FEATURE_STYLE:
        if name.startswith(pre):
            return col, card
    return None, "—"


def dyna_map() -> dict[str, str]:
    src = DYNA_TS.read_text(encoding="utf-8")
    return dict(re.findall(r'"(/[^"]+)":\s*"([^"]+)"', src))


DYNA = dyna_map()


def dyna_for(card: str) -> str:
    best = ""
    for k in DYNA:
        if (card == k or card.startswith(k + "/")) and len(k) > len(best):
            best = k
    return f"≈ {DYNA[best]}" if best else ""


class Deck:
    """`/crash/deck/preview` çıktısı: kart blokları, düğüm koordinatları, renkli işaretler."""

    def __init__(self, prev: dict[str, Any]):
        self.blocks: list[tuple[str, list[str]]] = []
        for key in ("starter", "engine"):
            lines = (prev.get(key) or "").splitlines()
            for o in prev.get(f"{key}_outline") or []:
                self.blocks.append((o["card"], lines[o["line"] - 1:o["line"] - 1 + o["lines"]]))
        self.nodes: dict[int, tuple[float, float, float]] = {}
        self.grnod: dict[int, tuple[str, list[int]]] = {}
        for card, ls in self.blocks:
            if card == "/NODE":
                for ln in ls[1:]:
                    p = ln.split()
                    if len(p) >= 4:
                        try:
                            self.nodes[int(p[0])] = (float(p[1]), float(p[2]), float(p[3]))
                        except ValueError:
                            pass
            elif card.startswith("/GRNOD/NODE/"):
                gid = int(card.rsplit("/", 1)[1])
                ids = [int(x) for ln in ls[2:] for x in ln.split() if x.lstrip("-").isdigit()]
                self.grnod[gid] = (ls[1].strip() if len(ls) > 1 else "", ids)

    def raw(self, skip_mesh: bool = True, max_lines: int = 8) -> list[tuple[str, str]]:
        out = []
        for card, ls in self.blocks:
            if skip_mesh and (card.split("/")[1:2] and "/" + card.split("/")[1] in MESH_CARDS):
                continue
            body = ls[:max_lines] + ([f"   … (+{len(ls) - max_lines} satır)"] if len(ls) > max_lines else [])
            out.append((card, "\n".join(body)))
        return out

    def diff(self, base: "Deck") -> list[tuple[str, str, str]]:
        """(durum, kart, metin): tabana göre eklenen / değişen / kalkan kartlar (mesh hariç)."""
        a = {c: "\n".join(ls) for c, ls in base.blocks if "/" + c.split("/")[1] not in MESH_CARDS}
        b = {c: "\n".join(ls) for c, ls in self.blocks if "/" + c.split("/")[1] not in MESH_CARDS}
        out = []
        for c, t in b.items():
            if c not in a:
                out.append(("eklendi", c, t))
            elif a[c] != t:
                out.append(("değişti", c, t))
        for c in a:
            if c not in b:
                out.append(("kalktı", c, a[c]))
        return out

    def _ints(self, ln: str) -> list[int]:
        return [int(x) for x in ln.split() if x.lstrip("-").isdigit()]

    def markers(self) -> list[dict[str, Any]]:
        """Renkli işaretler: points (düğüm kümesi) / line / plane / arrow."""
        mk: list[dict[str, Any]] = []
        P = self.nodes
        for card, ls in self.blocks:
            try:
                if card.startswith("/RBODY/") and len(ls) > 2:
                    v = self._ints(ls[2])
                    gid = int(ls[2].split()[5]) if len(ls[2].split()) > 5 else 0
                    pts = [P[i] for i in self.grnod.get(gid, ("", []))[1] if i in P]
                    mk.append({"kind": "points", "color": "#ff7f0e", "label": f"Kızak / rijit gövde '{ls[1].strip()}'",
                               "pts": pts})
                    if v and v[0] in P:
                        mk.append({"kind": "points", "color": "#000000", "label": "rijit gövde ana düğümü",
                                   "pts": [P[v[0]]], "size": 2.2})
                elif card.startswith("/BCS/") and len(ls) > 2:
                    gid = self._ints(ls[2])[-1]
                    title, ids = self.grnod.get(gid, ("", []))
                    if "spring" in title:
                        continue
                    mk.append({"kind": "points", "color": "#d62728", "label": f"BCS '{ls[1].strip()}' ({ls[2][:10].strip()})",
                               "pts": [P[i] for i in ids if i in P], "size": 1.6 if len(ids) < 3 else 0.9})
                elif card.startswith("/IMPVEL/") and len(ls) > 2:
                    gid = self._ints(ls[2])[-1] if self._ints(ls[2]) else 0
                    mk.append({"kind": "points", "color": "#00897b", "label": f"Sabit hız '{ls[1].strip()}'",
                               "pts": [P[i] for i in self.grnod.get(gid, ("", []))[1] if i in P]})
                elif card.startswith("/SPRING/") and len(ls) > 1:
                    v = self._ints(ls[1])
                    if len(v) >= 3 and v[1] in P and v[2] in P:
                        mk.append({"kind": "line", "color": "#9467bd", "label": "Yay", "pts": [P[v[1]], P[v[2]]]})
                        mk.append({"kind": "points", "color": "#9467bd", "label": "yay sabit ucu", "pts": [P[v[2]]],
                                   "size": 2.0})
                elif card.startswith("/TH/NODE/") and len(ls) > 3 and "crush" in ls[1]:
                    v = self._ints(ls[3].split("c")[0])
                    if v and v[0] in P:
                        mk.append({"kind": "points", "color": "#2ca02c", "label": "Ezilme referansı düğümü",
                                   "pts": [P[v[0]]], "size": 2.6})
                elif card.startswith("/SECT/") and len(ls) > 6:
                    corners = [tuple(float(x) for x in ln.split()[:3]) for ln in ls[-3:]]
                    o, c1, c2 = corners
                    c3 = tuple(c1[k] + c2[k] - o[k] for k in range(3))
                    mk.append({"kind": "plane", "color": "#17becf", "label": f"Kesit '{ls[1].strip()}'",
                               "pts": [o, c1, c3, c2]})
                elif card.startswith("/INIVEL/") and len(ls) > 2:
                    p = ls[2].split()
                    mk.append({"kind": "arrow", "color": "#1f77b4", "label": "İlk hız",
                               "vec": tuple(float(x) for x in p[:3])})
            except (ValueError, IndexError, KeyError):
                continue
        return mk


def feature_drawing(anim: dict[str, Any], deck: Deck | None, req: dict[str, Any], font: str, title: str,
                    w: float = 120, h: float = 72, legend_on: bool = True) -> Drawing | None:
    """t = 0 mesh soluk; deck'teki özellikler renkli (tablodaki renklerle aynı) + lejant."""
    frames, faces = anim.get("frames") or [], anim.get("faces") or []
    if not frames or not faces:
        return None
    pos = frames[0]["positions"]
    Pm = [(pos[i], pos[i + 1], pos[i + 2]) for i in range(0, len(pos), 3)]
    a, e = math.radians(35), math.radians(25)

    def proj(p: tuple[float, ...]) -> tuple[float, float, float]:
        x, y, z = p
        X = x * math.cos(a) - z * math.sin(a)
        Zr = x * math.sin(a) + z * math.cos(a)
        return X, y * math.cos(e) - Zr * math.sin(e), y * math.sin(e) + Zr * math.cos(e)

    Q = [proj(p) for p in Pm]
    marks = deck.markers() if deck else []
    xs, ys = [q[0] for q in Q], [q[1] for q in Q]
    span = max(max(xs) - min(xs), max(ys) - min(ys))
    wall = (req.get("barrier") or {}).get("wall") if req.get("use_rigid_wall", True) else None
    extra: list[tuple[float, float, float]] = []
    wall_q = None
    if wall and wall.get("kind", "plane") == "plane":
        pt, nv = wall["point"], wall["normal"]
        u = (0.0, 1.0, 0.0) if abs(nv[1]) < 0.9 else (1.0, 0.0, 0.0)
        v = (nv[1] * u[2] - nv[2] * u[1], nv[2] * u[0] - nv[0] * u[2], nv[0] * u[1] - nv[1] * u[0])
        s_ = span * 0.3
        wall_q = [proj(tuple(pt[k] + s1 * s_ * u[k] + s2 * s_ * v[k] for k in range(3)))
                  for s1, s2 in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        extra += wall_q
    for m_ in marks:
        if m_["kind"] in ("points", "line", "plane"):
            extra += [proj(p) for p in m_["pts"]]
    allx, ally = xs + [q[0] for q in extra], ys + [q[1] for q in extra]
    x0, x1, y0, y1 = min(allx), max(allx), min(ally), max(ally)
    leg_w = 46.0 if legend_on else 0.0
    msc = min(1.0, w / 120.0)  # küçük görüntüde işaret boyu da küçülür
    sc = min((w - leg_w - 4) * mm / max(x1 - x0, 1e-9), (h - 10) * mm / max(y1 - y0, 1e-9))

    def S(q: tuple[float, float, float]) -> tuple[float, float]:
        return 2 * mm + (q[0] - x0) * sc, 2 * mm + (q[1] - y0) * sc

    d = Drawing(w * mm, h * mm)
    if wall_q:
        d.add(Polygon([c for q in wall_q for c in S(q)], fillColor=colors.Color(0.55, 0.55, 0.6, 0.35),
                      strokeColor=colors.HexColor("#8c8c99"), strokeWidth=0.5))
    parts = anim.get("face_part") or [0] * len(faces)
    order = sorted(range(len(faces)), key=lambda i: sum(Q[n][2] for n in faces[i]) / len(faces[i]))
    if len(order) > 9000:
        order = order[:: len(order) // 9000 + 1]
    for i in order:
        base = colors.HexColor(PART_COLORS[(parts[i] or 0) % len(PART_COLORS)])
        fill = colors.Color(0.55 + 0.45 * base.red, 0.55 + 0.45 * base.green, 0.55 + 0.45 * base.blue)
        d.add(Polygon([c for n in faces[i] for c in S(Q[n])], fillColor=fill,
                      strokeColor=colors.Color(0.6, 0.6, 0.6), strokeWidth=0.06))
    legend: list[tuple[str, str]] = [("#8c8c99", "Rijit duvar")] if wall_q else []
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    for m_ in marks:
        col = colors.HexColor(m_["color"])
        if m_["kind"] == "points":
            r_ = m_.get("size", 1.0) * mm * 0.5 * msc * (0.7 if len(m_["pts"]) > 60 else 1.0)
            for p in m_["pts"][:4000]:
                X, Y = S(proj(p))
                d.add(Polygon([X - r_, Y - r_, X + r_, Y - r_, X + r_, Y + r_, X - r_, Y + r_], fillColor=col,
                              strokeColor=None))
        elif m_["kind"] == "line":
            (ax_, ay_), (bx_, by_) = (S(proj(p)) for p in m_["pts"])
            d.add(Line(ax_, ay_, bx_, by_, strokeColor=col, strokeWidth=1.3, strokeDashArray=[2.5, 1.5]))
        elif m_["kind"] == "plane":
            d.add(Polygon([c for p in m_["pts"] for c in S(proj(p))], fillColor=colors.Color(
                col.red, col.green, col.blue, 0.25), strokeColor=col, strokeWidth=0.6))
        elif m_["kind"] == "arrow":
            v = m_["vec"]
            n_ = math.sqrt(sum(c * c for c in v)) or 1.0
            q0 = (cx, cy + (y1 - y0) * 0.38, 0.0)
            tip = proj(tuple(c / n_ * span * 0.18 for c in v))
            org = proj((0.0, 0.0, 0.0))
            q1 = (q0[0] + tip[0] - org[0], q0[1] + tip[1] - org[1], 0.0)
            (ax_, ay_), (bx_, by_) = S(q0), S(q1)
            d.add(Line(ax_, ay_, bx_, by_, strokeColor=col, strokeWidth=1.6))
            ang = math.atan2(by_ - ay_, bx_ - ax_)
            for da in (2.6, -2.6):
                d.add(Line(bx_, by_, bx_ - 2.2 * mm * math.cos(ang + da / 6), by_ - 2.2 * mm * math.sin(ang + da / 6),
                           strokeColor=col, strokeWidth=1.6))
        if (m_["color"], m_["label"]) not in legend and m_["color"] != "#000000":
            legend.append((m_["color"], m_["label"]))
    for i_, (c_, lab) in enumerate(legend[:12] if legend_on else []):
        yy = (h - 12 - 4.6 * i_) * mm
        d.add(Polygon([(w - leg_w) * mm, yy, (w - leg_w + 3) * mm, yy, (w - leg_w + 3) * mm, yy + 3 * mm,
                       (w - leg_w) * mm, yy + 3 * mm], fillColor=colors.HexColor(c_), strokeColor=None))
        d.add(String((w - leg_w + 4.5) * mm, yy + 0.6 * mm, lab[:34], fontName=font, fontSize=6.4))
    d.add(String(2 * mm, (h - 4) * mm, title, fontName=font, fontSize=7.5 if legend_on else 5.4))
    return d


# ── PDF ───────────────────────────────────────────────────────────────────
def build(api: Api, out_pdf: Path, tests: set[str] | None = None) -> None:
    state = json.loads(OUT.read_text(encoding="utf-8"))
    res: dict[str, Any] = state.get("results", {})
    bases: dict[str, Any] = state.get("bases", {})
    texts = training_texts()
    steps = [s for s in plan() if not tests or s.test in tests]
    cache = Cache(api)
    font, bold = _fonts()
    ss = getSampleStyleSheet()
    H1 = ParagraphStyle("h1", parent=ss["Heading1"], fontName=bold, fontSize=17, spaceAfter=4)
    H2 = ParagraphStyle("h2", parent=ss["Heading2"], fontName=bold, fontSize=13, spaceBefore=8, spaceAfter=4,
                        textColor=colors.HexColor("#1f3b5a"))
    H3 = ParagraphStyle("h3", parent=ss["Heading3"], fontName=bold, fontSize=10.5, spaceBefore=6, spaceAfter=3)
    B = ParagraphStyle("b", parent=ss["Normal"], fontName=font, fontSize=8.6, leading=11)
    SM = ParagraphStyle("sm", parent=B, fontSize=7.4, leading=9.2, textColor=colors.HexColor("#333333"))
    MONO = ParagraphStyle("mono", parent=SM, fontName=mono_font(), fontSize=6.6, leading=8)

    def card_box(txt: str, dy: str = "", head: str = "") -> Table:
        """Ham kart: gri zeminli kutu; LS-DYNA karşılığı altta mavi."""
        cells = [[Preformatted((head + "\n" if head else "") + txt, MONO)]]
        if dy:
            cells.append([Paragraph(esc(dy), ParagraphStyle("dy", parent=SM, fontSize=6.6, leading=8,
                                                             textColor=colors.HexColor("#1f5fa8")))])
        t = Table(cells, hAlign="LEFT", colWidths=[174 * mm])
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f4f6f8")),
                               ("BOX", (0, 0), (-1, -1), 0.3, colors.HexColor("#c9d0d8")),
                               ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5)]))
        return t

    def esc(t: str) -> str:
        t = t.translate(SUBS)
        return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")

    def P(t: str, st: ParagraphStyle = B) -> Paragraph:
        return Paragraph(esc(t), st)

    def table(rows: list[list[Any]], widths: list[float] | None = None, fs: float = 7.4) -> Table:
        cells = [[c if not isinstance(c, str) else Paragraph(
            esc(c),
            ParagraphStyle("c", parent=SM, fontSize=fs, leading=fs + 1.6,
                           fontName=bold if r == 0 else font)) for c in row] for r, row in enumerate(rows)]
        t = Table(cells, hAlign="LEFT", colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8edf2")),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c9d0d8")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ]))
        return t

    story: list[Any] = []
    n_solve = sum(1 for k, r in res.items() if r.get("kind") == "solve" and r.get("run_id"))
    plan_keys = {s_.key for s_ in steps}
    res = {k: v for k, v in res.items() if k in plan_keys}  # eski / plandan çıkan adımlar raporda yok
    n_err = sum(1 for k, r in res.items() if r.get("status") == "error" and k != "T29b")
    story += [P("Crash Eğitim Testleri — Koşu Raporu", H1),
              P(f"{datetime.now():%d.%m.%Y %H:%M} · Belgeler → Eğitim testleri (T1–T30) · çözücü OpenRadioss · "
                f"{n_solve} çözücü koşusu · {len(res)} adım" + (f" · {n_err} adım hatalı" if n_err else "")
                + (" · T29b beklendiği gibi reddedildi (422)" if (res.get("T29b") or {}).get("status") == "error" else ""), SM),
              Spacer(1, 3 * mm),
              P("Her test belgedeki alt adımlarla koşuldu: model bir kez kurulur, her adım tabandan yalnız belgedeki "
                "değişikliği yapar. Tüm koşular crash_runs tablosunda (koşu no ile) — uygulamada Crash geçmişi → "
                "Karşılaştır ile açılabilir. Her testte 'Fiziksel okuma' tablosu koşunun ne yaptığını (sekti / durdu / "
                "bitmedi) ve tutarlılık kontrollerini sayılarla verir: impuls ≈ momentum değişimi (p₀ = m·v), "
                "IE / KE₀, kalan KE, enerji dengesi, hourglass ve eklenen kütle oranları (eşikler: "
                + ", ".join(f"{lab} ≤ %{lim * 100:g}" for _, lab, lim in LIMITS)
                + "). Ayar önerisi içermez. Kurulum tabloları koşunun kayıtlı isteğinden (deck'e giden) üretildi.", B)]

    # Sayfa 1: modellerin görüntüleri + koşu özeti
    gallery = []
    seen: list[str] = []
    for s in steps:
        r = res.get(s.key) or {}
        bk = r.get("base")
        if bk and bk not in seen and bk not in GALLERY_SKIP and r.get("run_id") and not r.get("reused_from"):
            seen.append(bk)
            brq = (bases.get(bk) or {}).get("request") or {}
            dr = feature_drawing(cache.anim(r["run_id"]), cache.deck(brq), brq, font,
                                 short_title((bases.get(bk) or {}).get("title", bk)),
                                 w=43, h=40, legend_on=False)
            if dr:
                gallery.append(dr)
    if gallery:
        story.append(P("Modeller (t = 0; renkli işaretler deck'teki kartlardan)", H3))
        rows_g = [gallery[i:i + 4] + [""] * (4 - len(gallery[i:i + 4])) for i in range(0, len(gallery), 4)]
        tg = Table(rows_g, hAlign="LEFT")
        tg.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 1),
                                ("BOX", (0, 0), (-1, -1), 0.3, colors.HexColor("#d0d5db")),
                                ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d0d5db"))]))
        story.append(tg)
    srows = [["Adım", "Alt madde", "Koşu", "Durum", "Fmax (kN)", "IE son (J)", "HG/IE (%)"]]
    for s in steps:
        r = res.get(s.key) or {}
        sc_ = r.get("scalars") or {}
        srows.append([s.key, s.label[:70], f"#{r['run_id']}" if r.get("run_id") else "—",
                      r.get("status", "koşulmadı") + (f" (= {r['reused_from']})" if r.get("reused_from") else ""),
                      f(sc_.get("rwall_force_max")), f(sc_.get("internal_energy_final")),
                      f(sc_["hourglass_ratio"] * 100 if isinstance(sc_.get("hourglass_ratio"), (int, float)) else None)])

    # 1) Özellik dizini
    story += [P("Özellik dizini — hangi kart / sınır koşulu nerede", H3),
              P("Renk kutusu model görüntülerindeki işaret rengiyle aynıdır. LS-DYNA adı yalnız bilgi amaçlı, "
                "yaklaşık (≈) karşılıktır.", SM)]
    idx: dict[str, dict[str, list[str]]] = {}
    for s in steps:
        r = res.get(s.key) or {}
        rq = r.get("request")
        if not rq or r.get("reused_from"):
            continue
        for feat, det in features(rq):
            idx.setdefault(feat, {}).setdefault(det, []).append(s.key)
    rows = [["", "Özellik", "Radioss kartı · LS-DYNA (≈)", "Kullanıldığı adımlar · değer"]]
    styles_ = []
    for feat in sorted(idx):
        col, card = feature_style(feat)
        lines = [f"{', '.join(keys)}: {det}" for det, keys in idx[feat].items()]
        rows.append(["", feat, f"{card}\n{dyna_for(card)}" if card != "—" else "—",
                     "\n".join(lines[:12]) + (f"\n… (+{len(lines) - 12})" if len(lines) > 12 else "")])
        if col:
            styles_.append(("BACKGROUND", (0, len(rows) - 1), (0, len(rows) - 1), colors.HexColor(col)))
    ti = table(rows, [5 * mm, 38 * mm, 45 * mm, 86 * mm], fs=6.9)
    ti.setStyle(TableStyle(styles_))
    story.append(ti)
    story += [P("Koşu özeti", H3), table(srows, [12 * mm, 74 * mm, 13 * mm, 27 * mm, 16 * mm, 16 * mm, 16 * mm], fs=6.8)]
    story += [P("Testlerin ortaya çıkardığı hatalar ve belgede olmayan girdiler", H3),
              table([["Konu", "Gözlem (koşu)", "Durum"]] + [list(x) for x in FINDINGS], [34 * mm, 104 * mm, 36 * mm],
                    fs=6.8),
              PageBreak()]

    # 2) Modeller + testler
    model_order: list[str] = []
    for s in steps:
        if s.model not in model_order:
            model_order.append(s.model)
    if "M5x" in model_order:  # karşılaştırma / DOE / içe aktarma en sonda
        model_order = [m_ for m_ in model_order if m_ != "M5x"] + ["M5x"]
    sec = 1
    for mk in model_order:
        msteps = [s for s in steps if s.model == mk]
        title = MODELS.get(mk, {}).get("title") or {"M5x": "Karşılaştırma, DOE ve LS-DYNA içe aktarma"}.get(mk, mk)
        story.append(P(f"{sec} · {title}", H2))
        sec += 1
        # Modelleme: modelin kullandığı her taban
        used = []
        for s in msteps:
            bk = (res.get(s.key) or {}).get("base")
            if bk and bk not in used:
                used.append(bk)
        for bk in used:
            bi = bases.get(bk) or {}
            rq = bi.get("request") or {}
            scn = bi.get("scenario") or {}
            mesh = bi.get("mesh") or {}
            story.append(P(f"Modelleme — {bi.get('title', bk)}", H3))
            g = scn.get("geometry") or {}
            mrows = [["Alan", "Değer"],
                     ["Şablon / geometri", f"{scn.get('template_id', '—')} · "
                      + ", ".join(f"{k} {f(v)}" for k, v in g.items() if isinstance(v, (int, float)))],
                     ["Mesh", f"{f(scn.get('element_size_mm'))} mm · {scn.get('element_scheme', '—')} · "
                      f"{'2D kabuk' if rq.get('dimension') == 2 else '3D solid'}"
                      + "".join(f" · {k} {v}" for k, v in mesh.items() if isinstance(v, (int, float)) and
                                any(t in k for t in ("node", "elem", "count")))],
                     ["Malzeme (kütüphane)", f"{scn.get('material_name', '—')}"
                      + (f" · küre/çarpıcı {scn['ball_material_name']}" if scn.get("ball_material_name") else "")],
                     ["Malzeme kartı", material_text(rq.get("model") or {})],
                     ["Parçalar", "; ".join(f"#{p['part_id']} {ROLE.get(p.get('role'), p.get('role'))}"
                                            + (f" · t {f(p['thickness_mm'])} mm" if p.get("thickness_mm") else "")
                                            for p in rq.get("parts") or [])],
                     ["Çarpma", f"{f((rq.get('barrier') or {}).get('speed_m_s'))} m/s · süre {f(rq.get('t_end_ms'))} ms"],
                     ["Çözüm / çıktı", "zaman adımı: " + ((rq.get("engine") or {}).get("dt_kind") or "Radioss varsayılanı")
                      + f" · TH aralığı {f((rq.get('engine') or {}).get('th_dt_ms')) if (rq.get('engine') or {}).get('th_dt_ms') else 'varsayılan'}"
                      + " · TH: " + ", ".join(k for k, v in (rq.get("th") or {}).items()
                                              if isinstance(v, dict) and v.get("enabled"))]]
            if scn.get("regions"):
                mrows.append(["Bölgeler", ", ".join(scn["regions"].keys())])
            for feat, det in features(rq):
                mrows.append([feat, det])
            story.append(table(mrows, [42 * mm, 132 * mm]))
            first = next((res[s.key] for s in msteps if (res.get(s.key) or {}).get("base") == bk
                          and (res.get(s.key) or {}).get("run_id")), None)
            bdeck = cache.deck(rq)
            if first:
                dr = feature_drawing(cache.anim(first["run_id"]), bdeck, rq, font,
                                     "Model (t = 0) · özellikler renkli", w=174, h=80)
                if dr:
                    story.append(dr)
            if bdeck:
                story.append(P("Ham kartlar (Radioss deck; düğüm / eleman listeleri hariç, uzun bloklar kısaltıldı)", SM))
                for card, txt in bdeck.raw():
                    dy = dyna_for(card)
                    story.append(KeepTogether([card_box(txt, dy), Spacer(1, 1 * mm)]))
        # Testler
        tids: list[str] = []
        for s in msteps:
            if s.test not in tids:
                tids.append(s.test)
        for tid in tids:
            tsteps = [s for s in msteps if s.test == tid]
            tx = texts.get(tid, {})
            story.append(CondPageBreak(60 * mm))
            story.append(P(f"{tid} · {tx.get('title', '')}  ({tx.get('area', '')})", H3))
            for lab, key in (("Öğrenilecek", "learn"), ("Değişen", "change"), ("Bak", "observe"),
                             ("Belgedeki beklenti", "expect")):
                if tx.get(key):
                    story.append(Paragraph(f"<font name='{bold}'>{lab}:</font> " + esc(tx[key]), SM))
            # adım tablosu
            srows = [["Adım", "Belgedeki alt madde", "Koşu", "Durum", "Süre"]]
            for s in tsteps:
                r = res.get(s.key) or {}
                st_ = r.get("status", "koşulmadı")
                if r.get("reused_from"):
                    st_ += f" (= {r['reused_from']})"
                srows.append([s.key, s.label, f"#{r['run_id']}" if r.get("run_id") else "—", st_,
                              f"{r.get('wall_s', '—')} s" if r.get("wall_s") and not r.get("reused_from") else "—"])
            story.append(table(srows, [12 * mm, 104 * mm, 14 * mm, 30 * mm, 14 * mm]))
            for s in tsteps:
                r = res.get(s.key) or {}
                if r.get("status") == "error" or (r.get("message") and r.get("status") not in ("solved",)):
                    story.append(P(f"{s.key}: {str(r.get('message'))[:600]}", SM))
            # kurulum farkı
            drows = [["Adım", "Model tabanına göre değişen alanlar (istek)"]]
            for s in tsteps:
                r = res.get(s.key) or {}
                if r.get("request") and not r.get("reused_from"):
                    base_rq = (bases.get(r.get("base")) or {}).get("request") or {}
                    dl = diff(base_rq, r["request"])
                    drows.append([s.key, "\n".join(dl[:10]) or "— (taban)"])
            if len(drows) > 1:
                story.append(Spacer(1, 1.5 * mm))
                story.append(table(drows, [12 * mm, 162 * mm], fs=6.8))
            # ham kart farkı (deck): tabana göre eklenen / değişen / kalkan kartlar
            for s in tsteps:
                r = res.get(s.key) or {}
                if not r.get("request") or r.get("reused_from"):
                    continue
                bdk = cache.deck((bases.get(r.get("base")) or {}).get("request"))
                sdk = cache.deck(r["request"])
                if not (bdk and sdk):
                    continue
                dd = sdk.diff(bdk)
                story.append(P(f"{s.key} — ham kart farkı (tabana göre): "
                               + (", ".join(f"{c} {st}" for st, c, _ in dd) if dd else "yok (taban deck)"), SM))
                for st, c, txt in dd:
                    ls = txt.splitlines()
                    body = "\n".join(ls[:9] + ([f"   … (+{len(ls) - 9} satır)"] if len(ls) > 9 else []))
                    dy = dyna_for(c)
                    story.append(KeepTogether([card_box(body, dy, f"[{st}]"), Spacer(1, 1 * mm)]))
            # skaler tablo
            runs = [(s, res.get(s.key) or {}) for s in tsteps]
            runs = [(s, r) for s, r in runs if r.get("run_id") and r.get("kind") in ("solve", "dyna") or r.get("reused_from")]
            if runs:
                scs = {s.key: (cache.run(r["run_id"]).get("scalars") or r.get("scalars") or {}) for s, r in runs}
                keys = [k for k in SCALARS if any(isinstance(scs[s.key].get(k[0]), (int, float)) for s, _ in runs)]
                head = ["Büyüklük"] + [f"{s.key} #{r['run_id']}" for s, r in runs]
                rows = [head] + [[f"{lab} ({u})" if u else lab] + [f(scs[s.key].get(k) * scl if isinstance(
                    scs[s.key].get(k), (int, float)) else None) for s, _ in runs] for k, lab, u, scl in keys]
                cw = (174 - 46) / max(1, len(runs))
                story.append(Spacer(1, 1.5 * mm))
                story.append(table(rows, [46 * mm] + [cw * mm] * len(runs), fs=6.8))
                # fiziksel okuma
                prow = [["Adım", "Fiziksel okuma — ne oldu", "Tutarlılık kontrolleri"]]
                for s, r in runs:
                    ke_c = (cache.run(r["run_id"]).get("curves") or {}).get("kinetic_energy") or []
                    rq_ = r.get("request") or (res.get(r.get("reused_from")) or {}).get("request") or {}
                    cv_ = cache.run(r["run_id"]).get("curves") or {}
                    t_ce = contact_end_ms(cv_.get("time") or [], cv_.get("rwall_force") or [])
                    lat = lateral_peak_mm(cache.anim(r["run_id"]),
                                          ((rq_.get("barrier") or {}).get("wall") or {}).get("normal"))
                    what, chk = physical_reading(scs[s.key], rq_, ke_c[0] if ke_c else None, t_ce, lat)
                    prow.append([f"{s.key} #{r['run_id']}", what, "\n".join(chk)])
                story.append(Spacer(1, 1.5 * mm))
                story.append(table(prow, [16 * mm, 78 * mm, 80 * mm], fs=6.8))
                # kuvvet eğrileri üst üste
                ser = []
                ylab = ""
                for s, r in runs:
                    c = cache.run(r["run_id"]).get("curves") or {}
                    fc = force_curve(c)
                    if fc and c.get("time"):
                        ylab = fc[0]
                        ser.append((f"{s.key} #{r['run_id']}", c["time"], fc[1]))
                ch = line_chart(f"{tid} — kuvvet–zaman (üst üste)", ser, font, "t (ms)", ylab)
                if ch:
                    story.append(ch)
                # F–δ
                ser = []
                for s, r in runs:
                    c = cache.run(r["run_id"]).get("curves") or {}
                    if c.get("crush_mm") and c.get("rwall_force"):
                        cr, fo = c["crush_mm"], c["rwall_force"]
                        im = max(range(len(cr)), key=lambda i: cr[i])
                        ser.append((f"{s.key} #{r['run_id']}", cr[:im + 1], [abs(v) for v in fo[:im + 1]]))
                if ser:
                    ch = line_chart(f"{tid} — kuvvet–ezilme F–δ", ser, font, "δ (mm)", "F (kN)")
                    if ch:
                        story.append(ch)
                # yay kuvveti
                ser = []
                for s, r in runs:
                    c = cache.run(r["run_id"]).get("curves") or {}
                    for k in sorted(c):
                        if k.startswith("th_spring_") and k.endswith("_FX"):
                            ser.append((f"{s.key} {k[3:]}", c["time"], c[k]))
                if ser:
                    ch = line_chart(f"{tid} — yay kuvveti", ser, font, "t (ms)", "F (kN)")
                    if ch:
                        story.append(ch)
                # enerji (koşu başına 4 eğri) + son biçim
                for s, r in runs:
                    if r.get("reused_from"):
                        continue
                    c = cache.run(r["run_id"]).get("curves") or {}
                    ser = [(lab, c.get("time", []), c[k]) for k, lab in ENERGY if c.get(k)]
                    ch = line_chart(f"{s.key} #{r['run_id']} — enerji", ser, font, "t (ms)", "E (J)", w=96, h=56)
                    an = cache.anim(r["run_id"])
                    md = mesh_drawing(an, -1, font, f"{s.key} — son durum (renk: plastik gerinim)", r.get("request"),
                                      w=78, h=56, color_by="eps")
                    cells = [x for x in (ch, md) if x is not None]
                    if cells:
                        t = Table([cells], hAlign="LEFT")
                        t.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0),
                                               ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
                        story.append(KeepTogether([t]))
            # özel adımlar
            for s in tsteps:
                r = res.get(s.key) or {}
                if r.get("kind") == "cfc" and r.get("cfc"):
                    cf = r["cfc"]
                    story.append(P(f"{s.key}: {s.label} — " + ", ".join(
                        f"{k} {f(v)}" for k, v in (cf.get("scalars") or cf).items() if isinstance(v, (int, float))), SM))
                    # testteki tüm CFC adımları tek grafikte: ham + her süzgeç (ilk CFC adımında bir kez)
                    cfcs = [x for x in tsteps if (res.get(x.key) or {}).get("kind") == "cfc"]
                    c = cache.run(r["run_id"]).get("curves") or {}
                    if s is cfcs[0] and c.get("rwall_force"):
                        ser = [(f"ham #{r['run_id']}", c["time"], [abs(v) for v in c["rwall_force"]])]
                        for x in cfcs:
                            cc = ((res.get(x.key) or {}).get("cfc") or {}).get("curves") or {}
                            fk = next((k for k in cc if k.startswith("rwall_force")), None)
                            if fk:
                                ser.append((f"CFC {x.extra.get('force_cfc')} ({x.key})", cc.get("time", c["time"]),
                                            [abs(v) for v in cc[fk]]))
                        if len(ser) > 1:
                            ch = line_chart(f"{tid} — duvar kuvveti: ham ve CFC süzülmüş (üst üste)", ser, font,
                                            "t (ms)", "F (kN)")
                            if ch:
                                story.append(ch)
                if r.get("kind") == "compare" and r.get("runs"):
                    ids = r["runs"]
                    for k, lab in ENERGY:
                        ser = []
                        for key, rid in ids.items():
                            c = cache.run(rid).get("curves") or {}
                            if c.get(k):
                                ser.append((f"{key} #{rid}", c["time"], c[k]))
                        ch = line_chart(f"T25 — {lab} enerji (üst üste)", ser, font, "t (ms)", "E (J)")
                        if ch:
                            story.append(ch)
                    rows = [["Büyüklük"] + [f"{k} #{v}" for k, v in ids.items()]]
                    for k, lab, u, scl in SCALARS[:10]:
                        rows.append([f"{lab} ({u})" if u else lab] + [
                            f((cache.run(v).get("scalars") or {}).get(k) * scl if isinstance(
                                (cache.run(v).get("scalars") or {}).get(k), (int, float)) else None) for v in ids.values()])
                    story.append(table(rows))
                if r.get("kind") == "doe":
                    st_ = r.get("study") or {}
                    cases = st_.get("cases") or []
                    story.append(P(f"DOE çalışması #{r.get('study_id')} · {st_.get('status')} · "
                                   f"{len(cases)} vaka · değişkenler {json.dumps(st_.get('vary'), ensure_ascii=False)}", SM))
                    crow = [["Vaka", "Koşu", "Durum"] + list((cases[0].get("values") or {}).keys() if cases else [])
                            + ["Fmax (kN)", "IE son (J)"]]
                    for c_ in cases:
                        sc_ = cache.run(c_.get("run_id")).get("scalars") or {}
                        crow.append([str(c_.get("index")), f"#{c_.get('run_id')}", str(c_.get("status"))]
                                    + [f(v) for v in (c_.get("values") or {}).values()]
                                    + [f(sc_.get("rwall_force_max")), f(sc_.get("internal_energy_final"))])
                    story.append(table(crow, fs=6.6))
                    # Fmax ve IE: (t, v) düzleminde dağılım yerine tablo; vekil model metrikleri
                    tr = r.get("train") or {}
                    tg = [t_ for t_ in tr.get("targets") or [] if t_.get("cv")]
                    if tg:
                        story.append(P(f"Vekil model (RF, {tg[0]['cv'].get('folds')}-fold CV, {tr.get('n_runs')} koşu; "
                                       f"girdiler {', '.join(tr.get('feature_keys') or [])}):", SM))
                        mrow = [["Hedef", "Birim", "R² (CV)", "MAE (CV)", "MAPE (CV)"]]
                        for t_ in tg:
                            cv = t_["cv"]
                            mrow.append([t_.get("label") or t_["key"], t_.get("unit", ""), f(cv.get("r2")),
                                         f(cv.get("mae")), f((cv.get("mape") or 0) * 100) + " %"])
                        story.append(table(mrow, [60 * mm, 18 * mm, 24 * mm, 24 * mm, 24 * mm], fs=6.8))
                        bnd = tr.get("bounds") or {}
                        if bnd:
                            story.append(P("Eğitim aralığı: " + ", ".join(f"{k} {f(v[0])}–{f(v[1])}" for k, v in bnd.items()), SM))
                    prow = [["Tahmin", "Girdiler", "Tepe kuvvet (kN)", "Ort. kuvvet (kN)", "Enerji (J)", "Aralık dışı (OOD)"]]
                    for k, lab in (("predict_in", "aralık içi (t 3, v 10)"), ("predict_ood", "aralık dışı (t 6, v 10)")):
                        pr = r.get(k) or {}
                        pv = pr.get("prediction") or {}
                        if pr:
                            prow.append([lab, ", ".join(f"{a} {f(b)}" for a, b in (r.get(k + "_inputs") or {}).items()),
                                         f(pv.get("peak_force_kn")), f(pv.get("mean_force_kn")),
                                         f(pv.get("energy_absorbed_j")), ", ".join(pr.get("out_of_domain") or []) or "—"])
                    if len(prow) > 1:
                        story.append(table(prow, [30 * mm, 46 * mm, 22 * mm, 22 * mm, 20 * mm, 34 * mm], fs=6.6))
                    if r.get("ml_error"):
                        story.append(P(f"ML: {r['ml_error']}", SM))
                    story.append(P("Not: eğitim, sunucudaki crash_box_shell / rigid_wall vekil modelinin üzerine yazar; "
                                   "rapordan sonra 150 koşuluk DOE #3 modeli yeniden eğitildi (geri yüklendi).", SM))
                if r.get("kind") == "dyna" and r.get("import"):
                    imp = r["import"]
                    ps = imp.get("parse") or {}
                    story.append(P(f"{s.key} · {imp.get('file')} · birimler {json.dumps(imp.get('units'))} · "
                                   + ", ".join(f"{k} {v}" for k, v in ps.items() if isinstance(v, (int, float)) and v)
                                   + (f" · ATLANAN: {ps.get('skipped')}" if ps.get("skipped") else " · atlanan yok"), SM))
                    rows_ = [["Kaynak (LS-DYNA)", "Radioss", "Durum", "Ayrıntı"]]
                    for pm in (imp.get("materials") or {}).get("parts") or []:
                        rows_.append([f"*{pm.get('keyword')} (MID {pm.get('mid')})", LAW.get(pm.get("law"), "—"),
                                      "çevrildi" if pm.get("law") else "ÇEVRİLMEDİ", str(pm.get("note") or "")])
                    for row in (imp.get("setup") or {}).get("rows") or []:
                        rows_.append([str(row.get("source")), str(row.get("target")), str(row.get("status")),
                                      str(row.get("detail"))])
                    story.append(table(rows_, [52 * mm, 34 * mm, 22 * mm, 66 * mm], fs=6.8))
                    for wv in ((imp.get("materials") or {}).get("warnings") or []) +                             ((imp.get("setup") or {}).get("warnings") or []):
                        story.append(P(f"uyarı: {wv}", SM))
                    if r.get("status") == "error":
                        story.append(P(f"{s.key} çözüm: {r.get('message')}", SM))
        story.append(PageBreak())

    doc = SimpleDocTemplate(str(out_pdf), pagesize=A4, topMargin=14 * mm, bottomMargin=14 * mm,
                            leftMargin=16 * mm, rightMargin=16 * mm, title="Crash Eğitim Testleri — Koşu Raporu")

    def footer(canvas: Any, d: Any) -> None:
        canvas.setFont(font, 7)
        canvas.setFillColor(colors.grey)
        canvas.drawRightString(A4[0] - 16 * mm, 8 * mm, f"Crash eğitim testleri · sayfa {d.page}")

    doc.build(story, onFirstPage=footer, onLaterPages=footer)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8001")
    ap.add_argument("--out", default=str(OUT.with_name("crash_egitim_raporu.pdf")))
    ap.add_argument("--tests", default="", help="ör. T1,T2 (boş = tümü)")
    a = ap.parse_args()
    build(Api(a.api), Path(a.out), {t for t in a.tests.split(",") if t} or None)
    print(a.out)


if __name__ == "__main__":
    main()
