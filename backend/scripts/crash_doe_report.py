"""Crash DOE raporu — tek crash DOE çalışmasından (ör. crash box 150 koşu)
paylaşılabilir özet: vekil model K-fold CV (tahmin vs FEA), FEA ortalama
ezilme kuvveti vs Wierzbicki–Abramowicz (1983), CV metrik tablosu.

Çıktı (`--out`, varsayılan `uploads/reports/crash_doe_<id>/`):
  report.json — satır verisi + metrikler
  report.html — bağımlılıksız (satır içi SVG) sayfa; tarayıcıda açılıp
                ekran görüntüsü alınabilir.

Kabul kriteri yok — oranlar ve skorlar veri. Kullanım:
  python -m scripts.crash_doe_report --study 3
"""

from __future__ import annotations

import argparse
import html
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import KFold, cross_val_predict

from app.db.session import SessionLocal
from app.ml.crash.corpus import load_crash_corpus
from app.ml.crash.surrogate import _cv_metrics
from app.models.crash_doe import CrashDoeStudy
from app.models.material import Material
from app.postprocess.crash_validation import tube_mean_crush_force_kn

#: Hedef → (etiket, birim)
TARGET_LABELS = {
    "mean_force_kn": ("Ortalama ezilme kuvveti", "kN"),
    "crush_mm": ("Ezilme mesafesi", "mm"),
    "peak_force_kn": ("Tepe kuvvet", "kN"),
    "energy_absorbed_j": ("Yutulan enerji", "J"),
}
#: Özellik → okunur ad
FEATURE_LABELS = {
    "req.barrier.speed_m_s": "hız v (m/s)",
    "geom.wall": "et kalınlığı t (mm)",
    "geom.box_width": "genişlik b (mm)",
    "req.rigid_bodies.0.mass_kg": "kızak kütlesi (kg)",
}


#: DOE yolu → okunur ad (rapor "taranan girdiler")
VARY_LABELS = {
    "speed_m_s": "hız v (m/s)",
    "geometry.wall": "et kalınlığı t (mm)",
    "geometry.box_width": "genişlik b (mm)",
    "rigid_bodies.0.mass_kg": "kızak kütlesi (kg)",
}


def _feature_col(names: list[str], key: str) -> int | None:
    return names.index(key) if key in names else None


def build_report(study_id: int, seed: int = 2026, folds: int = 5) -> dict[str, Any]:
    with SessionLocal() as db:
        study = db.get(CrashDoeStudy, study_id)
        if study is None:
            raise SystemExit(f"Crash DOE çalışması yok: {study_id}")
        base = study.spec.get("base", {}) if isinstance(study.spec, dict) else {}
        corpus = load_crash_corpus(db, study.template_id, "rigid_wall", study_id=study_id)
        mat_name = base.get("material_name", "S235")
        mat = db.query(Material).filter(Material.name == mat_name).first()
        sigma0 = (mat.yield_strength / 1e6) if mat else float("nan")
        rho = mat.density if mat else float("nan")

    names = corpus.feature_names
    X = corpus.X
    # Yalnız DOE'de taranan dört girdi (istek içindeki geometri kopyaları vb. değil)
    keys = [k for k in FEATURE_LABELS if k in names]
    Xs = X[:, [names.index(k) for k in keys]]
    const = corpus.constant_features
    height = float(const.get("geom.box_height", base.get("geometry", {}).get("box_height", 50.0)))
    length = float(const.get("geom.box_length", base.get("geometry", {}).get("box_length", 300.0)))

    rows: list[dict[str, Any]] = []
    for i, rid in enumerate(corpus.run_ids):
        r = {"run_id": rid, **{k: float(Xs[i, j]) for j, k in enumerate(keys)}}
        for t_i, tk in enumerate(corpus.target_names):
            v = corpus.Y[i, t_i]
            r[tk] = float(v) if math.isfinite(v) else None
        t = r.get("geom.wall")
        b = r.get("geom.box_width")
        if t and b:
            c = ((height - t) + (b - t)) / 2.0  # orta yüzey kenar ortalaması
            r["pm_wa_kn"] = tube_mean_crush_force_kn(sigma0, t, c)["wierzbicki_abramowicz_1983"]
            box_kg = rho * 2.0 * ((height - t) + (b - t)) * t * length * 1e-9
            r["box_mass_kg"] = box_kg
            e = r.get("energy_absorbed_j")
            r["sea_j_per_g"] = e / (box_kg * 1e3) if e is not None and box_kg > 0 else None
        rows.append(r)

    # Vekil model: hedef başına RF, K-fold CV tahmini (her nokta, onu görmeyen modelden)
    cv: dict[str, Any] = {}
    for t_i, tk in enumerate(corpus.target_names):
        y = corpus.Y[:, t_i]
        ok = np.isfinite(y)
        n = int(ok.sum())
        if n < 10:
            cv[tk] = {"n": n, "skipped": "az satır"}
            continue
        rf = RandomForestRegressor(n_estimators=300, random_state=seed)
        kf = KFold(n_splits=min(folds, n), shuffle=True, random_state=seed)
        pred = cross_val_predict(rf, Xs[ok], y[ok], cv=kf)
        cv[tk] = {**_cv_metrics(y[ok], pred), "folds": kf.n_splits}
        idx = np.flatnonzero(ok)
        for j, p in zip(idx, pred):
            rows[j][f"cv_pred_{tk}"] = float(p)
        imp = rf.fit(Xs[ok], y[ok]).feature_importances_
        cv[tk]["importance"] = {k: float(v) for k, v in zip(keys, imp)}

    ratios = [r["mean_force_kn"] / r["pm_wa_kn"] for r in rows if r.get("mean_force_kn") and r.get("pm_wa_kn")]
    return {
        "study_id": study_id,
        "study_name": study.name,
        "template_id": corpus.template_id,
        "n_runs": len(rows),
        "dropped": corpus.dropped,
        "material": {"name": mat_name, "sigma0_mpa": sigma0, "density": rho},
        "fixed": {"box_length_mm": length, "box_height_mm": height, **{k: v for k, v in base.items() if k in ("t_end_ms", "element_size_mm")}},
        "vary": study.spec.get("vary") if isinstance(study.spec, dict) else None,
        "features": keys,
        "cv": cv,
        "theory_ratio": {
            "n": len(ratios),
            "mean": float(np.mean(ratios)) if ratios else None,
            "min": float(np.min(ratios)) if ratios else None,
            "max": float(np.max(ratios)) if ratios else None,
        },
        "rows": rows,
    }


# --- SVG ------------------------------------------------------------------------

def _scatter_svg(xs: list[float], ys: list[float], *, xlabel: str, ylabel: str, title: str,
                 color: str = "#2563eb", diag: bool = True, w: int = 460, h: int = 400) -> str:
    pad_l, pad_b, pad_t, pad_r = 62, 52, 36, 16
    lo = min(min(xs), min(ys)) if diag else min(xs)
    hi = max(max(xs), max(ys)) if diag else max(xs)
    ylo = lo if diag else min(ys)
    yhi = hi if diag else max(ys)
    span, yspan = (hi - lo) or 1.0, (yhi - ylo) or 1.0
    lo, hi = lo - 0.05 * span, hi + 0.05 * span
    ylo, yhi = ylo - 0.05 * yspan, yhi + 0.05 * yspan

    def px(v: float) -> float:
        return pad_l + (v - lo) / (hi - lo) * (w - pad_l - pad_r)

    def py(v: float) -> float:
        return h - pad_b - (v - ylo) / (yhi - ylo) * (h - pad_b - pad_t)

    out = [f'<svg viewBox="0 0 {w} {h}" class="plot" role="img" aria-label="{html.escape(title)}">',
           f'<text x="{w / 2}" y="20" class="pt">{html.escape(title)}</text>']
    for k in range(6):
        gx = lo + (hi - lo) * k / 5
        gy = ylo + (yhi - ylo) * k / 5
        out.append(f'<line x1="{px(gx):.1f}" y1="{pad_t}" x2="{px(gx):.1f}" y2="{h - pad_b}" class="grid"/>')
        out.append(f'<line x1="{pad_l}" y1="{py(gy):.1f}" x2="{w - pad_r}" y2="{py(gy):.1f}" class="grid"/>')
        out.append(f'<text x="{px(gx):.1f}" y="{h - pad_b + 16}" class="tick" text-anchor="middle">{gx:.3g}</text>')
        out.append(f'<text x="{pad_l - 6}" y="{py(gy) + 4:.1f}" class="tick" text-anchor="end">{gy:.3g}</text>')
    if diag:
        out.append(f'<line x1="{px(lo):.1f}" y1="{py(lo):.1f}" x2="{px(hi):.1f}" y2="{py(hi):.1f}" class="diag"/>')
    for x, y in zip(xs, ys):
        out.append(f'<circle cx="{px(x):.1f}" cy="{py(y):.1f}" r="3.6" fill="{color}" fill-opacity="0.65"/>')
    out.append(f'<text x="{(pad_l + w - pad_r) / 2}" y="{h - 12}" class="al" text-anchor="middle">{html.escape(xlabel)}</text>')
    out.append(f'<text x="16" y="{(pad_t + h - pad_b) / 2}" class="al" text-anchor="middle" '
               f'transform="rotate(-90 16 {(pad_t + h - pad_b) / 2})">{html.escape(ylabel)}</text>')
    out.append("</svg>")
    return "".join(out)


def render_html(rep: dict[str, Any]) -> str:
    rows = rep["rows"]
    cards = []
    for tk in ("mean_force_kn", "crush_mm", "peak_force_kn"):
        m = rep["cv"].get(tk, {})
        pts = [(r[tk], r[f"cv_pred_{tk}"]) for r in rows if r.get(tk) is not None and r.get(f"cv_pred_{tk}") is not None]
        if not pts:
            continue
        lab, unit = TARGET_LABELS[tk]
        svg = _scatter_svg([p[0] for p in pts], [p[1] for p in pts], xlabel=f"FEA (OpenRadioss) [{unit}]",
                           ylabel=f"Vekil model tahmini [{unit}]", title=lab)
        cards.append(f'<figure>{svg}<figcaption>R² {m.get("r2", float("nan")):.3f} · MAE {m.get("mae", float("nan")):.3g} {unit} '
                     f'· {m.get("folds")}-katlı CV · n {m.get("n")}</figcaption></figure>')
    th = [(r["pm_wa_kn"], r["mean_force_kn"]) for r in rows if r.get("pm_wa_kn") and r.get("mean_force_kn")]
    if th:
        tr = rep["theory_ratio"]
        svg = _scatter_svg([p[0] for p in th], [p[1] for p in th], xlabel="Wierzbicki–Abramowicz (1983) [kN]",
                           ylabel="FEA ortalama kuvvet [kN]", title="FEA ↔ teori", color="#b45309")
        cards.append(f'<figure>{svg}<figcaption>FEA / teori ortalama {tr["mean"]:.2f} (min {tr["min"]:.2f}, '
                     f'max {tr["max"]:.2f}) · σ₀ = {rep["material"]["sigma0_mpa"]:.0f} MPa</figcaption></figure>')
        rc = [(r["crush_mm"], r["mean_force_kn"] / r["pm_wa_kn"]) for r in rows
              if r.get("crush_mm") and r.get("mean_force_kn") and r.get("pm_wa_kn")]
        if rc:
            svg = _scatter_svg([p[0] for p in rc], [p[1] for p in rc], xlabel="Ezilme mesafesi [mm]",
                               ylabel="FEA / teori", title="Teori oranı ↔ ezilme", color="#7c3aed", diag=False)
            cards.append(f"<figure>{svg}<figcaption>Kısa ezilmede ilk katlanma tepesi ortalamayı yükseltir; "
                         f"teori kararlı katlanma platosunu tanımlar.</figcaption></figure>")

    trs = []
    for tk, (lab, unit) in TARGET_LABELS.items():
        m = rep["cv"].get(tk)
        if not m or "r2" not in m:
            continue
        imp = m.get("importance", {})
        top = max(imp, key=imp.get) if imp else ""
        trs.append(f"<tr><td>{lab}</td><td>{m['r2']:.3f}</td><td>{m['mae']:.3g} {unit}</td>"
                   f"<td>{m.get('mape', float('nan')) * 100:.1f} %</td><td>{FEATURE_LABELS.get(top, top)}</td></tr>")
    vary = rep.get("vary") or {}
    vrows = "".join(
        f"<li>{VARY_LABELS.get(k, k)}: "
        f"{lohi[0]:g} – {lohi[1]:g}</li>" for k, lohi in vary.items()
    )
    return f"""<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Crash Box Surrogate</title>
<style>
:root{{--bg:#f7f8f6;--fg:#14181a;--mut:#5b6560;--card:#fff;--line:#d9ded9}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}}
main{{max-width:1040px;margin:0 auto;padding:28px 16px}}
h1{{font-size:24px;margin:0 0 4px}} .sub{{color:var(--mut);margin:0 0 20px}}
.grid2{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px}}
figure{{margin:0;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px}}
figcaption{{color:var(--mut);font-size:13px;text-align:center}}
.plot{{width:100%;height:auto}} .pt{{font:600 14px system-ui;text-anchor:middle;fill:var(--fg)}}
.tick{{font:11px system-ui;fill:var(--mut)}} .al{{font:12px system-ui;fill:var(--fg)}}
.grid{{stroke:#e6e9e6}} .diag{{stroke:#9aa39d;stroke-dasharray:5 4}}
table{{border-collapse:collapse;width:100%;background:var(--card);border:1px solid var(--line);border-radius:10px;margin-top:16px}}
td,th{{padding:8px 10px;border-bottom:1px solid var(--line);text-align:left}} th{{font-size:13px;color:var(--mut)}}
.meta{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px;margin-top:16px}}
.meta div{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px}}
</style></head><body><main>
<h1>Crash box eksenel ezilme — vekil model (surrogate)</h1>
<p class="sub">{rep['n_runs']} OpenRadioss koşusu (LHS DOE) · kabuk crash box + raylı kızak, rijit duvar ·
{html.escape(rep['material']['name'])} · L {rep['fixed']['box_length_mm']:g} mm, h {rep['fixed']['box_height_mm']:g} mm</p>
<div class="grid2">{''.join(cards)}</div>
<table><tr><th>Hedef</th><th>R² (CV)</th><th>MAE</th><th>MAPE</th><th>En etkili girdi</th></tr>{''.join(trs)}</table>
<div class="meta"><div><b>Taranan girdiler</b><ul>{vrows}</ul></div>
<div><b>Yöntem</b><ul><li>Random Forest, hedef başına ayrı model</li>
<li>{rep['cv'].get('mean_force_kn', {}).get('folds', 5)}-katlı çapraz doğrulama — her nokta onu görmeyen modelden</li>
<li>Çözücü: OpenRadioss (açık kaynak), mesh: Gmsh</li></ul></div></div>
</main></body></html>"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--study", type=int, required=True)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    rep = build_report(args.study)
    out = args.out or Path("uploads") / "reports" / f"crash_doe_{args.study}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "report.html").write_text(render_html(rep), encoding="utf-8")
    print(f"{rep['n_runs']} koşu · rapor: {out / 'report.html'}")
    for tk, m in rep["cv"].items():
        if "r2" in m:
            print(f"  {tk}: R² {m['r2']:.3f} · MAE {m['mae']:.3g} · n {m['n']}")
    print(f"  FEA/teori: {rep['theory_ratio']}")


if __name__ == "__main__":
    main()
