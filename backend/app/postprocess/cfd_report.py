"""CFD koşusu PDF raporu (reportlab) — Faz 2 belgeleme adımı.

Bir ``cfd_runs`` kaydı + ``job.json``: koşu bilgisi, çözücü / türbülans /
mesh, yamalar, kuvvet katsayıları (ortalama ± std), yama başına kuvvet, roket
koşusunda katsayılar + basınç merkezi + Barrowman yan yana, residual geçmişi
(log10) ve Cd geçmişi grafiği. Yalnız veri; yorum / öneri yok.

Türkçe karakterler için sistemde bulunan bir TTF (DejaVuSans / Arial)
kaydedilir; bulunamazsa Helvetica.
"""

from __future__ import annotations

import math
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

_FONT_CANDIDATES = [
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
]
_PALETTE = ["#1f77b4", "#d62728", "#2ca02c", "#ff7f0e", "#9467bd", "#8c564b", "#17becf"]


def _fonts() -> tuple[str, str]:
    for reg, bold in _FONT_CANDIDATES:
        if Path(reg).is_file() and Path(bold).is_file():
            try:
                if "CfdSans" not in pdfmetrics.getRegisteredFontNames():
                    pdfmetrics.registerFont(TTFont("CfdSans", reg))
                    pdfmetrics.registerFont(TTFont("CfdSans-Bold", bold))
                return "CfdSans", "CfdSans-Bold"
            except Exception:  # noqa: BLE001 — bozuk font dosyası
                continue
    return "Helvetica", "Helvetica-Bold"


def _f(v: Any, d: int = 4) -> str:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        return "—"
    return f"{v:.{d}g}"


def _table(rows: list[list[str]], font: str, bold: str, widths: list[float] | None = None) -> Table:
    t = Table(rows, hAlign="LEFT", colWidths=widths)
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font),
        ("FONTNAME", (0, 0), (-1, 0), bold),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef0ec")),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d9ddd6")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def _chart(title: str, x: list[float], series: dict[str, list[float]], font: str, *, log: bool) -> Drawing | None:
    data, names = [], []
    for name, ys in series.items():
        pts = []
        for xi, yi in zip(x, ys):
            if isinstance(yi, (int, float)) and math.isfinite(yi) and (yi > 0 or not log):
                pts.append((xi, math.log10(yi) if log else yi))
        if len(pts) > 1:
            step = max(1, len(pts) // 400)
            data.append(pts[::step])
            names.append(name)
    if not data:
        return None
    d = Drawing(170 * mm, 70 * mm)
    lp = LinePlot()
    lp.x, lp.y, lp.width, lp.height = 14 * mm, 10 * mm, 120 * mm, 52 * mm
    lp.data = data
    for i in range(len(data)):
        lp.lines[i].strokeColor = colors.HexColor(_PALETTE[i % len(_PALETTE)])
        lp.lines[i].strokeWidth = 0.8
    lp.xValueAxis.labels.fontName = font
    lp.yValueAxis.labels.fontName = font
    lp.xValueAxis.labels.fontSize = lp.yValueAxis.labels.fontSize = 7
    if log:
        lp.yValueAxis.labelTextFormat = lambda v: f"1e{v:.0f}"
    d.add(lp)
    d.add(String(14 * mm, 65 * mm, title, fontName=font, fontSize=9))
    for i, n in enumerate(names):
        d.add(String(138 * mm, (58 - 5 * i) * mm, f"— {n}", fontName=font, fontSize=7, fillColor=colors.HexColor(_PALETTE[i % len(_PALETTE)])))
    d.add(String(70 * mm, 2 * mm, "iterasyon", fontName=font, fontSize=7))
    return d


def build_cfd_report_pdf(run: dict[str, Any], job: dict[str, Any]) -> bytes:
    font, bold = _fonts()
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=18 * mm, leftMargin=18 * mm, rightMargin=18 * mm)
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Heading1"], fontName=bold, fontSize=17, spaceAfter=4)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontName=bold, fontSize=12, spaceBefore=12, spaceAfter=5)
    sub = ParagraphStyle("sub", parent=ss["Normal"], fontName=font, fontSize=9, textColor=colors.grey)
    body = ParagraphStyle("b", parent=ss["Normal"], fontName=font, fontSize=9)
    sc: dict[str, Any] = job.get("scalars") or run.get("scalars") or {}
    case: dict[str, Any] = job.get("case") or {}
    story: list[Any] = []

    created = run.get("created_at")
    when = created.strftime("%d.%m.%Y %H:%M") if isinstance(created, datetime) else str(created or "")
    story.append(Paragraph(f"CFD Koşu Raporu — {run.get('name') or 'Koşu #' + str(run.get('id'))}", h1))
    story.append(Paragraph(
        f"Koşu #{run.get('id')} · {when} · çözücü {job.get('application') or run.get('application') or '—'} · "
        f"türbülans {job.get('turbulence') or '—'} · durum {run.get('status')}", sub))
    if run.get("message"):
        story.append(Paragraph(str(run["message"]), sub))
    story.append(Spacer(1, 4 * mm))

    # --- kurulum
    story.append(Paragraph("Kurulum", h2))
    mesh = job.get("mesh") or {}
    rows = [["Alan", "Değer"],
            ["Mesh", f"{mesh.get('kind') or '—'} · {mesh.get('cells') or '—'} hücre"],
            ["Akışkan", f"ν = {_f(case.get('nu_m2_s'))} m²/s · ρ = {_f(job.get('rho_kg_m3'))} kg/m³"],
            ["İterasyon", f"{_f(sc.get('iterations'), 6)} / {_f(job.get('end_iterations'), 6)} · "
                          f"{'yakınsadı' if sc.get('converged') else 'iterasyon sınırı'}"]]
    ctl = case.get("control") or {}
    if ctl:
        rows.append(["Çözüm ayarları", f"gevşetme U {ctl.get('relax_u')} / diğer {ctl.get('relax_other')} · çekirdek {ctl.get('n_procs', 1)}"])
    comp = case.get("compressible") or {}
    if (job.get("application") or "").startswith("rho") and comp:
        rows.append(["Serbest akım", f"p∞ {_f(comp.get('p_inf_pa'))} Pa · T∞ {_f(comp.get('t_inf_k'))} K"])
    story.append(_table(rows, font, bold, [40 * mm, 130 * mm]))
    patches = case.get("patches") or []
    if patches:
        story.append(Spacer(1, 3 * mm))
        prow = [["Yama", "Tür", "Değer"]]
        for p in patches:
            if p.get("kind") in ("inlet", "farfield") and p.get("velocity_m_s"):
                val = "U = (" + ", ".join(_f(c) for c in p["velocity_m_s"]) + ") m/s"
            elif p.get("kind") == "outlet":
                val = f"p = {_f(p.get('pressure') or 0.0)}"
            else:
                val = "—"
            prow.append([str(p.get("name")), str(p.get("kind")), val])
        story.append(_table(prow, font, bold, [45 * mm, 35 * mm, 90 * mm]))

    # --- katsayılar
    story.append(Paragraph("Kuvvet katsayıları", h2))
    crow = [["Katsayı", "Son", "Ortalama", "Std"]]
    for k in ("Cd", "Cl", "Cs", "CmPitch"):
        if k in sc:
            crow.append([k, _f(sc.get(k)), _f(sc.get(f"{k}_mean")), _f(sc.get(f"{k}_std"))])
    if "CdA_m2" in sc:
        crow.append(["CdA (m²)", _f(sc.get("CdA_m2")), _f(sc.get("CdA_mean_m2")), "—"])
    if len(crow) > 1:
        story.append(_table(crow, font, bold, [40 * mm, 40 * mm, 40 * mm, 40 * mm]))
        story.append(Paragraph(f"Ortalama penceresi: son {_f(sc.get('coeff_average_window'), 5)} iterasyon.", sub))
    else:
        story.append(Paragraph("Bu koşuda kuvvet katsayısı istenmedi.", body))
    tags = sorted({k[6:-2] for k in sc if k.startswith("force_") and k.endswith("_x") and "_pressure" not in k and "_viscous" not in k})
    if tags:
        story.append(Spacer(1, 3 * mm))
        frow = [["Yama", "Fx (N)", "Fy (N)", "Fz (N)", "Fx basınç", "Fx viskoz"]]
        for t in tags:
            frow.append([t, *(_f(sc.get(f"force_{t}_{a}")) for a in "xyz"), _f(sc.get(f"force_{t}_pressure_x")), _f(sc.get(f"force_{t}_viscous_x"))])
        story.append(_table(frow, font, bold))

    # --- roket
    ra = job.get("rocket_aero")
    if ra:
        rk = job.get("rocket") or {}
        story.append(Paragraph("Roket aerodinamiği", h2))
        story.append(Paragraph(
            f"V = {_f(rk.get('speed_m_s'))} m/s · α = {_f(rk.get('alpha_deg'))}° · Mach {_f(rk.get('mach'), 3)} · "
            f"q = {_f(ra.get('q_pa'))} Pa · A_ref = {_f(ra.get('a_ref_m2'))} m² · moment noktası x = {_f(ra.get('x_ref_m'))} m", body))
        b = ra.get("barrowman") or {}
        rrow = [["Büyüklük", "CFD", "Barrowman", "Fark"],
                ["CA / CN", f"{_f(ra.get('CA'))} / {_f(ra.get('CN'))}", "—", "—"],
                ["CD / CL", f"{_f(ra.get('CD'))} / {_f(ra.get('CL'))}", "—", "—"],
                ["Cm", _f(ra.get("Cm")), "—", "—"],
                ["CNα (1/rad)", _f(ra.get("CN_alpha_per_rad")), _f(b.get("cn_alpha_barrowman")),
                 f"%{_f(b.get('cn_alpha_diff_percent'), 3)}" if b.get("cn_alpha_diff_percent") is not None else "—"],
                ["x_cp (mm)", _f((ra.get("x_cp_m") or math.nan) * 1000, 5), _f((b.get("x_cp_barrowman_m") or math.nan) * 1000, 5),
                 f"{_f(b.get('x_cp_diff_calibers'), 3)} kal." if b.get("x_cp_diff_calibers") is not None else "—"],
                ["Kararlılık (kalibre)", _f(ra.get("stability_calibers"), 3), "—", "—"]]
        story.append(_table(rrow, font, bold, [45 * mm, 45 * mm, 40 * mm, 40 * mm]))

    # --- referans
    ref = run.get("reference") or {}
    if ref and ref.get("kind") != "rocket_r3":
        story.append(Paragraph("Analitik referans", h2))
        story.append(_table([["Alan", "Değer"], *[[str(k), _f(v) if isinstance(v, (int, float)) else str(v)] for k, v in ref.items()]], font, bold, [60 * mm, 110 * mm]))

    # --- grafikler
    curves = job.get("curves") or {}
    its = curves.get("iteration") or []
    res = curves.get("residuals") or {}
    if its and res:
        story.append(Paragraph("Residual geçmişi", h2))
        ch = _chart("İlk residual (log10)", its, res, font, log=True)
        if ch:
            story.append(ch)
    fc = curves.get("force_coeffs") or {}
    if fc.get("iteration") and fc.get("Cd"):
        ch = _chart("Cd geçmişi", fc["iteration"], {k: fc[k] for k in ("Cd", "Cl") if k in fc}, font, log=False)
        if ch:
            story.append(ch)

    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph("Otomatik üretilmiştir (OpenFOAM, SimSurrogate). Sayılar koşunun verisidir; değerlendirme mühendisindir.", sub))
    doc.build(story)
    return buf.getvalue()
