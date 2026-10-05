"""Plaka–küre hız taraması (1.18d) — çalışan backend'e (localhost:8000)
`plate_ball_shell` senaryoları gönderir, her hız için veri tablosu yazar:
`docs/validation/plate_ball_sweep.json` (+ `.md`).

Hüküm yok: delinme eşiği / kabul mühendisin. Tablo: KE₀, küre kütlesi
(2·KE₀/v0²), temas tepe kuvveti ve impulsu, silinen eleman, plaka IE, küre
son hızı (impulstan işaretli, enerjiden işaretsiz kontrol), enerji dengesi,
hourglass / IE.

Varsayılanlar TEST değerleri (2026-10-04, mühendis değer vermeden "devam"
dedi): S235 LAW2, plaka 300 × 300 × 2, /FAIL/TENSSTRAIN ε_t1 0.15 ε_t2 0.25,
küre D50 + 1 kg, 5 mm, 2 ms. Hepsi argümanla değişir.

Kullanım (backend kökünden, sunucu açıkken):
    .\\.venv\\Scripts\\python.exe scripts/plate_ball_sweep.py --speeds 25 50 100
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.postprocess.plate_ball import (  # noqa: E402
    ball_mass_kg,
    residual_speed_energy,
    residual_velocity_impulse,
)

API = "http://localhost:8000"
OUT = ROOT.parent / "docs" / "validation"


def _args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--speeds", type=float, nargs="+", default=[25, 50, 100, 150, 200], help="m/s")
    p.add_argument("--material", default="S235")
    p.add_argument("--plate-size", type=float, default=300.0)
    p.add_argument("--plate-t", type=float, default=2.0)
    p.add_argument("--ball-d", type=float, default=50.0)
    p.add_argument("--gap", type=float, default=1.0)
    p.add_argument("--ball-mass", type=float, default=1.0, help="ek kütle (kg), kabuk kütlesine ek")
    p.add_argument("--ball-t", type=float, default=1.0)
    p.add_argument("--elem", type=float, default=5.0)
    p.add_argument("--t-end", type=float, default=2.0, help="ms")
    p.add_argument("--eps-t1", type=float, default=0.15, help="TENSSTRAIN ε_t1 (0 = kart yok)")
    p.add_argument("--eps-t2", type=float, default=0.25, help="TENSSTRAIN ε_t2")
    p.add_argument("--tag", default="plate_ball_sweep", help="çıktı dosya adı")
    return p.parse_args()


def _post(body: dict) -> dict:
    req = urllib.request.Request(
        f"{API}/crash/scenario", data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=7200) as r:
        return json.loads(r.read().decode("utf-8"))


def _model(a: argparse.Namespace) -> dict:
    model: dict = {"law": "plastic"}
    if a.eps_t1 > 0 or a.eps_t2 > 0:
        model["fail"] = {"tensstrain": {"eps_t1": a.eps_t1, "eps_t2": a.eps_t2}}
    return model


def run_case(a: argparse.Namespace, v0: float) -> dict:
    t0 = time.time()
    res = _post({
        "template_id": "plate_ball_shell",
        "name": f"1.18d v{v0:g} t{a.plate_t:g} D{a.ball_d:g} +{a.ball_mass:g}kg",
        "geometry": {"plate_size": a.plate_size, "plate_thickness": a.plate_t,
                     "ball_diameter": a.ball_d, "gap": a.gap},
        "material_name": a.material,
        "element_size_mm": a.elem,
        "speed_m_s": v0,
        "t_end_ms": a.t_end,
        "ball_mass_kg": a.ball_mass,
        "ball_thickness_mm": a.ball_t,
        "model": _model(a),
        "wait": True,
    })
    crash = res["crash"]
    row: dict = {"v0_m_s": v0, "run_id": crash.get("run_id"), "job_id": crash.get("job_id"),
                 "status": crash.get("status"), "wall_s": round(time.time() - t0, 1)}
    if crash.get("status") != "solved":
        row["message"] = crash.get("message")
        return row
    job = json.loads((ROOT / "uploads" / "crash" / crash["job_id"] / "job.json").read_text(encoding="utf-8"))
    s, c = job["scalars"], job.get("curves") or {}
    ke0 = float(s["kinetic_energy_max"])
    m = ball_mass_kg(ke0, v0)
    impulse = float(s.get("contact_1_impulse_final") or 0.0)
    plate_ke = float((c.get("th_part_0_KE") or [0.0])[-1])
    row.update({
        "ke0_j": ke0,
        "ball_mass_kg": m,
        "contact_force_max_kn": s.get("contact_1_force_max"),
        "contact_impulse_ns": impulse,
        "elements_deleted": s.get("elements_deleted"),
        "plate_ie_final_j": float((c.get("th_part_0_IE") or [s.get("internal_energy_final")])[-1]),
        "v_res_impulse_m_s": residual_velocity_impulse(v0, impulse, m),
        "v_res_energy_m_s": residual_speed_energy(float(s["kinetic_energy_final"]), plate_ke, m),
        "energy_balance_rel": s.get("energy_balance_rel"),
        "hourglass_ratio": s.get("hourglass_ratio"),
    })
    return row


def _md(report: dict) -> str:
    st = report["setup"]
    lines = [
        "# Plaka–küre hız taraması (1.18d)",
        "",
        f"Üretildi: {report['generated']} · `scripts/plate_ball_sweep.py`. "
        "Hüküm yok — delinme eşiği / kabul mühendisin.",
        "",
        f"Kurulum ({'TEST değerleri' if st['test_values'] else 'mühendis değerleri'}): {st['material']} LAW2, "
        f"plaka {st['plate_size']:g} × {st['plate_size']:g} × {st['plate_t']:g} mm, "
        f"/FAIL/TENSSTRAIN ε_t1 {st['eps_t1']:g} ε_t2 {st['eps_t2']:g}, küre D{st['ball_d']:g} "
        f"(kabuk {st['ball_t']:g} mm) + {st['ball_mass']:g} kg, g {st['gap']:g} mm, eleman {st['elem']:g} mm, "
        f"{st['t_end']:g} ms. Plaka kenarı /BCS 111111, küre rijit gövde, TYPE7.",
        "",
        "Son hız +z yukarı: impulstan v = −v0 + I/m (negatif = hâlâ −z: geçti ya da temas sürüyor; "
        "pozitif = geri sekti), enerjiden |v| (kontrol).",
        "",
        "| v0 m/s | koşu | KE₀ J | m kg | F tepe kN | I N·s | silinen | plaka IE J | v son (I) m/s | ‖v son‖ (E) m/s | denge | HG/IE |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]

    def f(v, fmt="{:.3g}"):
        return "—" if v is None else fmt.format(v)

    for r in report["rows"]:
        if r.get("status") != "solved":
            lines.append(f"| {r['v0_m_s']:g} | #{r.get('run_id')} | {r.get('status')} {r.get('message') or ''} |||||||||||")
            continue
        lines.append(
            f"| {r['v0_m_s']:g} | #{r['run_id']} | {f(r['ke0_j'], '{:.1f}')} | {f(r['ball_mass_kg'], '{:.4f}')} | "
            f"{f(r['contact_force_max_kn'], '{:.1f}')} | {f(r['contact_impulse_ns'], '{:.2f}')} | "
            f"{f(r['elements_deleted'], '{:.0f}')} | {f(r['plate_ie_final_j'], '{:.1f}')} | "
            f"{f(r['v_res_impulse_m_s'], '{:+.2f}')} | {f(r['v_res_energy_m_s'], '{:.2f}')} | "
            f"{f(r['energy_balance_rel'], '{:.2e}')} | {f(r['hourglass_ratio'], '{:.3f}')} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    a = _args()
    defaults = (a.material, a.plate_t, a.eps_t1, a.eps_t2, a.ball_d, a.ball_mass) == ("S235", 2.0, 0.15, 0.25, 50.0, 1.0)
    rows = []
    for v0 in a.speeds:
        print(f"v0 = {v0:g} m/s …", flush=True)
        row = run_case(a, v0)
        print(json.dumps(row, ensure_ascii=False), flush=True)
        rows.append(row)
    report = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "setup": {
            "material": a.material, "plate_size": a.plate_size, "plate_t": a.plate_t, "ball_d": a.ball_d,
            "gap": a.gap, "ball_mass": a.ball_mass, "ball_t": a.ball_t, "elem": a.elem, "t_end": a.t_end,
            "eps_t1": a.eps_t1, "eps_t2": a.eps_t2, "test_values": defaults,
        },
        "rows": rows,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{a.tag}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / f"{a.tag}.md").write_text(_md(report), encoding="utf-8")
    print(f"yazıldı: {OUT / (a.tag + '.md')}")


if __name__ == "__main__":
    main()
