"""Analiz sonucu PDF rapor üretimi (reportlab).

Bir AnalysisRun'ın özet raporu: proje/case bilgisi, malzeme, BC listesi,
sonuç skalerleri (max von Mises, deplasman, safety factor, fatigue life).
Ham veri/mesh dahil değil (o zaten .inp/.frd/.json dosyalarından indirilebilir)
— bu rapor mühendisin paylaşabileceği, okunabilir bir özet.
"""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def _fmt_num(v: Any, unit: str = "") -> str:
    if v is None:
        return "—"
    try:
        fv = float(v)
    except (TypeError, ValueError):
        return str(v)
    if abs(fv) >= 1000 or (0 < abs(fv) < 0.01):
        return f"{fv:.3e}{(' ' + unit) if unit else ''}"
    return f"{fv:.3f}{(' ' + unit) if unit else ''}"


def build_run_report_pdf(
    *,
    run_id: int,
    run_name: str | None,
    geometry_filename: str | None,
    created_at: datetime,
    dimension: int,
    status: str,
    message: str | None,
    bcs: list[dict[str, Any]],
    materials_snapshot: list[dict[str, Any]],
    scalars: dict[str, float],
    fatigue_note: str | None = None,
) -> bytes:
    """Verilen run bilgilerinden bir PDF rapor üretir, byte olarak döner."""
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle", parent=styles["Heading1"], fontSize=18, spaceAfter=4
    )
    sub_style = ParagraphStyle(
        "ReportSub", parent=styles["Normal"], textColor=colors.grey, fontSize=10
    )
    section_style = ParagraphStyle(
        "ReportSection", parent=styles["Heading2"], fontSize=13, spaceBefore=14, spaceAfter=6
    )

    story: list[Any] = []
    story.append(Paragraph(f"CAE Analiz Raporu — {run_name or f'Run #{run_id}'}", title_style))
    story.append(
        Paragraph(
            f"Geometri: {geometry_filename or '—'} · "
            f"{'3D solid' if dimension == 3 else '2D shell'} · "
            f"{created_at.strftime('%d.%m.%Y %H:%M')} · Run #{run_id} · Durum: {status}",
            sub_style,
        )
    )
    if message:
        story.append(Paragraph(message, sub_style))
    story.append(Spacer(1, 8 * mm))

    # --- Malzeme ---
    story.append(Paragraph("Malzeme", section_style))
    if materials_snapshot:
        mat_rows = [["Parça", "Malzeme", "E (Pa)", "ν", "ρ (kg/m³)"]]
        for m in materials_snapshot:
            mat_rows.append(
                [
                    str(m.get("part_id", "—")),
                    str(m.get("name", "—")),
                    _fmt_num(m.get("youngs_modulus")),
                    _fmt_num(m.get("poisson_ratio")),
                    _fmt_num(m.get("density")),
                ]
            )
        mat_table = Table(mat_rows, hAlign="LEFT")
        mat_table.setStyle(_default_table_style())
        story.append(mat_table)
    else:
        story.append(Paragraph("Malzeme ataması bulunamadı.", styles["Normal"]))

    # --- BC listesi ---
    story.append(Paragraph("Sınır Koşulları (BC)", section_style))
    if bcs:
        bc_rows = [["#", "Tip", "Detay"]]
        for i, bc in enumerate(bcs, start=1):
            bc_type = str(bc.get("type", "—"))
            detail_parts = [
                f"{k}={v}"
                for k, v in bc.items()
                if k != "type" and v is not None and v != []
            ]
            bc_rows.append([str(i), bc_type, ", ".join(detail_parts) or "—"])
        bc_table = Table(bc_rows, hAlign="LEFT", colWidths=[10 * mm, 30 * mm, 120 * mm])
        bc_table.setStyle(_default_table_style())
        story.append(bc_table)
    else:
        story.append(Paragraph("BC bulunamadı.", styles["Normal"]))

    # --- Sonuçlar ---
    story.append(Paragraph("Sonuçlar", section_style))
    result_rows = [
        ["Max von Mises", _fmt_num(scalars.get("max_von_mises"), "MPa")],
        ["Max deplasman", _fmt_num(scalars.get("max_displacement"), "mm")],
        ["Kritik node", _fmt_num(scalars.get("critical_node_id"))],
        ["Safety factor (statik)", _fmt_num(scalars.get("safety_factor"))],
        ["Yorulma ömrü (cycle)", _fmt_num(scalars.get("fatigue_life_cycles"))],
    ]
    result_table = Table(result_rows, hAlign="LEFT", colWidths=[60 * mm, 100 * mm])
    result_table.setStyle(_default_table_style())
    story.append(result_table)
    if fatigue_note:
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph(f"Not (yorulma): {fatigue_note}", sub_style))

    story.append(Spacer(1, 10 * mm))
    story.append(
        Paragraph(
            "Bu rapor otomatik üretilmiştir. Yorulma ömrü ve S-N eğrisi değerleri "
            "(aksi belirtilmedikçe) ampirik tahminlerdir, gerçek yorulma testinin "
            "yerini tutmaz.",
            sub_style,
        )
    )

    doc.build(story)
    return buf.getvalue()


def _default_table_style() -> TableStyle:
    return TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef0ec")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d9ddd6")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
    )
