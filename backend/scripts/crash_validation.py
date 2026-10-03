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

Kullanım (backend kökünden, sunucu açıkken):
    .\\.venv\\Scripts\\python.exe scripts/crash_validation.py [--quick]
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
    contact_duration_ms,
    contact_window,
    elastic_impact_force_kn,
    plateau_kn,
    ratio,
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


def _run(name: str, body: dict) -> tuple[dict, dict, float]:
    t0 = time.time()
    res = _post({"name": f"1.17f {name}", "wait": True, **body})
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


def main() -> None:
    quick = "--quick" in sys.argv
    sizes = [5.0, 4.0] if quick else [5.0, 4.0, 3.0, 2.5]
    started = datetime.now(timezone.utc).isoformat()
    print("V1…", flush=True)
    cases = [v1_elastic()]
    print("V2…", flush=True)
    cases.append(v2_plastic())
    print("V3…", flush=True)
    cases.append(v3_sled(sizes))
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
