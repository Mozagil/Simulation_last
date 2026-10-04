"""Crash validasyon seti (1.17f) — çalışan backend'e (localhost:8000) senaryo
koşuları gönderir, referanslarla karşılaştırır, rapor yazar:
`docs/validation/crash_validation.json` (+ `.md`). Kabul kriteri koymaz —
oranlar veri; eşik mühendisin.

Vakalar (crash_box_shell 300 × 50 × 40, t 3, S235, 10 m/s, rijit duvar):
  V1 elastik (LAW1) kısa çarpma — plato ρ·c·v·A, temas süresi 2L/c, impuls 2·M·v0
  V2 elasto-plastik (LAW2) kısa çarpma — plato σy·A, impuls M·(v0 + v_son)
  V3 kızaklı ezilme (rijit gövde kutu_arka + TEST kütlesi) — Pm = IE/δ vs
     Wierzbicki–Abramowicz / Abramowicz–Jones; mesh 5 / 4 / 3 / 2.5 mm
Hepsinde enerji dengesi, hourglass / IE.

1.18e (plate_ball_shell):
  V4 elastik yarı-statik plaka–küre — ankastre kare plaka k = D/(α·a²),
     F_max = v·√(k·m), δ_max = v·√(m/k), temas süresi π·√(m/k), impuls 2·m·v0
  V5 Recht–Ipson (p = 2) uydurması `docs/validation/plate_ball_sweep.json`
     (1.18d tarama) delinmiş noktalarına — tutarlılık verisi, koşu yok
K1 (taylor_bar):
  V6 Taylor çubuğu (S235 LAW2, tet4) — son boy L1/L0 vs Wilkins–Guinan
     exp(−ρ·v0²/(2·σy)) (h = 0), duvar impulsu M·(v0 + v_son); 2 hız + mesh
K2 (drop_box_shell):
  V7 düşme 1 m (yüzey + köşe) — KE₀ = m·g·H, serbest düşme temas anı,
     duvar impulsu m·(vz_son − vz_0) + m·g·t (ağırlık merkezi hızı TH VZ)
K3 (pole_beam_shell):
  V8 direk Ø254 (/RWALL/CYL) — ortalama direk kuvveti IE/δ vs üç nokta eğilme
     çökme yükü 4·Mp/L; impuls M·(v0 + v_son); mesh 10 / 7.5 mm
K4 (rops_frame_shell):
  V9 ROPS yanal yavaş itme 1 m/s, δ = v·t — kesit kuvveti platosu vs portal
     sallanma yükü 4·Mp/H ve 4·Mp/(H − R) (rijit büküm altı mafsal); ∫F dδ vs IE
K5 (plate_ball_shell, kafa impaktörü):
  V10 Ø165 / 4.5 kg, 11.1 m/s, kaput 0.8 mm — kafa ivmesi ∫|a|dt vs Δv = I/m,
     impuls vs m·(v0 + v_son); HIC15 (ham / CFC1000) veri
K6 (plate_ball_shell, FOPS):
  V13 kapı intrüzyonu (K8) Ø305 silindir, 1 m/s — temas kuvveti platosu vs
     ankastre kiriş 8·Mp/L; ∫F dδ vs IE; 120 mm'de kuvvet (membran, veri)
  V14 Hopkinson (K9) Ø20, Ls 100, Li 500, çelik LAW1, 10 m/s — giriş çubuğu kesit
     kuvveti platosu ρ·c·v0·A/2, darbe süresi 2·Ls/c
  V15 patlama yüklü plaka (K10) 400² × 3, Friedlander Ps 2 MPa, td 0.2 ms, b 1 —
     uygulanan impuls A·∫p dt vs plaka momentumu |ZMOM|(td); kalıcı çökme (veri)
  V16 kepçe / taş (K11) R500 φ90 W600 t10, taş Ø200 / 300 kg, 5 m/s — taş ivmesi
     ∫|a|dt vs I/m; kütle; taş en büyük ilerlemesi, taban iç enerjisi (veri)
  V17 kuş çarpması (K12, SPH) 1.82 kg, L/D 2, 150 m/s, plaka 600² × 6 — Wilbeck:
     kararlı akış kuvveti ρ·A·v², darbe süresi L/v, impuls / m·v (veri)
  V18 mayın / araç altı patlama (K13, /LOAD/PBLAST zemin yansımalı) — Hopkinson–
     Cranz küp kök ölçekleme: (W, R, a) ile (W/8, R/2, a/2) serbest plaka impulsu 8×,
     varış süresi 2×; ankastre taban plakası çökmesi (veri)
  V12 S-kiriş (K7) 50 kg kılavuzlu kızak, 5 m/s — impuls M·(v0 + v_son); ortalama kuvvet
     IE/δ / aynı kesitli düz tüp W&A (veri: eğilmeli çökme)
  V11 227 kg Ø250, H 5.21 m (11.6 kJ), tavan 1200² × 6 — KE₀ = m·g·H; temasa
     kadar düşülen mesafe ve cisim en büyük ilerlemesi (veri; v = −v0 − g·t + I/m)

Kullanım (backend kökünden, sunucu açıkken):
    .\\.venv\\Scripts\\python.exe scripts/crash_validation.py [--quick] [--only V4,V5]
--only: yalnız verilen vakaları koşar, mevcut rapordaki diğerlerini korur.
"""

from __future__ import annotations

import json
import math
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.postprocess.crash_validation import (  # noqa: E402
    clamped_square_plate_stiffness_n_per_mm,
    contact_duration_ms,
    drop_wall_impulse_ns,
    free_fall_contact_ms,
    contact_window,
    elastic_impact_force_kn,
    plateau_kn,
    quasi_static_impact,
    ratio,
    recht_ipson_fit,
    taylor_final_shape,
    wilkins_guinan_ratio,
    sled_crush,
    tube_mean_crush_force_kn,
    wave_speeds,
)

API = "http://localhost:8000"
OUT = ROOT.parent / "docs" / "validation"
# Malzeme S235 (kütüphane): ρ 7850, E 210 GPa, ν 0.3, σy 235 MPa
RHO, E, NU, SY = 7850.0, 210e9, 0.3, 235.0
L, H, B, T = 300.0, 50.0, 40.0, 3.0
MID_H, MID_B = H - T, B - T  # orta yüzey kenarları 47 × 37
AREA = 2.0 * (MID_H + MID_B) * T  # 504 mm²
V0 = 10.0
SLED_KG = 50.0  # TEST değeri — mühendis kararı değil (Pm teoride kütleden bağımsız)


def _post(body: dict) -> dict:
    req = urllib.request.Request(
        f"{API}/crash/scenario", data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=3600) as r:
        return json.loads(r.read().decode("utf-8"))


_STEP = {"V4": "1.18e", "V5": "1.18e", "V6": "K1", "V7": "K2", "V8": "K3", "V9": "K4", "V10": "K5", "V11": "K6", "V12": "K7", "V13": "K8", "V14": "K9", "V15": "K10", "V16": "K11", "V17": "K12", "V18": "K13"}


def _run(name: str, body: dict) -> tuple[dict, dict, float]:
    t0 = time.time()
    res = _post({"name": f"{_STEP.get(name.split()[0], '1.17f')} {name}", "wait": True, **body})
    wall = time.time() - t0
    crash = res["crash"]
    if crash["status"] != "solved":
        raise RuntimeError(f"{name}: {crash['status']} {crash.get('message')}")
    job = json.loads((ROOT / "uploads" / "crash" / crash["job_id"] / "job.json").read_text(encoding="utf-8"))
    return crash, job, wall


def _common(job: dict) -> dict:
    s = job["scalars"]
    return {
        "energy_balance_rel": s.get("energy_balance_rel"),
        "hourglass_ratio": s.get("hourglass_ratio"),
        "timestep_min_ms": s.get("timestep_min"),
        "mass_model_kg": s.get("mass_model"),
    }


def v1_elastic() -> dict:
    crash, job, wall = _run("V1 elastik LAW1", {"t_end_ms": 0.4, "engine": {"th_dt_ms": 0.001},
                                                "model": {"law": "elastic"}})
    c = job["curves"]
    t, f = c["time"], c["rwall_force"]
    ta, tb = contact_window(t, f)
    dur = tb - ta
    plat = plateau_kn(t, f, ta + 0.2 * dur, ta + 0.8 * dur)
    ws = wave_speeds(E, RHO, NU)
    m = job["scalars"]["mass_model"]
    imp = job["scalars"]["rwall_impulse_final"]
    refs = {k: elastic_impact_force_kn(RHO, v, V0, AREA) for k, v in ws.items()}
    durs = {k: contact_duration_ms(L, v) for k, v in ws.items()}
    return {
        "id": "V1", "title": "Elastik kutu rijit duvara (LAW1)", "run_id": crash["run_id"], "wall_s": wall,
        "rows": [
            {"quantity": "Plato kuvveti (kN)", "sim": plat, "ref": refs["c0"], "ref_label": "ρ·c₀·v·A (çubuk)",
             "ratio": ratio(plat, refs["c0"]), "alt_ref": refs["cp"], "alt_label": "ρ·c_p·v·A (levha)"},
            {"quantity": "Temas süresi (ms)", "sim": dur, "ref": durs["c0"], "ref_label": "2L/c₀",
             "ratio": ratio(dur, durs["c0"]), "alt_ref": durs["cp"], "alt_label": "2L/c_p"},
            {"quantity": "Duvar impulsu (N·s)", "sim": imp, "ref": 2 * m * V0, "ref_label": "2·M·v0 (elastik geri sekme)",
             "ratio": ratio(imp, 2 * m * V0)},
        ],
        **_common(job),
    }


def v2_plastic() -> dict:
    crash, job, wall = _run("V2 elasto-plastik LAW2", {"t_end_ms": 0.4, "engine": {"th_dt_ms": 0.001},
                                                       "model": {"law": "plastic"}})
    c, s = job["curves"], job["scalars"]
    t, f = c["time"], c["rwall_force"]
    ta, tb = contact_window(t, f)
    dur = tb - ta
    plat = plateau_kn(t, f, ta + 0.2 * dur, ta + 0.8 * dur)
    m = s["mass_model"]
    v_end = math.sqrt(2.0 * max(s.get("kinetic_energy_final", 0.0), 0.0) / m)  # büyüklük; geri sekme yönü varsayılır
    imp = s["rwall_impulse_final"]
    return {
        "id": "V2", "title": "Elasto-plastik kutu rijit duvara (LAW2, kısa)", "run_id": crash["run_id"], "wall_s": wall,
        "rows": [
            {"quantity": "Plato kuvveti (kN)", "sim": plat, "ref": SY * AREA / 1e3, "ref_label": "σy·A",
             "ratio": ratio(plat, SY * AREA / 1e3)},
            {"quantity": "Duvar impulsu (N·s)", "sim": imp, "ref": m * (V0 + v_end),
             "ref_label": "M·(v0 + v_son), v_son = √(2·KE_son/M)", "ratio": ratio(imp, m * (V0 + v_end))},
            {"quantity": "Temas süresi (ms)", "sim": dur, "ref": None, "ref_label": "— (plastik dalga; analitik yok)",
             "ratio": None},
        ],
        **_common(job),
    }


def v3_sled(sizes: list[float]) -> dict:
    pm_ref = tube_mean_crush_force_kn(SY, T, (MID_H + MID_B) / 2.0)
    mesh_rows = []
    for es in sizes:
        crash, job, wall = _run(
            f"V3 kızak {SLED_KG:g} kg (test) eleman {es:g} mm",
            {"t_end_ms": 15.0, "element_size_mm": es, "engine": {"th_dt_ms": 0.01},
             "rigid_bodies": [{"name": "kizak", "region": "kutu_arka", "mass_kg": SLED_KG}]},
        )
        c, s = job["curves"], job["scalars"]
        m = s["mass_model"]
        cr = sled_crush(c["time"], c["rwall_impulse"], m, V0)
        # durma anındaki iç enerji (doğrusal aradeğer)
        t, ie = c["time"], c["internal_energy"]
        k = next((i for i, x in enumerate(t) if x >= cr["t_stop_ms"]), len(t) - 1)
        ie_stop = ie[k]
        pm_sim = ie_stop / cr["crush_mm"] if cr["crush_mm"] > 0 else float("nan")
        f_mean = plateau_kn(t, c["rwall_force"], 0.0, cr["t_stop_ms"])
        mesh_rows.append({
            "element_mm": es, "run_id": crash["run_id"], "wall_s": wall,
            "crush_mm": cr["crush_mm"], "t_stop_ms": cr["t_stop_ms"], "ie_stop_j": ie_stop,
            "pm_energy_kn": pm_sim, "f_mean_kn": f_mean, "f_peak_kn": s.get("rwall_force_max"),
            "ratio_wa": ratio(pm_sim, pm_ref["wierzbicki_abramowicz_1983"]),
            "ratio_aj": ratio(pm_sim, pm_ref["abramowicz_jones_1984"]),
            **_common(job),
        })
        print(f"  V3 {es} mm: δ {cr['crush_mm']:.1f} mm, Pm {pm_sim:.2f} kN, {wall:.0f} s", flush=True)
    return {
        "id": "V3", "title": f"Kızaklı eksenel ezilme ({SLED_KG:g} kg test kütlesi) + mesh yakınsaması",
        "references": {
            "wierzbicki_abramowicz_1983_kn": pm_ref["wierzbicki_abramowicz_1983"],
            "abramowicz_jones_1984_kn": pm_ref["abramowicz_jones_1984"],
            "formula": "Pm = k·σ0·t^(5/3)·C^(1/3), k = 9.56 (W&A 1983) | 13.06 (A&J 1984), σ0 = σy, C = (47+37)/2 mm",
        },
        "mesh": mesh_rows,
    }


# 1.18e — plaka–küre (TEST: ağır küre 50 kg, 1 m/s → yarı-statik varsayımı için)
PB_A, PB_T, PB_D, PB_GAP = 300.0, 5.0, 50.0, 1.0
PB_MASS_KG, PB_V0 = 50.0, 1.0


def v4_plate_ball_elastic() -> dict:
    k = clamped_square_plate_stiffness_n_per_mm(E, NU, PB_T, PB_A)
    crash, job, wall = _run("V4 plaka–küre elastik yarı-statik", {
        "template_id": "plate_ball_shell",
        "geometry": {"plate_size": PB_A, "plate_thickness": PB_T, "ball_diameter": PB_D, "gap": PB_GAP},
        "speed_m_s": PB_V0, "t_end_ms": 14.0, "ball_mass_kg": PB_MASS_KG,
        "engine": {"th_dt_ms": 0.02}, "model": {"law": "elastic"},
        # Ham tepe plaka modlarının yüksek frekanslı salınımını taşır; yarı-statik
        # tepe (temel frekans ~50 Hz) için CFC60 süzülmüş tepe ayrıca raporlanır.
        "filters": {"force_cfc": 60},
    })
    c, s = job["curves"], job["scalars"]
    t, f, imp = c["time"], c["contact_1_force"], c["contact_1_impulse"]
    m = 2.0 * s["kinetic_energy_max"] / (PB_V0 * PB_V0)  # küre kütlesi (kabuk + ek)
    ref = quasi_static_impact(k, m, PB_V0)
    ta, tb = contact_window(t, f)
    # temastan sonra küre ilerlemesi: v(t) = v0 − I(t)/m (plakaya doğru +), ∫ v dt
    k0 = next(i for i, x in enumerate(t) if x >= ta)
    travel, best = 0.0, 0.0
    for i in range(k0 + 1, len(t)):
        v_a, v_b = PB_V0 - imp[i - 1] / m, PB_V0 - imp[i] / m
        travel += 0.5 * (v_a + v_b) * (t[i] - t[i - 1])
        best = max(best, travel)
    imp_end = s["contact_1_impulse_final"]
    return {
        "id": "V4", "title": f"Plaka–küre elastik yarı-statik (LAW1, küre {PB_MASS_KG:g} kg test, {PB_V0:g} m/s)",
        "run_id": crash["run_id"], "wall_s": wall,
        "references": {"k_n_per_mm": k, "ball_mass_kg": m,
                       "formula": "k = D/(0.0056·a²), D = E·t³/12(1−ν²); F = v·√(k·m), δ = v·√(m/k), T = π·√(m/k)"},
        "rows": [
            {"quantity": "Temas tepe kuvveti (kN)", "sim": s["contact_1_force_max"], "ref": ref["force_max_kn"],
             "ref_label": "v·√(k·m)", "ratio": ratio(s["contact_1_force_max"], ref["force_max_kn"])},
            {"quantity": "Temas tepe kuvveti CFC60 (kN)", "sim": s.get("contact_1_force_max_cfc60"),
             "ref": ref["force_max_kn"], "ref_label": "v·√(k·m)",
             "ratio": ratio(s.get("contact_1_force_max_cfc60") or float("nan"), ref["force_max_kn"])},
            {"quantity": "Küre en büyük ilerlemesi (mm)", "sim": best, "ref": ref["deflection_max_mm"],
             "ref_label": "v·√(m/k) (plaka çökmesi)", "ratio": ratio(best, ref["deflection_max_mm"])},
            {"quantity": "Temas süresi (ms)", "sim": tb - ta, "ref": ref["contact_ms"], "ref_label": "π·√(m/k)",
             "ratio": ratio(tb - ta, ref["contact_ms"])},
            {"quantity": "Temas impulsu (N·s)", "sim": imp_end, "ref": 2.0 * m * PB_V0,
             "ref_label": "2·m·v0 (elastik geri sekme)", "ratio": ratio(imp_end, 2.0 * m * PB_V0)},
        ],
        **_common(job),
    }


def v5_recht_ipson() -> dict:
    sweep = json.loads((OUT / "plate_ball_sweep.json").read_text(encoding="utf-8"))
    rows = [r for r in sweep["rows"] if r.get("status") == "solved"]
    perf = [r for r in rows if (r.get("elements_deleted") or 0) > 0 and r["v_res_impulse_m_s"] < 0]
    intact = [r for r in rows if r not in perf]
    fit = recht_ipson_fit([r["v0_m_s"] for r in perf], [abs(r["v_res_impulse_m_s"]) for r in perf])
    lo = max((r["v0_m_s"] for r in intact), default=None)
    hi = min((r["v0_m_s"] for r in perf), default=None)
    points = []
    for r in perf:
        pred = fit["a"] * math.sqrt(max(r["v0_m_s"] ** 2 - fit["v_bl_m_s"] ** 2, 0.0))
        points.append({"v0_m_s": r["v0_m_s"], "run_id": r["run_id"], "v_res_sim": abs(r["v_res_impulse_m_s"]),
                       "v_res_fit": pred, "ratio": ratio(abs(r["v_res_impulse_m_s"]), pred)})
    return {
        "id": "V5", "title": "Plaka–küre Recht–Ipson (p = 2) uydurması — 1.18d tarama (TEST değerleri)",
        "references": {"formula": "v_r = a·√(v0² − v_bl²); en küçük kareler v_r² ~ v0²",
                       "sweep_setup": sweep["setup"], "sweep_generated": sweep["generated"]},
        "fit": {**fit, "bracket_low_m_s": lo, "bracket_high_m_s": hi,
                "v_bl_in_bracket": bool(lo is not None and hi is not None and lo <= fit["v_bl_m_s"] <= hi)},
        "rows": [{"quantity": f"Son hız v0 = {pt['v0_m_s']:g} m/s (#{pt['run_id']})", "sim": pt["v_res_sim"],
                  "ref": pt["v_res_fit"], "ref_label": "Recht–Ipson uydurma", "ratio": pt["ratio"]}
                 for pt in points],
    }


# K1 — Taylor çubuğu (L0 50, D0 10; S235 LAW2 mükemmel plastik b = 0)
TB_L0, TB_D0 = 50.0, 10.0
TB_CASES = ((100.0, 1.5), (150.0, 1.5), (100.0, 1.0))  # (v0 m/s, eleman mm)


def _animation(run_id: int) -> dict:
    with urllib.request.urlopen(f"{API}/crash/runs/{run_id}/animation", timeout=3600) as r:
        return json.loads(r.read().decode("utf-8"))


def v6_taylor() -> dict:
    rows, runs = [], []
    for v0, es in TB_CASES:
        crash, job, wall = _run(f"V6 Taylor {v0:g} m/s eleman {es:g} mm", {
            "template_id": "taylor_bar", "geometry": {"length": TB_L0, "diameter": TB_D0},
            "speed_m_s": v0, "t_end_ms": 0.5, "element_size_mm": es,
            "engine": {"th_dt_ms": 0.002}, "model": {"law": "plastic"},
        })
        s = job["scalars"]
        anim = _animation(crash["run_id"])
        shape = taylor_final_shape(anim["faces"], anim["frames"][-1]["positions"])
        ratio_sim = shape["length_mm"] / TB_L0
        ref = wilkins_guinan_ratio(RHO, v0, SY * 1e6)
        m = s["mass_model"]
        v_end = math.sqrt(2.0 * max(s.get("kinetic_energy_final", 0.0), 0.0) / m)
        imp = s["rwall_impulse_final"]
        tag = f"v0 {v0:g} m/s, {es:g} mm (#{crash['run_id']})"
        rows += [
            {"quantity": f"L1/L0 — {tag}", "sim": ratio_sim, "ref": ref,
             "ref_label": "Wilkins–Guinan exp(−ρv²/2σy), h = 0", "ratio": ratio(ratio_sim, ref)},
            {"quantity": f"D1/D0 uç çapı — {tag}", "sim": shape["front_diameter_mm"] / TB_D0, "ref": None,
             "ref_label": "— (veri)", "ratio": None},
            {"quantity": f"Duvar impulsu (N·s) — {tag}", "sim": imp, "ref": m * (v0 + v_end),
             "ref_label": "M·(v0 + v_son)", "ratio": ratio(imp, m * (v0 + v_end))},
        ]
        runs.append({"run_id": crash["run_id"], "v0_m_s": v0, "element_mm": es, "wall_s": wall,
                     "L1_mm": shape["length_mm"], "D1_mm": shape["front_diameter_mm"], **_common(job)})
        print(f"  V6 {tag}: L1/L0 {ratio_sim:.4f} (WG {ref:.4f}), {wall:.0f} s", flush=True)
    worst = max(runs, key=lambda r: r["energy_balance_rel"] or 0.0)
    return {
        "id": "V6", "title": f"Taylor çubuğu (S235 LAW2, tet4, L0 {TB_L0:g} / D0 {TB_D0:g} mm)",
        "references": {"formula": "L1/L0 = h/L0 + (1 − h/L0)·exp(−ρ·v0²/(2·σ0)); h = 0 (alt sınır)"},
        "rows": rows, "runs": runs,
        "energy_balance_rel": worst["energy_balance_rel"], "hourglass_ratio": worst["hourglass_ratio"],
    }


# K2 — düşme kutusu 200 × 150 × 50, t 2, S235 LAW2; H 1 m, g 1 mm boşluk
DB_H_MM, DB_GAP, DB_G = 1000.0, 1.0, 9.81
DB_CASES = (("yüzey", {}), ("köşe", {"rot_x": 35.26, "rot_y": 45.0}))


def v7_drop() -> dict:
    rows, runs = [], []
    v0 = math.sqrt(2.0 * DB_G * DB_H_MM / 1000.0)
    for label, rot in DB_CASES:
        crash, job, wall = _run(f"V7 düşme 1 m {label}", {
            "template_id": "drop_box_shell", "geometry": {"gap": DB_GAP, **rot},
            "drop_height_mm": DB_H_MM, "t_end_ms": 5.0, "element_size_mm": 10.0,
            "engine": {"th_dt_ms": 0.005}, "model": {"law": "plastic"},
            "th": {"part": {"vars": ["IE", "KE", "VZ"]}},
        })
        c, s = job["curves"], job["scalars"]
        m = s["mass_model"]
        t, f = c["time"], c["rwall_force"]
        t_on = next((ti for ti, fi in zip(t, f) if abs(fi) > 1e-6), float("nan"))
        t_ref = free_fall_contact_ms(DB_GAP, v0, DB_G)
        vz = c.get("th_part_0_VZ") or []
        imp = s["rwall_impulse_final"]
        imp_ref = drop_wall_impulse_ns(m, -v0, vz[-1], DB_G, t[-1]) if vz else float("nan")
        ke0_ref = m * DB_G * DB_H_MM / 1000.0
        tag = f"{label} (#{crash['run_id']})"
        rows += [
            {"quantity": f"KE₀ (J) — {tag}", "sim": s["kinetic_energy_max"], "ref": ke0_ref,
             "ref_label": "m·g·H", "ratio": ratio(s["kinetic_energy_max"], ke0_ref)},
            {"quantity": f"Temas anı (ms) — {tag}", "sim": t_on, "ref": t_ref,
             "ref_label": f"serbest düşme g = {DB_GAP:g} mm (TH aralığı 0.005 ms)", "ratio": ratio(t_on, t_ref)},
            {"quantity": f"Zemin impulsu (N·s) — {tag}", "sim": imp, "ref": imp_ref,
             "ref_label": "m·(vz_son − vz₀) + m·g·t", "ratio": ratio(imp, imp_ref)},
        ]
        runs.append({"run_id": crash["run_id"], "orientation": label, "wall_s": wall, "vz_end_m_s": vz[-1] if vz else None,
                     "force_max_kn": s.get("rwall_force_max"), "ie_final_j": s.get("internal_energy_final"), **_common(job)})
        print(f"  V7 {tag}: t_on {t_on:.4f} / {t_ref:.4f} ms, I {imp:.3f} / {imp_ref:.3f}", flush=True)
    worst = max(runs, key=lambda r: r["energy_balance_rel"] or 0.0)
    return {
        "id": "V7", "title": "Düşme testi 1 m (kabuk kutu 200×150×50 t2, S235 LAW2, yüzey + köşe)",
        "references": {"formula": "v0 = √(2gH); g = v0·t + ½·g·t²; I = m·(vz_son − vz₀) + m·g·t"},
        "rows": rows, "runs": runs,
        "energy_balance_rel": worst["energy_balance_rel"], "hourglass_ratio": worst["hourglass_ratio"],
    }


# K3 — direk kirişi L 800, h 60, b 40, t 2; uçlar rijit gövde + 10 kg (TEST); 5 m/s
PB_BEAM = {"length": 800.0, "depth": 60.0, "width": 40.0, "wall": 2.0, "gap": 1.0}
PB_END_KG, PB_POLE_V0 = 10.0, 5.0


def v8_pole() -> dict:
    from app.templates.pole_beam_shell import PoleBeamShellParams, plastic_modulus_mm3

    zp = plastic_modulus_mm3(PoleBeamShellParams(**PB_BEAM))
    p_ref = 4.0 * SY * zp / PB_BEAM["length"] / 1e3  # kN
    rows, runs = [], []
    for es in (10.0, 7.5):
        crash, job, wall = _run(f"V8 direk Ø254 eleman {es:g} mm", {
            "template_id": "pole_beam_shell", "geometry": PB_BEAM, "speed_m_s": PB_POLE_V0,
            "end_mass_kg": PB_END_KG, "t_end_ms": 25.0, "element_size_mm": es,
            "engine": {"th_dt_ms": 0.02}, "model": {"law": "plastic"},
        })
        c, s = job["curves"], job["scalars"]
        m = s["mass_model"]
        cr = sled_crush(c["time"], c["rwall_impulse"], m, PB_POLE_V0)
        t, ie = c["time"], c["internal_energy"]
        k = next((i for i, x in enumerate(t) if x >= cr["t_stop_ms"]), len(t) - 1)
        pm = ie[k] / cr["crush_mm"] if cr["crush_mm"] > 0 else float("nan")
        v_end = math.sqrt(2.0 * max(s.get("kinetic_energy_final", 0.0), 0.0) / m)
        imp = s["rwall_impulse_final"]
        tag = f"{es:g} mm (#{crash['run_id']})"
        rows += [
            {"quantity": f"Ortalama direk kuvveti IE/δ (kN) — {tag}", "sim": pm, "ref": p_ref,
             "ref_label": "4·Mp/L (rijit-plastik üç nokta eğilme)", "ratio": ratio(pm, p_ref)},
            {"quantity": f"Direk impulsu (N·s) — {tag}", "sim": imp, "ref": m * (PB_POLE_V0 + v_end),
             "ref_label": "M·(v0 + v_son)", "ratio": ratio(imp, m * (PB_POLE_V0 + v_end))},
        ]
        runs.append({"run_id": crash["run_id"], "element_mm": es, "wall_s": wall, "crush_mm": cr["crush_mm"],
                     "t_stop_ms": cr["t_stop_ms"], "pm_kn": pm, "f_peak_kn": s.get("rwall_force_max"), **_common(job)})
        print(f"  V8 {tag}: δ {cr['crush_mm']:.1f} mm, Pm {pm:.2f} / {p_ref:.2f} kN, {wall:.0f} s", flush=True)
    worst = max(runs, key=lambda r: r["energy_balance_rel"] or 0.0)
    return {
        "id": "V8", "title": f"Direk yan çarpması Ø254 (kiriş L800 h60 b40 t2, S235, uçlar {PB_END_KG:g}+{PB_END_KG:g} kg test, {PB_POLE_V0:g} m/s)",
        "references": {"formula": f"P = 4·Mp/L, Mp = σy·Zp, Zp = t·(h'b' + h'²/2) = {zp:.0f} mm³"},
        "rows": rows, "runs": runs,
        "energy_balance_rel": worst["energy_balance_rel"], "hourglass_ratio": worst["hourglass_ratio"],
    }


# K4 — ROPS portal W 1000, H 1200, 80 × 60 t 4, R 150; S235; itme 1 m/s, 100 mm
RF = {"span": 1000.0, "height": 1200.0, "depth": 80.0, "width": 60.0, "wall": 4.0, "bend_radius": 150.0}
RF_V, RF_T_END = 1.0, 100.0


def v9_rops() -> dict:
    from app.templates.rops_frame_shell import RopsFrameShellParams, plastic_modulus_mm3

    mp = SY * plastic_modulus_mm3(RopsFrameShellParams(**RF))  # N·mm
    ref_h = 4.0 * mp / RF["height"] / 1e3
    ref_hr = 4.0 * mp / (RF["height"] - RF["bend_radius"]) / 1e3
    rows, runs = [], []
    for es in (15.0, 10.0):
        crash, job, wall = _run(f"V9 ROPS itme eleman {es:g} mm", {
            "template_id": "rops_frame_shell", "geometry": RF, "push_speed_m_s": RF_V,
            "t_end_ms": RF_T_END, "element_size_mm": es, "engine": {"th_dt_ms": 0.25},
            "model": {"law": "plastic"},
        })
        c, s = job["curves"], job["scalars"]
        t, f = c["time"], c["section_1_force"]
        d = [RF_V * ti for ti in t]  # mm (m/s = mm/ms)
        plat = plateau_kn(t, f, 40.0 / RF_V, 95.0 / RF_V)
        work = sum(0.5 * (f[i] + f[i - 1]) * (d[i] - d[i - 1]) for i in range(1, len(t)))  # kN·mm = J
        ie = s["internal_energy_final"] + (c.get("hourglass_energy") or [0.0])[-1]
        tag = f"{es:g} mm (#{crash['run_id']})"
        rows += [
            {"quantity": f"Kesit kuvveti platosu δ 40–95 mm (kN) — {tag}", "sim": plat, "ref": ref_h,
             "ref_label": "4·Mp/H (taban + kiriş seviyesi mafsalları)", "ratio": ratio(plat, ref_h),
             "alt_ref": ref_hr, "alt_label": "4·Mp/(H − R) (rijit büküm altı mafsal)"},
            {"quantity": f"∫F dδ (J) — {tag}", "sim": work, "ref": ie, "ref_label": "IE + HG (son)",
             "ratio": ratio(work, ie)},
        ]
        runs.append({"run_id": crash["run_id"], "element_mm": es, "wall_s": wall, "plateau_kn": plat,
                     "f_max_kn": s.get("section_1_force_max"), "work_j": work, **_common(job)})
        print(f"  V9 {tag}: plato {plat:.2f} kN (4Mp/H {ref_h:.2f}, 4Mp/(H−R) {ref_hr:.2f}), {wall:.0f} s", flush=True)
    worst = max(runs, key=lambda r: r["energy_balance_rel"] or 0.0)
    return {
        "id": "V9", "title": "ROPS portal yanal yavaş itme (W1000 H1200, 80×60 t4, R150, S235 LAW2, 1 m/s)",
        "references": {"formula": f"Mp = σy·t·(d·e + d²/2) = {mp / 1e6:.3f} kN·m; F = 4·Mp/H | 4·Mp/(H − R)"},
        "rows": rows, "runs": runs,
        "energy_balance_rel": worst["energy_balance_rel"], "hourglass_ratio": worst["hourglass_ratio"],
    }


# K5 — kafa impaktörü: yetişkin kafa formu Ø165, 4.5 kg; kaput 600 × 600 × 0.8; 40 km/h
HI_GEOM = {"plate_size": 600.0, "plate_thickness": 0.8, "ball_diameter": 165.0, "gap": 1.0}
HI_V0, HI_KG = 11.1, 4.5


def v10_head() -> dict:
    crash, job, wall = _run("V10 kafa impaktörü Ø165 4.5 kg", {
        "template_id": "plate_ball_shell", "geometry": HI_GEOM, "speed_m_s": HI_V0,
        "ball_total_mass_kg": HI_KG, "ball_thickness_mm": 1.0, "t_end_ms": 15.0, "element_size_mm": 10.0,
        "engine": {"th_dt_ms": 0.01}, "model": {"law": "plastic"}, "filters": {"acc_cfc": 1000},
    })
    c, s = job["curves"], job["scalars"]
    m = 2.0 * s["kinetic_energy_max"] / (HI_V0 * HI_V0)
    t, a = c["time"], c["acc_g"]
    dv_acc = sum(0.5 * (a[i] + a[i - 1]) * (t[i] - t[i - 1]) for i in range(1, len(t))) * 9.80665e-3  # g·ms → m/s
    imp = s["contact_1_impulse_final"]
    dv_imp = imp / m
    rows = [
        {"quantity": "Kafa Δv (m/s): ∫|a| dt", "sim": dv_acc, "ref": dv_imp, "ref_label": "temas impulsu / m",
         "ratio": ratio(dv_acc, dv_imp)},
        {"quantity": "Kütle (kg): 2·KE₀/v0²", "sim": m, "ref": HI_KG, "ref_label": "istenen toplam (kabuk + ek)",
         "ratio": ratio(m, HI_KG)},
        {"quantity": "HIC15 (ham)", "sim": s.get("hic15"), "ref": None, "ref_label": "— (veri)", "ratio": None},
        {"quantity": "HIC15 (CFC1000)", "sim": s.get("hic15_cfc1000"), "ref": None, "ref_label": "— (veri)", "ratio": None},
        {"quantity": "Tepe ivme (g, CFC1000)", "sim": s.get("acc_peak_g_cfc1000"), "ref": None, "ref_label": "— (veri)",
         "ratio": None},
    ]
    print(f"  V10 #{crash['run_id']}: Δv {dv_acc:.3f} / {dv_imp:.3f}, HIC15 {s.get('hic15_cfc1000')}", flush=True)
    return {
        "id": "V10", "title": f"Kafa impaktörü Ø165 / {HI_KG:g} kg, {HI_V0:g} m/s, kaput 600×600×0.8 S235 (kenar sabit)",
        "run_id": crash["run_id"], "wall_s": wall,
        "references": {"formula": "∫|a|dt = Δv = I/m (ivme kanalının bütünlüğü); HIC eşiği mühendisin"},
        "rows": rows, **_common(job),
    }


# K6 — FOPS: tavan 1200 × 1200 × 6 S235, cisim Ø250 / 227 kg, H 5210 mm
FO_GEOM = {"plate_size": 1200.0, "plate_thickness": 6.0, "ball_diameter": 250.0, "gap": 1.0}
FO_KG, FO_H, FO_G = 227.0, 5210.0, 9.81


def v11_fops() -> dict:
    v0 = math.sqrt(2.0 * FO_G * FO_H / 1000.0)
    crash, job, wall = _run("V11 FOPS 227 kg H 5.21 m", {
        "template_id": "plate_ball_shell", "geometry": FO_GEOM, "ball_total_mass_kg": FO_KG,
        "ball_thickness_mm": 2.0, "drop_height_mm": FO_H, "gravity": {"accel_m_s2": -FO_G, "direction": "Z"},
        "t_end_ms": 40.0, "element_size_mm": 20.0, "engine": {"th_dt_ms": 0.02}, "model": {"law": "plastic"},
    })
    c, s = job["curves"], job["scalars"]
    t, imp = c["time"], c["contact_1_impulse"]
    m = 2.0 * s["kinetic_energy_max"] / (v0 * v0)
    f = c["contact_1_force"]
    t_on = next((ti for ti, fi in zip(t, f) if abs(fi) > 1e-6), float("nan"))
    # cisim düşey hızı (z yukarı) ve yer değiştirmesi; en büyük aşağı ilerleme − boşluk
    z, z_min = 0.0, 0.0
    vz_prev = -v0
    for i in range(1, len(t)):
        vz = -v0 - FO_G * 1e-3 * t[i] + imp[i] / m
        z += 0.5 * (vz + vz_prev) * (t[i] - t[i - 1])
        vz_prev = vz
        z_min = min(z_min, z)
    travel = -z_min - FO_GEOM["gap"]
    ke0_ref = m * FO_G * FO_H / 1000.0
    rows = [
        {"quantity": "KE₀ (J)", "sim": s["kinetic_energy_max"], "ref": FO_KG * FO_G * FO_H / 1000.0,
         "ref_label": f"m·g·H ({FO_KG:g} kg istenen)", "ratio": ratio(s["kinetic_energy_max"], FO_KG * FO_G * FO_H / 1000.0)},
        # Temas anında kapanan mesafe: TYPE7 boşluğu kabuk kalınlıklarından (orta yüzeyler arası
        # t_plaka/2 + g + t_küre/2 = 5 mm, eksi temas boşluğu) — geometrik g ile kıyaslanmaz, veri.
        {"quantity": "Temas anına kadar düşülen mesafe (mm)", "sim": v0 * t_on + 0.5 * FO_G * 1e-3 * t_on ** 2,
         "ref": None, "ref_label": "— (veri; orta yüzeyler arası 5 mm − TYPE7 temas boşluğu)", "ratio": None},
        {"quantity": "Cisim en büyük ilerlemesi (mm)", "sim": travel, "ref": None,
         "ref_label": "— (veri; tavan çökmesi + yerel ezilme)", "ratio": None},
        {"quantity": "Tavan iç enerjisi (J)", "sim": float((c.get("th_part_0_IE") or [float("nan")])[-1]), "ref": None,
         "ref_label": "— (veri)", "ratio": None},
    ]
    print(f"  V11 #{crash['run_id']}: KE0 {s['kinetic_energy_max']:.0f} / {ke0_ref:.0f} J, ilerleme {travel:.1f} mm", flush=True)
    return {
        "id": "V11", "title": f"FOPS: {FO_KG:g} kg Ø250 küre, H {FO_H / 1000:g} m, tavan 1200²×6 S235 (kenar sabit)",
        "run_id": crash["run_id"], "wall_s": wall,
        "references": {"formula": "v0 = √(2gH), KE₀ = m·g·H; g = v0·t + ½·g·t²; ISO 3449 kriterleri mühendisin"},
        "rows": rows, **_common(job),
    }


# K7 — S-kiriş: L1 100, L2 200, R 150, θ 45°, 60 × 40 t 2; kızak 50 kg (TEST), yalnız x kılavuzlu; 5 m/s
SR_GEOM = {"front_length": 100.0, "rear_length": 200.0, "bend_radius": 150.0, "bend_angle": 45.0,
           "height": 60.0, "width": 40.0, "wall": 2.0}
SR_SLED, SR_V0 = 50.0, 5.0


def v12_s_rail() -> dict:
    crash, job, wall = _run("V12 S-kiriş kızak 50 kg 5 m/s (kılavuzlu)", {
        "template_id": "s_rail_shell", "geometry": SR_GEOM, "speed_m_s": SR_V0, "t_end_ms": 45.0,
        "element_size_mm": 8.0, "engine": {"th_dt_ms": 0.01}, "model": {"law": "plastic"},
        "rigid_bodies": [{"name": "kizak", "region": "arka_halka", "mass_kg": SR_SLED}],
    })
    c, s = job["curves"], job["scalars"]
    m = s["mass_model"]
    cr = sled_crush(c["time"], c["rwall_impulse"], m, SR_V0)
    t, ie = c["time"], c["internal_energy"]
    k = next((i for i, x in enumerate(t) if x >= cr["t_stop_ms"]), len(t) - 1)
    pm = ie[k] / cr["crush_mm"] if cr["crush_mm"] > 0 else float("nan")
    wa = tube_mean_crush_force_kn(SY, SR_GEOM["wall"], (SR_GEOM["height"] - SR_GEOM["wall"] + SR_GEOM["width"] - SR_GEOM["wall"]) / 2.0)
    v_end = math.sqrt(2.0 * max(s.get("kinetic_energy_final", 0.0), 0.0) / m)
    imp = s["rwall_impulse_final"]
    # Kızak koşu sonunda hâlâ ileri gidiyorsa (I < M·v0) son hız aynı yönde: M·(v0 − v_son).
    sign = -1.0 if imp < m * SR_V0 else 1.0
    imp_ref = m * (SR_V0 + sign * v_end)
    rows = [
        {"quantity": "Duvar impulsu (N·s)", "sim": imp, "ref": imp_ref,
         "ref_label": "M·(v0 ∓ v_son), v_son = √(2·KE_son/M) (ileri: −, geri sekme: +)",
         "ratio": ratio(imp, imp_ref)},
        {"quantity": "Ortalama kuvvet IE/δ (kN)", "sim": pm, "ref": wa["wierzbicki_abramowicz_1983"],
         "ref_label": "aynı kesitli DÜZ tüp eksenel ezilme (W&A) — veri, eğilmeli çökme beklenir",
         "ratio": ratio(pm, wa["wierzbicki_abramowicz_1983"])},
        {"quantity": "Ezilme δ (mm)", "sim": cr["crush_mm"], "ref": None, "ref_label": "— (veri)", "ratio": None},
        {"quantity": "Tepe kuvvet (kN)", "sim": s.get("rwall_force_max"), "ref": None, "ref_label": "— (veri)", "ratio": None},
    ]
    print(f"  V12 #{crash['run_id']}: δ {cr['crush_mm']:.1f} mm, Pm {pm:.2f} kN (düz W&A {wa['wierzbicki_abramowicz_1983']:.2f})", flush=True)
    return {
        "id": "V12", "title": f"S-kiriş (L1 100, L2 200, R150, θ45°, 60×40 t2, S235), kızak {SR_SLED:g} kg test, {SR_V0:g} m/s",
        "run_id": crash["run_id"], "wall_s": wall,
        "references": {"formula": "I = M·(v0 + v_son); Pm = IE(t_dur) / δ; düz tüp W&A 9.56·σ0·t^(5/3)·C^(1/3)"},
        "rows": rows, **_common(job),
    }


# K8 — kapı darbe kirişi L 800, 40 × 30 t 1.5, S235; Ø305 silindir, 1 m/s, 120 mm
DB2 = {"length": 800.0, "depth": 40.0, "width": 30.0, "wall": 1.5, "impactor_diameter": 305.0, "gap": 1.0}
DB2_V, DB2_T = 1.0, 120.0


def v13_door() -> dict:
    from app.templates.door_beam_shell import DoorBeamShellParams, plastic_modulus_mm3

    mp = SY * plastic_modulus_mm3(DoorBeamShellParams(**DB2))
    p_ref = 8.0 * mp / DB2["length"] / 1e3
    crash, job, wall = _run("V13 kapı intrüzyonu Ø305 1 m/s", {
        "template_id": "door_beam_shell", "geometry": DB2, "push_speed_m_s": DB2_V, "t_end_ms": DB2_T,
        "element_size_mm": 8.0, "engine": {"th_dt_ms": 0.25}, "model": {"law": "plastic"},
    })
    c, s = job["curves"], job["scalars"]
    t, f = c["time"], c["contact_1_force"]
    d = [DB2_V * ti for ti in t]
    plat = plateau_kn(t, f, 5.0 / DB2_V, 20.0 / DB2_V)
    work = sum(0.5 * (f[i] + f[i - 1]) * (d[i] - d[i - 1]) for i in range(1, len(t)))
    ie = s["internal_energy_final"] + (c.get("hourglass_energy") or [0.0])[-1]
    k_end = len(t) - 1
    rows = [
        {"quantity": "Temas kuvveti platosu δ 5–20 mm (kN)", "sim": plat, "ref": p_ref,
         "ref_label": "8·Mp/L (ankastre kiriş, orta yük, rijit-plastik)", "ratio": ratio(plat, p_ref)},
        {"quantity": "∫F dδ (J)", "sim": work, "ref": ie, "ref_label": "IE + HG (son)", "ratio": ratio(work, ie)},
        {"quantity": f"Kuvvet δ = {d[k_end]:.0f} mm (kN)", "sim": f[k_end], "ref": None,
         "ref_label": "— (veri; büyük çökmede membran sertleşmesi)", "ratio": None},
    ]
    print(f"  V13 #{crash['run_id']}: plato {plat:.2f} / {p_ref:.2f} kN, F_son {f[k_end]:.2f} kN", flush=True)
    return {
        "id": "V13", "title": "Kapı intrüzyonu (darbe kirişi L800 40×30 t1.5 S235, uçlar ankastre; Ø305 silindir, 1 m/s)",
        "run_id": crash["run_id"], "wall_s": wall,
        "references": {"formula": f"Mp = σy·t·(h'b' + h'²/2) = {mp / 1e6:.3f} kN·m; P = 8·Mp/L = {p_ref:.2f} kN"},
        "rows": rows, **_common(job),
    }


# K9 — Hopkinson: Ø20, çarpıcı 100, giriş 500 (S235 elastik LAW1), 10 m/s
HB = {"diameter": 20.0, "striker_length": 100.0, "bar_length": 500.0, "gap": 0.5}
HB_V0 = 10.0


def v14_hopkinson() -> dict:
    crash, job, wall = _run("V14 Hopkinson çarpıcı 10 m/s", {
        "template_id": "hopkinson_bar", "geometry": HB, "speed_m_s": HB_V0, "t_end_ms": 0.15,
        "element_size_mm": 3.0, "engine": {"th_dt_ms": 0.0005}, "model": {"law": "elastic"},
    })
    c, s = job["curves"], job["scalars"]
    t, f = c["time"], c["section_1_force"]
    c0 = wave_speeds(E, RHO, NU)["c0"]
    area = math.pi * HB["diameter"] ** 2 / 4.0
    f_ref = elastic_impact_force_kn(RHO, c0, HB_V0, area) / 2.0
    ta, tb = contact_window(t, f, frac=0.5)
    dur = tb - ta
    plat = plateau_kn(t, f, ta + 0.2 * dur, ta + 0.8 * dur)
    dur_ref = contact_duration_ms(HB["striker_length"], c0)
    # Dalga yolu: temas kuvvetinin yarı genlik anından kesit kuvvetinin yarı genlik
    # anına (temas TYPE7 boşluğu geometrik g'den önce kapanır — K6 notu).
    tc, _tce = contact_window(t, c["contact_1_force"], frac=0.5)
    travel_ref = (HB["bar_length"] / 4.0) / c0
    rows = [
        {"quantity": "Kesit kuvveti platosu (kN)", "sim": plat, "ref": f_ref, "ref_label": "ρ·c₀·v0·A / 2 (eşit empedans)",
         "ratio": ratio(plat, f_ref)},
        {"quantity": "Darbe süresi, yarı genlikte (ms)", "sim": dur, "ref": dur_ref, "ref_label": "2·Ls/c₀",
         "ratio": ratio(dur, dur_ref)},
        {"quantity": "Dalga yolu süresi temas → x = Li/4 (ms)", "sim": ta - tc, "ref": travel_ref,
         "ref_label": "(Li/4)/c₀ (yarı genlik anları)", "ratio": ratio(ta - tc, travel_ref)},
    ]
    print(f"  V14 #{crash['run_id']}: plato {plat:.2f} / {f_ref:.2f} kN, süre {dur:.4f} / {dur_ref:.4f} ms", flush=True)
    return {
        "id": "V14", "title": "Hopkinson çubuğu (Ø20, Ls 100, Li 500, S235 elastik LAW1, tet4 3 mm, 10 m/s)",
        "run_id": crash["run_id"], "wall_s": wall,
        "references": {"formula": f"c₀ = √(E/ρ) = {c0:.0f} m/s; σ = ρ·c₀·v0/2; süre 2·Ls/c₀"},
        "rows": rows, **_common(job),
    }


# K10 — patlama yüklü plaka: 400 × 400 × 3 S235, Ps 2 MPa, td 0.2 ms, b 1
BP = {"plate_size": 400.0, "plate_thickness": 3.0}
BP_PS, BP_TD, BP_B = 2.0, 0.2, 1.0


def v15_blast() -> dict:
    from app.solvers.crash_params import CrashPressureLoadParams

    pl = CrashPressureLoadParams(peak_mpa=BP_PS, duration_ms=BP_TD, decay=BP_B)
    i_app = pl.impulse_per_area_mpa_ms() * BP["plate_size"] ** 2 / 1e3  # MPa·ms·mm² = N·ms → N·s
    crash, job, wall = _run("V15 patlama plaka Ps 2 MPa td 0.2 ms", {
        "template_id": "blast_plate_shell", "geometry": BP, "blast_peak_mpa": BP_PS, "blast_duration_ms": BP_TD,
        "blast_decay": BP_B, "t_end_ms": 3.0, "element_size_mm": 10.0, "engine": {"th_dt_ms": 0.005},
        "model": {"law": "plastic"}, "th": {"part": {"vars": ["IE", "KE", "ZMOM"]}},
    })
    c, s = job["curves"], job["scalars"]
    t, zm = c["time"], [abs(v) for v in c.get("th_part_0_ZMOM") or []]
    k = min(range(len(t)), key=lambda i: abs(t[i] - BP_TD))
    # Kontrol: kenarlar neredeyse serbest (yalnız Rx) — mesnet tepkisi yok, momentum = impuls.
    crash_f, job_f, _w = _run("V15 patlama kontrol serbest plaka", {
        "template_id": "blast_plate_shell", "geometry": BP, "blast_peak_mpa": BP_PS, "blast_duration_ms": BP_TD,
        "blast_decay": BP_B, "t_end_ms": 0.4, "element_size_mm": 10.0, "engine": {"th_dt_ms": 0.005},
        "model": {"law": "plastic"}, "th": {"part": {"vars": ["IE", "KE", "ZMOM"]}},
        "boundary_conditions": [{"name": "neredeyse_serbest", "region": "plaka_kenar", "dofs": "000100"}],
    })
    cf = job_f["curves"]
    zf = abs(cf["th_part_0_ZMOM"][min(range(len(cf["time"])), key=lambda i: abs(cf["time"][i] - BP_TD))])
    anim = _animation(crash["run_id"])
    disp = anim["frames"][-1].get("node", {}).get("disp_mag") or [0.0]
    disp_peak = max(max(f.get("node", {}).get("disp_mag") or [0.0]) for f in anim["frames"])
    rows = [
        {"quantity": f"Serbest plaka momentumu |ZMOM| t = td (N·s) (#{crash_f['run_id']})", "sim": zf, "ref": i_app,
         "ref_label": "A·∫p dt (Friedlander kapalı form)", "ratio": ratio(zf, i_app)},
        {"quantity": "Ankastre plaka |ZMOM| t = td (N·s)", "sim": zm[k] if zm else None, "ref": i_app,
         "ref_label": "A·∫p dt — veri: mesnetler darbe sırasında momentum alır",
         "ratio": ratio(zm[k], i_app) if zm else None},
        {"quantity": "En büyük yer değiştirme, tüm kareler (mm)", "sim": disp_peak, "ref": None,
         "ref_label": "— (veri; anim kare aralığıyla)", "ratio": None},
        {"quantity": "Son karede en büyük yer değiştirme (mm)", "sim": max(disp), "ref": None,
         "ref_label": "— (veri; kalıcı + titreşim)", "ratio": None},
        {"quantity": "Plaka iç enerjisi son (J)", "sim": s.get("internal_energy_final"), "ref": None, "ref_label": "— (veri)",
         "ratio": None},
    ]
    print(f"  V15 #{crash['run_id']}: ZMOM(td) {zm[k] if zm else float('nan'):.2f} / I {i_app:.2f} N·s, δ {max(disp):.1f} mm", flush=True)
    return {
        "id": "V15", "title": "Patlama yüklü plaka (400×400×3 S235 ankastre; Friedlander Ps 2 MPa, td 0.2 ms, b 1)",
        "run_id": crash["run_id"], "wall_s": wall,
        "references": {"formula": "I/A = Ps·td·[1/b − (1 − e^(−b))/b²]; momentum = impuls (kısa darbe)"},
        "rows": rows, **_common(job),
    }


# K11 — kepçe tabanı R 500, φ 90°, W 600, t 10 S235; taş Ø200, toplam 300 kg; 5 m/s
BR = {"radius": 500.0, "angle": 90.0, "width": 600.0, "thickness": 10.0, "rock_diameter": 200.0, "gap": 1.0}
BR_KG, BR_V0 = 300.0, 5.0


def v16_bucket() -> dict:
    crash, job, wall = _run("V16 kepçe taş 300 kg 5 m/s", {
        "template_id": "bucket_rock_shell", "geometry": BR, "speed_m_s": BR_V0, "ball_total_mass_kg": BR_KG,
        "ball_thickness_mm": 2.0, "t_end_ms": 20.0, "element_size_mm": 20.0, "engine": {"th_dt_ms": 0.01},
        "model": {"law": "plastic"},
    })
    c, s = job["curves"], job["scalars"]
    m = 2.0 * s["kinetic_energy_max"] / (BR_V0 * BR_V0)
    t, a = c["time"], c["acc_g"]
    dv_acc = sum(0.5 * (a[i] + a[i - 1]) * (t[i] - t[i - 1]) for i in range(1, len(t))) * 9.80665e-3
    imp = c["contact_1_impulse"]
    dv_imp = imp[-1] / m
    z, z_min, vz_prev = 0.0, 0.0, -BR_V0
    for i in range(1, len(t)):
        vz = -BR_V0 + imp[i] / m
        z += 0.5 * (vz + vz_prev) * (t[i] - t[i - 1])
        vz_prev = vz
        z_min = min(z_min, z)
    rows = [
        {"quantity": "Taş Δv: ∫|a| dt (m/s)", "sim": dv_acc, "ref": dv_imp, "ref_label": "temas impulsu / m",
         "ratio": ratio(dv_acc, dv_imp)},
        {"quantity": "Taş kütlesi 2·KE₀/v0² (kg)", "sim": m, "ref": BR_KG, "ref_label": "istenen toplam",
         "ratio": ratio(m, BR_KG)},
        {"quantity": "Taş en büyük ilerlemesi (mm)", "sim": -z_min - BR["gap"], "ref": None,
         "ref_label": "— (veri; taban çökmesi + temas boşluğu)", "ratio": None},
        {"quantity": "Taban iç enerjisi son (J)", "sim": float((c.get("th_part_0_IE") or [float("nan")])[-1]),
         "ref": None, "ref_label": "— (veri)", "ratio": None},
        {"quantity": "Temas tepe kuvveti (kN)", "sim": s.get("contact_1_force_max"), "ref": None,
         "ref_label": "— (veri)", "ratio": None},
    ]
    print(f"  V16 #{crash['run_id']}: Δv {dv_acc:.3f} / {dv_imp:.3f}, ilerleme {-z_min - BR['gap']:.1f} mm", flush=True)
    return {
        "id": "V16", "title": "Kepçe / taş (taban R500 φ90° W600 t10 S235, kenarlar sabit; taş Ø200 / 300 kg, 5 m/s)",
        "run_id": crash["run_id"], "wall_s": wall,
        "references": {"formula": "∫|a|dt = Δv = I/m; KE₀ = ½·m·v0²"},
        "rows": rows, **_common(job),
    }


# K12 — kuş çarpması (SPH): 1.82 kg, L/D 2, ρ 950, 150 m/s; plaka 600 × 600 × 6 S235 ankastre
BS_KG, BS_LD, BS_RHO, BS_V0 = 1.82, 2.0, 950.0, 150.0


def v17_bird() -> dict:
    crash, job, wall = _run("V17 kuş 1.82 kg 150 m/s SPH", {
        "template_id": "blast_plate_shell", "geometry": {"plate_size": 600.0, "plate_thickness": 6.0},
        "bird_mass_kg": BS_KG, "bird_ld": BS_LD, "speed_m_s": BS_V0, "t_end_ms": 3.0, "element_size_mm": 15.0,
        "engine": {"th_dt_ms": 0.005}, "model": {"law": "plastic"},
    })
    c, s = job["curves"], job["scalars"]
    m = 2.0 * s["kinetic_energy_max"] / (BS_V0 * BS_V0)
    # Kontrol: plakanın tüm düğümleri sabit (rijit hedef) — Wilbeck bağıntıları rijit hedef içindir.
    crash_r, job_r, _w = _run("V17 kuş rijit hedef kontrol", {
        "template_id": "blast_plate_shell", "geometry": {"plate_size": 600.0, "plate_thickness": 6.0},
        "bird_mass_kg": BS_KG, "bird_ld": BS_LD, "speed_m_s": BS_V0, "t_end_ms": 3.0, "element_size_mm": 15.0,
        "engine": {"th_dt_ms": 0.005}, "model": {"law": "plastic"},
        "boundary_conditions": [{"name": "rijit_hedef", "region": "plaka", "dofs": "111111"}],
    })
    cr_, sr_ = job_r["curves"], job_r["scalars"]
    vol = BS_KG / BS_RHO * 1e9
    r = (vol / (math.pi * (2.0 * BS_LD - 2.0 + 4.0 / 3.0))) ** (1.0 / 3.0)
    length, area = 2.0 * r * BS_LD, math.pi * r * r
    t, f = c["time"], c["contact_1_force"]
    ta, tb = contact_window(t, f, frac=0.05)
    f_steady = BS_RHO * area * 1e-6 * BS_V0 ** 2 / 1e3  # kN
    t_ref = length / BS_V0  # ms
    plat = plateau_kn(t, f, ta + 0.25 * t_ref, ta + 0.75 * t_ref)
    imp = s["contact_1_impulse_final"]
    tr, fr = cr_["time"], cr_["contact_1_force"]
    ra, rb = contact_window(tr, fr, frac=0.05)
    plat_r = plateau_kn(tr, fr, ra + 0.25 * t_ref, ra + 0.75 * t_ref)
    imp_r = sr_["contact_1_impulse_final"]
    rows = [
        {"quantity": f"RİJİT hedef: kararlı akış kuvveti (kN) (#{crash_r['run_id']})", "sim": plat_r, "ref": f_steady,
         "ref_label": "ρ·A·v² (Wilbeck)", "ratio": ratio(plat_r, f_steady)},
        {"quantity": "RİJİT hedef: darbe süresi %5 (ms)", "sim": rb - ra, "ref": t_ref, "ref_label": "L/v",
         "ratio": ratio(rb - ra, t_ref)},
        {"quantity": "RİJİT hedef: aktarılan impuls (N·s)", "sim": imp_r, "ref": m * BS_V0,
         "ref_label": "m·v (sıçramasız akış)", "ratio": ratio(imp_r, m * BS_V0)},
        {"quantity": "Kuş kütlesi 2·KE₀/v0² (kg)", "sim": m, "ref": BS_KG, "ref_label": "istenen (SPH kafes yaklaşığı)",
         "ratio": ratio(m, BS_KG)},
        {"quantity": "Ankastre plaka: kararlı akış kuvveti (kN)", "sim": plat, "ref": f_steady,
         "ref_label": "ρ·A·v² — veri (deforme olan hedef)", "ratio": ratio(plat, f_steady)},
        {"quantity": "Ankastre plaka: darbe süresi %5 (ms)", "sim": tb - ta, "ref": t_ref, "ref_label": "L/v — veri",
         "ratio": ratio(tb - ta, t_ref)},
        {"quantity": "Ankastre plaka: aktarılan impuls (N·s)", "sim": imp, "ref": m * BS_V0,
         "ref_label": "m·v — veri (plaka geri iter)", "ratio": ratio(imp, m * BS_V0)},
        {"quantity": "Tepe temas kuvveti (kN)", "sim": s.get("contact_1_force_max"), "ref": None,
         "ref_label": "— (Hugoniot evresi, veri)", "ratio": None},
    ]
    print(f"  V17 #{crash['run_id']}: plato {plat:.1f} / {f_steady:.1f} kN, süre {tb - ta:.3f} / {t_ref:.3f} ms", flush=True)
    return {
        "id": "V17", "title": f"Kuş çarpması SPH ({BS_KG:g} kg, L/D {BS_LD:g}, {BS_V0:g} m/s; plaka 600²×6 S235 ankastre)",
        "run_id": crash["run_id"], "wall_s": wall,
        "references": {"formula": f"Kapsül Ø{2 * r:.1f} × L{length:.1f} mm; ρ·A·v² = {f_steady:.1f} kN; L/v = {t_ref:.3f} ms"},
        "rows": rows, **_common(job),
    }


# K13 — mayın: 6 kg TNT eşdeğeri, 500 mm, taban 1000 × 1000 × 10 S235; ölçekli ikiz W/8, R/2, a/2
MN_W, MN_R, MN_A, MN_T = 6.0, 500.0, 1000.0, 10.0


def _mine_run(label: str, w: float, r: float, a: float, t: float, free: bool) -> tuple[dict, dict]:
    body = {
        "template_id": "blast_plate_shell", "geometry": {"plate_size": a, "plate_thickness": t},
        "mine_tnt_kg": w, "mine_standoff_mm": r, "mine_exp_data": 2, "t_end_ms": 3.0 * r / MN_R,
        "element_size_mm": 25.0 * a / MN_A, "engine": {"th_dt_ms": 0.005 * r / MN_R}, "model": {"law": "plastic"},
        "th": {"part": {"vars": ["IE", "KE", "ZMOM"]}},
    }
    if free:
        body["boundary_conditions"] = [{"name": "serbest", "region": "plaka_kenar", "dofs": "000100"}]
    crash, job, _w = _run(f"V18 mayın {label}", body)
    return crash, job


def _arrival_and_momentum(job: dict) -> tuple[float, float]:
    c = job["curves"]
    zm, t = c["th_part_0_ZMOM"], c["time"]
    peak = max(abs(v) for v in zm)
    t_on = next(ti for ti, z in zip(t, zm) if abs(z) > 1e-3 * peak)
    return t_on, zm[-1]


def v18_mine() -> dict:
    c1, j1 = _mine_run(f"{MN_W:g} kg {MN_R:g} mm serbest", MN_W, MN_R, MN_A, MN_T, True)
    c2, j2 = _mine_run(f"{MN_W / 8:g} kg {MN_R / 2:g} mm serbest (ölçekli)", MN_W / 8, MN_R / 2, MN_A / 2, MN_T / 2, True)
    c3, j3 = _mine_run(f"{MN_W:g} kg {MN_R:g} mm ankastre taban", MN_W, MN_R, MN_A, MN_T, False)
    t1, i1 = _arrival_and_momentum(j1)
    t2, i2 = _arrival_and_momentum(j2)
    anim = _animation(c3["run_id"])
    disp_peak = max(max(f.get("node", {}).get("disp_mag") or [0.0]) for f in anim["frames"])
    rows = [
        {"quantity": f"İmpuls oranı (#{c1['run_id']} / #{c2['run_id']})", "sim": i1 / i2 if i2 else None, "ref": 8.0,
         "ref_label": "Hopkinson–Cranz: toplam impuls ∝ W (geometrik benzerlik)", "ratio": ratio(i1 / i2, 8.0) if i2 else None},
        {"quantity": "Varış süresi oranı", "sim": t1 / t2 if t2 else None, "ref": 2.0,
         "ref_label": "t ∝ W^(1/3)", "ratio": ratio(t1 / t2, 2.0) if t2 else None},
        {"quantity": f"Serbest plaka impulsu {MN_W:g} kg (N·s)", "sim": i1, "ref": None,
         "ref_label": "— (veri; PBLAST TM5-1300 zemin yansımalı)", "ratio": None},
        {"quantity": f"Ankastre taban en büyük çökme (mm) (#{c3['run_id']})", "sim": disp_peak, "ref": None,
         "ref_label": "— (veri)", "ratio": None},
        {"quantity": "Ankastre taban iç enerjisi son (J)", "sim": j3["scalars"].get("internal_energy_final"), "ref": None,
         "ref_label": "— (veri)", "ratio": None},
    ]
    print(f"  V18: I {i1:.0f}/{i2:.0f} = {i1 / i2:.3f}, t {t1:.4f}/{t2:.4f} = {t1 / t2:.3f}, çökme {disp_peak:.1f} mm", flush=True)
    return {
        "id": "V18", "title": f"Mayın / araç altı patlama (/LOAD/PBLAST zemin yansımalı; {MN_W:g} kg TNT, {MN_R:g} mm, taban {MN_A:g}²×{MN_T:g} S235)",
        "run_id": c3["run_id"], "wall_s": None,
        "references": {"formula": "Hopkinson–Cranz: Z = R/W^(1/3) aynı → p aynı, i ve t ∝ W^(1/3); toplam I ∝ W"},
        "rows": rows, **_common(j3),
    }


CASES = {"V1": v1_elastic, "V2": v2_plastic, "V4": v4_plate_ball_elastic, "V5": v5_recht_ipson,
         "V6": v6_taylor, "V7": v7_drop, "V8": v8_pole, "V9": v9_rops, "V10": v10_head, "V11": v11_fops,
         "V12": v12_s_rail, "V13": v13_door, "V14": v14_hopkinson, "V15": v15_blast, "V16": v16_bucket, "V17": v17_bird, "V18": v18_mine}


def _only_arg() -> str | None:
    for i, a in enumerate(sys.argv):
        if a.startswith("--only="):
            return a.split("=", 1)[1]
        if a == "--only" and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return None


def main() -> None:
    quick = "--quick" in sys.argv
    sizes = [5.0, 4.0] if quick else [5.0, 4.0, 3.0, 2.5]
    started = datetime.now(timezone.utc).isoformat()
    only = _only_arg()
    if only:
        path = OUT / "crash_validation.json"
        report = json.loads(path.read_text(encoding="utf-8"))
        by_id = {c["id"]: c for c in report["cases"]}
        for cid in [x.strip().upper() for x in only.split(",") if x.strip()]:
            print(f"{cid}…", flush=True)
            by_id[cid] = v3_sled(sizes) if cid == "V3" else CASES[cid]()
        report["cases"] = [by_id[k] for k in sorted(by_id, key=lambda i: int(i[1:]))]
        report["updated_at"] = started
        path.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
        print("yazıldı:", path)
        return
    print("V1…", flush=True)
    cases = [v1_elastic()]
    print("V2…", flush=True)
    cases.append(v2_plastic())
    print("V3…", flush=True)
    cases.append(v3_sled(sizes))
    print("V4…", flush=True)
    cases.append(v4_plate_ball_elastic())
    print("V5…", flush=True)
    cases.append(v5_recht_ipson())
    print("V6…", flush=True)
    cases.append(v6_taylor())
    print("V7…", flush=True)
    cases.append(v7_drop())
    print("V8…", flush=True)
    cases.append(v8_pole())
    print("V9…", flush=True)
    cases.append(v9_rops())
    print("V10…", flush=True)
    cases.append(v10_head())
    print("V11…", flush=True)
    cases.append(v11_fops())
    print("V12…", flush=True)
    cases.append(v12_s_rail())
    print("V13…", flush=True)
    cases.append(v13_door())
    print("V14…", flush=True)
    cases.append(v14_hopkinson())
    print("V15…", flush=True)
    cases.append(v15_blast())
    print("V16…", flush=True)
    cases.append(v16_bucket())
    print("V17…", flush=True)
    cases.append(v17_bird())
    print("V18…", flush=True)
    cases.append(v18_mine())
    report = {
        "generated_at": started,
        "setup": {"template": "crash_box_shell", "L_mm": L, "h_mm": H, "b_mm": B, "t_mm": T,
                  "material": "S235 (ρ 7850, E 210 GPa, ν 0.3, σy 235 MPa)", "v0_m_s": V0,
                  "area_mm2": AREA, "note": "Kabul kriteri yok — oranlar veri; eşik mühendisin."},
        "cases": cases,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "crash_validation.json").write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    print("yazıldı:", OUT / "crash_validation.json")


if __name__ == "__main__":
    main()
