"""
AeroScribe NRF Report Generator
================================
Generates aviation-grade Non-Routine Finding (NRF) compliance PDF reports
using a builder pattern. Features:
  - Branded header + diagonal watermark on every page
  - Running page header/footer with document ID and page numbers
  - Color-coded severity banners per IATA risk categories
  - Structured numbered procedure steps table
  - Enriched AMM fields: duration, parts, regulatory references
  - Inspector sign-off block with name, date, and signature line
"""

import os
import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfgen import canvas as pdfgen_canvas
from reportlab.platypus import PageBreak

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "reports")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── Color Palette ─────────────────────────────────────────────────────────────
C_NAVY      = colors.HexColor("#0A1628")
C_NAVY_MED  = colors.HexColor("#0F2044")
C_BLUE      = colors.HexColor("#1D4ED8")
C_BLUE_LITE = colors.HexColor("#EFF6FF")
C_SLATE     = colors.HexColor("#334155")
C_MUTED     = colors.HexColor("#64748B")
C_DIVIDER   = colors.HexColor("#CBD5E1")
C_BG_ROW    = colors.HexColor("#F8FAFC")
C_BG_ALT    = colors.HexColor("#F1F5F9")
C_WHITE     = colors.white

# Severity palette
C_SEV_1_BG  = colors.HexColor("#FEE2E2"); C_SEV_1_FG = colors.HexColor("#991B1B"); C_SEV_1_BD = colors.HexColor("#EF4444")
C_SEV_2_BG  = colors.HexColor("#FFEDD5"); C_SEV_2_FG = colors.HexColor("#9A3412"); C_SEV_2_BD = colors.HexColor("#F97316")
C_SEV_3_BG  = colors.HexColor("#FEF3C7"); C_SEV_3_FG = colors.HexColor("#92400E"); C_SEV_3_BD = colors.HexColor("#F59E0B")
C_SEV_4_BG  = colors.HexColor("#D1FAE5"); C_SEV_4_FG = colors.HexColor("#065F46"); C_SEV_4_BD = colors.HexColor("#10B981")

PAGE_W, PAGE_H = A4
L_MARGIN = R_MARGIN = 18 * mm
T_MARGIN = 22 * mm
B_MARGIN = 22 * mm
USABLE_W = PAGE_W - L_MARGIN - R_MARGIN   # ≈ 174mm / ~493pt


# ── Page Template Callbacks ───────────────────────────────────────────────────

def _make_page_callbacks(report_id: str, doc_date: str):
    """Return on_first_page and on_later_pages callbacks for SimpleDocTemplate."""

    def _draw_page(canvas, doc, is_first: bool):
        canvas.saveState()

        # Diagonal watermark
        canvas.setFont("Helvetica-Bold", 52)
        canvas.setFillColor(colors.HexColor("#E2E8F0"))
        canvas.setStrokeColor(colors.HexColor("#E2E8F0"))
        canvas.translate(PAGE_W / 2, PAGE_H / 2)
        canvas.rotate(40)
        canvas.setFillAlpha(0.07)
        canvas.drawCentredString(0, 0, "AEROSCRIBE NRF")
        canvas.setFillAlpha(1.0)
        canvas.translate(-(PAGE_W / 2), -(PAGE_H / 2))

        # Running header (skip on first page to not conflict with banner)
        if not is_first:
            canvas.setFillColor(C_NAVY)
            canvas.rect(0, PAGE_H - 14 * mm, PAGE_W, 14 * mm, fill=1, stroke=0)
            canvas.setFillColor(C_WHITE)
            canvas.setFont("Helvetica-Bold", 8)
            canvas.drawString(L_MARGIN, PAGE_H - 9 * mm, "AEROSCRIBE — NON-ROUTINE FINDING REPORT")
            canvas.setFont("Helvetica", 7)
            canvas.drawRightString(PAGE_W - R_MARGIN, PAGE_H - 9 * mm, f"Document: {report_id}")

        # Running footer
        canvas.setFillColor(C_NAVY)
        canvas.rect(0, 0, PAGE_W, 12 * mm, fill=1, stroke=0)
        canvas.setFillColor(C_WHITE)
        canvas.setFont("Helvetica", 7)
        footer_left = f"Generated: {doc_date}  ·  AeroScribe AI MRO System"
        canvas.drawString(L_MARGIN, 4.5 * mm, footer_left)
        canvas.drawRightString(
            PAGE_W - R_MARGIN, 4.5 * mm,
            f"Page {doc.page}  ·  RESTRICTED — MAINTENANCE PERSONNEL ONLY"
        )

        canvas.restoreState()

    def on_first_page(canvas, doc):
        _draw_page(canvas, doc, is_first=True)

    def on_later_pages(canvas, doc):
        _draw_page(canvas, doc, is_first=False)

    return on_first_page, on_later_pages


# ── Style Sheet ───────────────────────────────────────────────────────────────

def _build_styles():
    styles = getSampleStyleSheet()
    common = dict(fontName="Helvetica", leading=13)

    def ps(name, **kw):
        return ParagraphStyle(name, parent=styles["Normal"], **{**common, **kw})

    return {
        "banner_main": ps("BannerMain", fontName="Helvetica-Bold", fontSize=13,
                          leading=17, textColor=C_WHITE, alignment=0),
        "banner_sub": ps("BannerSub", fontName="Helvetica", fontSize=8,
                         leading=11, textColor=colors.HexColor("#94A3B8")),
        "section_h": ps("SectionH", fontName="Helvetica-Bold", fontSize=9.5,
                        textColor=C_NAVY, spaceBefore=10, spaceAfter=5,
                        letterSpacing=1.0, leading=14),
        "label": ps("Label", fontName="Helvetica-Bold", fontSize=7.5,
                    textColor=C_MUTED, leading=10),
        "val": ps("Val", fontName="Helvetica", fontSize=9,
                  textColor=C_NAVY, leading=12),
        "body": ps("Body", fontSize=8.5, textColor=C_SLATE, leading=13),
        "step_num": ps("StepNum", fontName="Helvetica-Bold", fontSize=8.5,
                       textColor=C_BLUE, leading=13),
        "step_text": ps("StepText", fontSize=8.5, textColor=C_SLATE, leading=13),
        "severity": ps("Severity", fontName="Helvetica-Bold", fontSize=8.5, leading=13),
        "sub": ps("Sub", fontSize=7.5, textColor=C_MUTED, leading=10),
        "footer_note": ps("FooterNote", fontSize=7, textColor=C_MUTED,
                          leading=10, spaceBefore=4),
        "sig_label": ps("SigLabel", fontName="Helvetica-Bold", fontSize=7.5,
                        textColor=C_MUTED, leading=10),
        "sig_val": ps("SigVal", fontSize=8, textColor=C_NAVY, leading=11),
    }


# ── Section Builders ──────────────────────────────────────────────────────────

def _section_rule(styles):
    """Thin horizontal divider with section label styling."""
    return HRFlowable(width="100%", thickness=0.5, color=C_DIVIDER,
                      spaceAfter=6, spaceBefore=2)


def _banner(report_id, doc_date, styles):
    """Full-width branded header banner."""
    data = [[
        Paragraph(
            "<b>AEROSCRIBE  ·  NON-ROUTINE FINDING REPORT</b>",
            styles["banner_main"]
        ),
        Paragraph(
            f"<b>Document:</b> {report_id}<br/>"
            f"<b>Issued:</b> {doc_date}",
            ParagraphStyle("BannerRight", parent=styles["banner_sub"],
                           alignment=2)  # right-align
        ),
    ]]
    t = Table(data, colWidths=[USABLE_W * 0.6, USABLE_W * 0.4])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_NAVY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
        ("LEFTPADDING", (0, 0), (0, 0), 16),
        ("RIGHTPADDING", (-1, -1), (-1, -1), 16),
    ]))
    return t


def _meta_grid(report_id, aircraft_id, amm_entry, doc_date, styles):
    """4-column metadata grid showing key document metadata."""
    lbl = styles["label"]
    val = styles["val"]
    rows = [
        [Paragraph("<b>REPORT ID</b>", lbl),         Paragraph(report_id, val),
         Paragraph("<b>ISSUE DATE / TIME</b>", lbl), Paragraph(doc_date, val)],
        [Paragraph("<b>AIRCRAFT REGISTRATION</b>", lbl), Paragraph(aircraft_id, val),
         Paragraph("<b>ATA SYSTEM CHAPTER</b>", lbl), Paragraph(amm_entry["chapter"], val)],
        [Paragraph("<b>AMM DIRECTIVE REF.</b>", lbl), Paragraph(amm_entry["id"], val),
         Paragraph("<b>DISPOSITION STATUS</b>", lbl), Paragraph("<b>PENDING APPROVAL</b>", val)],
        [Paragraph("<b>REGULATORY REFERENCE</b>", lbl),
         Paragraph(amm_entry.get("regulatory_reference", "N/A"), val),
         Paragraph("<b>RISK CATEGORY</b>", lbl),
         Paragraph(f"<b>Risk Level {amm_entry.get('risk_level', '—')}</b>", val)],
    ]
    col_w = USABLE_W / 4
    t = Table(rows, colWidths=[col_w * 0.9, col_w * 1.1, col_w * 0.9, col_w * 1.1])
    t.setStyle(TableStyle([
        ("GRID",       (0, 0), (-1, -1), 0.4, C_DIVIDER),
        ("BACKGROUND", (0, 0), (0, -1), C_BG_ROW),
        ("BACKGROUND", (2, 0), (2, -1), C_BG_ROW),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
    ]))
    return t


def _severity_banner(amm_entry, styles):
    """Color-coded severity alert banner."""
    sev = amm_entry.get("severity_class", "")
    risk = amm_entry.get("risk_level", 3)
    palette = {
        1: (C_SEV_1_BG, C_SEV_1_FG, C_SEV_1_BD),
        2: (C_SEV_2_BG, C_SEV_2_FG, C_SEV_2_BD),
        3: (C_SEV_3_BG, C_SEV_3_FG, C_SEV_3_BD),
        4: (C_SEV_4_BG, C_SEV_4_FG, C_SEV_4_BD),
    }
    bg, fg, bd = palette.get(risk, palette[3])

    rich = (f"<font color='{fg.hexval()}'>"
            f"<b>▲ SAFETY SCHEDULE NOTICE:</b>  {sev}</font>")
    data = [[Paragraph(rich, styles["severity"])]]
    t = Table(data, colWidths=[USABLE_W])
    t.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, -1), bg),
        ("BOX",          (0, 0), (-1, -1), 1.2, bd),
        ("TOPPADDING",   (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 9),
        ("LEFTPADDING",  (0, 0), (-1, -1), 12),
    ]))
    return t


def _defect_grid(defect, styles):
    """Two-column defect finding detail table."""
    lbl = styles["label"]
    val = styles["val"]
    bbox = defect.get("bbox", [])
    bbox_str = (f"({bbox[0]:.0f}, {bbox[1]:.0f})  →  ({bbox[2]:.0f}, {bbox[3]:.0f})"
                if len(bbox) == 4 else "N/A")
    rows = [
        [Paragraph("<b>DETECTED ANOMALY TYPE</b>", lbl),
         Paragraph(defect.get("label", "N/A").replace("_", " ").upper(), val),
         Paragraph("<b>AI CONFIDENCE SCORE</b>", lbl),
         Paragraph(f"{defect.get('confidence', 0) * 100:.1f}%", val)],
        [Paragraph("<b>BOUNDING BOX COORDINATES (px)</b>", lbl),
         Paragraph(bbox_str, val),
         Paragraph("<b>DETECTION METHOD</b>", lbl),
         Paragraph("YOLOv8 Computer Vision", val)],
    ]
    col_w = USABLE_W / 4
    t = Table(rows, colWidths=[col_w * 0.95, col_w * 1.05, col_w * 0.95, col_w * 1.05])
    t.setStyle(TableStyle([
        ("GRID",       (0, 0), (-1, -1), 0.4, C_DIVIDER),
        ("BACKGROUND", (0, 0), (0, -1), C_BG_ROW),
        ("BACKGROUND", (2, 0), (2, -1), C_BG_ROW),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
    ]))
    return t


def _amm_reference_grid(amm_entry, styles):
    """AMM directive metadata: tooling, duration, parts."""
    lbl = styles["label"]
    val = styles["val"]
    rows = [
        [Paragraph("<b>DIRECTIVE TITLE</b>", lbl),
         Paragraph(amm_entry["title"], val)],
        [Paragraph("<b>REQUIRED TOOLING &amp; EQUIPMENT</b>", lbl),
         Paragraph(amm_entry.get("tooling", "N/A"), val)],
        [Paragraph("<b>PARTS &amp; CONSUMABLES REQUIRED</b>", lbl),
         Paragraph(amm_entry.get("parts_required", "N/A"), val)],
        [Paragraph("<b>ESTIMATED LABOR DURATION</b>", lbl),
         Paragraph(amm_entry.get("estimated_duration", "N/A"), val)],
    ]
    col_w = USABLE_W
    t = Table(rows, colWidths=[col_w * 0.32, col_w * 0.68])
    t.setStyle(TableStyle([
        ("GRID",       (0, 0), (-1, -1), 0.4, C_DIVIDER),
        ("BACKGROUND", (0, 0), (0, -1), C_BG_ROW),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
    ]))
    return t


def _procedure_table(amm_entry, styles):
    """Render procedure steps as a numbered table with alternating row shading."""
    rows = []
    header = [
        Paragraph("<b>STEP</b>", styles["label"]),
        Paragraph("<b>WORK INSTRUCTION</b>", styles["label"]),
    ]
    rows.append(header)

    step_lines = [
        line.strip()
        for line in amm_entry["procedure"].split("\n")
        if line.strip()
    ]

    for i, line in enumerate(step_lines):
        # Strip leading "Step N." prefix from text (we render step number separately)
        text = line
        for prefix in (f"Step {i+1}.", f"{i+1}."):
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
                break

        rows.append([
            Paragraph(f"<b>{i + 1:02d}</b>", styles["step_num"]),
            Paragraph(text, styles["step_text"]),
        ])

    t = Table(rows, colWidths=[USABLE_W * 0.08, USABLE_W * 0.92])
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), C_NAVY),
        ("TEXTCOLOR",  (0, 0), (-1, 0), C_WHITE),
        ("GRID",       (0, 0), (-1, -1), 0.4, C_DIVIDER),
        ("VALIGN",     (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("ALIGN",      (0, 0), (0, -1), "CENTER"),
    ]
    # Alternating row shading (skip header row at index 0)
    for idx in range(1, len(rows)):
        if idx % 2 == 0:
            style_cmds.append(("BACKGROUND", (0, idx), (-1, idx), C_BG_ALT))
    t.setStyle(TableStyle(style_cmds))
    return t


def _signoff_block(inspector_notes, inspector_name, doc_date, report_id, styles):
    """Dual-column inspector sign-off block."""
    lbl = styles["sig_label"]
    val = styles["sig_val"]
    notes_text = (inspector_notes.strip()
                  if inspector_notes.strip()
                  else "Inspector verified AI recommendation. No structural discrepancies noted.")
    name_text = inspector_name.strip() if inspector_name.strip() else "________________"

    left = [
        [Paragraph("<b>AEROSCRIBE SYSTEM LOG</b>", lbl)],
        [Paragraph(f"Report ID: {report_id}", val)],
        [Paragraph(f"Timestamp: {doc_date}", val)],
        [Spacer(1, 10)],
        [Paragraph("__________________________________", val)],
        [Paragraph("AeroScribe AI Inspection Agent", styles["sub"])],
    ]
    right = [
        [Paragraph("<b>CERTIFIED INSPECTOR APPROVAL</b>", lbl)],
        [Paragraph(f"Inspector: {name_text}", val)],
        [Paragraph("License / Auth No.: ________________", val)],
        [Spacer(1, 10)],
        [Paragraph("__________________________________", val)],
        [Paragraph("Signature &amp; Date", styles["sub"])],
    ]
    # Render each side as a sub-table, then place side by side
    def make_side(rows_data):
        t = Table(rows_data, colWidths=[USABLE_W * 0.46])
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ]))
        return t

    gap = [[Spacer(USABLE_W * 0.04, 1)]]
    outer = Table(
        [[make_side(left), Table(gap, colWidths=[USABLE_W * 0.04]), make_side(right)]],
        colWidths=[USABLE_W * 0.46, USABLE_W * 0.04, USABLE_W * 0.50],
    )
    outer.setStyle(TableStyle([
        ("BOX",          (0, 0), (-1, -1), 0.5, C_DIVIDER),
        ("TOPPADDING",   (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 14),
        ("LEFTPADDING",  (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (-1, -1), (-1, -1), 14),
        ("LINEAFTER",    (0, 0), (0, -1), 0.5, C_DIVIDER),
        ("VALIGN",       (0, 0), (-1, -1), "TOP"),
    ]))
    return outer


def _inspector_notes_block(inspector_notes, styles):
    """Bordered inspector notes section."""
    notes_text = (inspector_notes.strip()
                  if inspector_notes.strip()
                  else "Inspector verified AI recommendation. No structural discrepancies noted.")
    data = [[Paragraph(notes_text, styles["body"])]]
    t = Table(data, colWidths=[USABLE_W])
    t.setStyle(TableStyle([
        ("BOX",          (0, 0), (-1, -1), 0.5, C_DIVIDER),
        ("BACKGROUND",   (0, 0), (-1, -1), C_BG_ROW),
        ("TOPPADDING",   (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 10),
        ("LEFTPADDING",  (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
    ]))
    return t


# ── Main Entry Point ──────────────────────────────────────────────────────────

def generate_nrf_report(
    defect: dict,
    amm_entry: dict,
    inspector_notes: str = "",
    aircraft_id: str = "N/A",
    report_id: str = None,
    inspector_name: str = "",
) -> tuple[str, str]:
    """
    Generate a professional NRF compliance PDF report.

    Returns:
        (filepath, report_id) tuple.
    """
    if report_id is None:
        report_id = "NRF-" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S")

    filepath = os.path.join(OUTPUT_DIR, f"{report_id}.pdf")
    doc_date = datetime.datetime.now().strftime("%Y-%m-%d  %H:%M  UTC")

    on_first, on_later = _make_page_callbacks(report_id, doc_date)

    doc = SimpleDocTemplate(
        filepath,
        pagesize=A4,
        topMargin=T_MARGIN,
        bottomMargin=B_MARGIN,
        leftMargin=L_MARGIN,
        rightMargin=R_MARGIN,
    )

    S = _build_styles()
    E = []  # flowable elements list

    def section(title, number):
        E.append(Spacer(1, 5 * mm))
        E.append(Paragraph(
            f"<font color='#1D4ED8'>{number}.</font>  {title}",
            S["section_h"]
        ))
        E.append(_section_rule(S))

    # ── 1. Header Banner ─────────────────────────────────────────────────────
    E.append(_banner(report_id, doc_date, S))
    E.append(Spacer(1, 5 * mm))

    # ── 2. Document Metadata Grid ─────────────────────────────────────────────
    section("DOCUMENT METADATA", "A")
    E.append(_meta_grid(report_id, aircraft_id, amm_entry, doc_date, S))

    # ── 3. Defect Scan Results ────────────────────────────────────────────────
    section("STRUCTURAL INSPECTION SCAN RESULTS", "B")
    E.append(_defect_grid(defect, S))
    E.append(Spacer(1, 3 * mm))
    E.append(_severity_banner(amm_entry, S))

    # ── 4. Regulatory Manual Reference ───────────────────────────────────────
    section("REGULATORY MANUAL REFERENCE (AMM)", "C")
    E.append(_amm_reference_grid(amm_entry, S))

    # ── 5. Approved Work Instructions ────────────────────────────────────────
    section("APPROVED MAINTENANCE WORK INSTRUCTIONS", "D")
    E.append(_procedure_table(amm_entry, S))

    # ── 6. Inspector Remarks ──────────────────────────────────────────────────
    section("INSPECTION REMARKS &amp; DEBRIS LOGS", "E")
    E.append(_inspector_notes_block(inspector_notes, S))

    # ── 7. Sign-off Block ─────────────────────────────────────────────────────
    section("CERTIFICATION &amp; SIGN-OFF", "F")
    E.append(_signoff_block(inspector_notes, inspector_name, doc_date, report_id, S))

    # ── 8. Legal Footer Note ──────────────────────────────────────────────────
    E.append(Spacer(1, 6 * mm))
    E.append(Paragraph(
        "<b>SYSTEM NOTICE:</b>  This NRF report was compiled offline on local MRO edge AI hardware. "
        "Aircraft structural release requires a wet signature from a licensed certifying engineer and "
        "contemporaneous entry in the primary aircraft technical log in accordance with EASA Part-M "
        "/ FAA Part-43 requirements. This document does not substitute for regulatory compliance.",
        S["footer_note"]
    ))

    doc.build(E, onFirstPage=on_first, onLaterPages=on_later)
    return filepath, report_id
