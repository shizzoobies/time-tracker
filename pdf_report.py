from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
)
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from datetime import datetime

# ── Palette ───────────────────────────────────────────────────────────────────
NAVY    = colors.HexColor('#1c1917')   # brand near-black
BLUE    = colors.HexColor('#c4006e')   # brand dark pink
ACCENT  = colors.HexColor('#fff0f8')   # light pink
WHITE   = colors.white
STRIPE  = colors.HexColor('#fceef5')   # light pink stripe
BORDER  = colors.HexColor('#ddd6cf')   # warm border
GRID    = colors.HexColor('#f5ede8')   # warm grid
GREEN   = colors.HexColor('#2ea3c5')   # brand teal
GRAY    = colors.HexColor('#5c5248')   # brand muted
LGRAY   = colors.HexColor('#ede8e3')   # warm surface


def _fmt_time_range(start, end) -> str:
    def to12(t: str) -> str:
        try:
            h, m = map(int, t.split(':'))
            period = "AM" if h < 12 else "PM"
            return f"{h % 12 or 12}:{m:02d} {period}"
        except Exception:
            return t
    if start and end:
        return f"{to12(start)} – {to12(end)}"
    if start:
        return to12(start)
    if end:
        return to12(end)
    return ""


def generate_pdf(entries, week_start, week_end, output_path, settings=None, projects=None):
    if settings is None:
        settings = {}

    your_name    = settings.get('your_name',    'Consultant')
    company      = settings.get('company_name', 'Client')
    rate_str     = settings.get('hourly_rate',  '').strip()
    total_hours  = sum(e['hours'] for e in entries)

    cats: dict[str, float] = {}
    for e in entries:
        cat = e.get('category', 'Other')
        cats[cat] = cats.get(cat, 0) + e['hours']

    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        rightMargin=0.7 * inch,
        leftMargin=0.7 * inch,
        topMargin=0.65 * inch,
        bottomMargin=0.65 * inch,
    )

    styles = getSampleStyleSheet()

    # ── Cell paragraph styles (enable text wrapping inside table cells) ───
    cell_normal = ParagraphStyle('CellNormal', fontSize=9, fontName='Helvetica',
                                 textColor=colors.HexColor('#1c1917'), leading=12)
    cell_bold   = ParagraphStyle('CellBold',   fontSize=9, fontName='Helvetica-Bold',
                                 textColor=colors.HexColor('#1c1917'), leading=12)

    # ── Custom paragraph styles ────────────────────────────────────────────
    hdr_title = ParagraphStyle('HdrTitle', fontSize=24, fontName='Helvetica-Bold',
                               textColor=WHITE, leading=28)
    hdr_sub   = ParagraphStyle('HdrSub',   fontSize=10, fontName='Helvetica',
                               textColor=colors.HexColor('#c8ccee'), leading=15)
    hdr_right = ParagraphStyle('HdrRight', fontSize=10, fontName='Helvetica',
                               textColor=WHITE, leading=15, alignment=TA_RIGHT)
    hdr_right_bold = ParagraphStyle('HdrRightB', fontSize=11, fontName='Helvetica-Bold',
                                    textColor=WHITE, leading=16, alignment=TA_RIGHT)
    section_hdr = ParagraphStyle('SecHdr', fontSize=11, fontName='Helvetica-Bold',
                                 textColor=NAVY, spaceBefore=14, spaceAfter=5)

    story = []

    # ── Page header block ──────────────────────────────────────────────────
    week_range = (
        f"{datetime.strptime(week_start, '%Y-%m-%d').strftime('%B %d')} – "
        f"{datetime.strptime(week_end,   '%Y-%m-%d').strftime('%B %d, %Y')}"
    )
    generated = datetime.now().strftime('%B %d, %Y')

    left_cell = [
        Paragraph("TIME REPORT", hdr_title),
        Spacer(1, 4),
        Paragraph(f"Prepared by {your_name}", hdr_sub),
        Paragraph(f"For {company}", hdr_sub),
    ]
    right_cell = [
        Paragraph(week_range, hdr_right_bold),
        Paragraph(f"Generated {generated}", hdr_right),
    ]

    header_tbl = Table(
        [[left_cell, right_cell]],
        colWidths=[4.2 * inch, 2.9 * inch],
    )
    header_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), NAVY),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING',    (0, 0), (-1, -1), 20),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 20),
        ('LEFTPADDING',   (0, 0), (0, -1),  22),
        ('RIGHTPADDING',  (-1, 0), (-1, -1), 22),
        ('ROUNDEDCORNERS', [6, 6, 6, 6]),
    ]))
    story.append(header_tbl)
    story.append(Spacer(1, 0.22 * inch))

    # ── Summary + category side-by-side ───────────────────────────────────
    # Left: summary card
    sum_rows = [['', '']]
    sum_rows.append(['Total Hours', f"{total_hours:.2f} hrs"])
    if rate_str:
        try:
            rate = float(rate_str)
            sum_rows.append(['Rate',         f"${rate:,.2f} / hr"])
            sum_rows.append(['Amount Due',   f"${total_hours * rate:,.2f}"])
        except ValueError:
            pass
    sum_rows.append(['Entries',  str(len(entries))])

    sum_style = TableStyle([
        ('SPAN',          (0, 0), (-1, 0)),
        ('BACKGROUND',    (0, 0), (-1, 0), BLUE),
        ('TEXTCOLOR',     (0, 0), (-1, 0), WHITE),
        ('FONTNAME',      (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',      (0, 0), (-1, 0), 9),
        ('ALIGN',         (0, 0), (-1, 0), 'CENTER'),
        ('BACKGROUND',    (0, 1), (-1, -1), ACCENT),
        ('ROWBACKGROUNDS',(0, 1), (-1, -1), [ACCENT, WHITE]),
        ('FONTNAME',      (0, 1), (0, -1),  'Helvetica-Bold'),
        ('FONTNAME',      (1, 1), (1, -1),  'Helvetica'),
        ('FONTSIZE',      (0, 1), (-1, -1), 10),
        ('ALIGN',         (1, 1), (1, -1),  'RIGHT'),
        ('BOX',           (0, 0), (-1, -1), 1, BORDER),
        ('LINEBELOW',     (0, 0), (-1, 0),  1, BORDER),
        ('GRID',          (0, 1), (-1, -1), 0.5, GRID),
        ('TOPPADDING',    (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('LEFTPADDING',   (0, 0), (-1, -1), 10),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 10),
    ])

    sum_rows2 = [['SUMMARY', '']] + sum_rows[1:]
    sum_tbl2 = Table(sum_rows2, colWidths=[1.6 * inch, 1.5 * inch])
    sum_tbl2.setStyle(sum_style)

    # Right: category breakdown
    if cats:
        cat_rows = [['CATEGORY', 'HRS', '%']]
        for cat, hrs in sorted(cats.items(), key=lambda x: -x[1]):
            pct = (hrs / total_hours * 100) if total_hours else 0
            cat_rows.append([cat, f"{hrs:.2f}", f"{pct:.0f}%"])

        cat_tbl = Table(cat_rows, colWidths=[2.0 * inch, 0.7 * inch, 0.6 * inch])
        cat_tbl.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, 0), BLUE),
            ('TEXTCOLOR',     (0, 0), (-1, 0), WHITE),
            ('FONTNAME',      (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE',      (0, 0), (-1, 0), 9),
            ('ALIGN',         (1, 0), (-1, -1), 'CENTER'),
            ('ROWBACKGROUNDS',(0, 1), (-1, -1), [WHITE, STRIPE]),
            ('FONTSIZE',      (0, 1), (-1, -1), 9),
            ('BOX',           (0, 0), (-1, -1), 1, BORDER),
            ('LINEBELOW',     (0, 0), (-1, 0),  1, BORDER),
            ('GRID',          (0, 1), (-1, -1), 0.5, GRID),
            ('TOPPADDING',    (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING',   (0, 0), (-1, -1), 8),
        ]))
    else:
        cat_tbl = Paragraph("", styles['Normal'])

    side_tbl = Table(
        [[sum_tbl2, '', cat_tbl]],
        colWidths=[3.2 * inch, 0.3 * inch, 3.6 * inch],
    )
    side_tbl.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING',  (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING',   (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 0),
    ]))
    story.append(side_tbl)
    story.append(Spacer(1, 0.22 * inch))

    # ── Projects section ──────────────────────────────────────────────────
    active_projects = [p for p in (projects or [])
                       if p.get("status") in ("Active", "On Hold")]
    if active_projects:
        story.append(Paragraph("PROJECTS & PRIORITIES", section_hdr))
        story.append(HRFlowable(width="100%", thickness=1.5, color=NAVY, spaceAfter=6))

        proj_rows = [["Priority", "Project", "Status", "% Done", "Due Date"]]
        for p in active_projects:
            due = p.get("due_date") or "—"
            pct = "Ongoing" if p.get("is_ongoing") else f"{p.get('completion', 0)}%"
            proj_rows.append([
                p.get("priority", "Medium"),
                Paragraph(p.get("name", ""), cell_normal),
                p.get("status", "Active"),
                pct,
                due,
            ])

        PRIORITY_COLOR = {
            "High":   colors.HexColor("#c4006e"),
            "Medium": colors.HexColor("#2ea3c5"),
            "Low":    colors.HexColor("#5c5248"),
        }

        col_w = [0.85 * inch, 3.2 * inch, 0.9 * inch, 0.6 * inch, 1.1 * inch]
        pt = Table(proj_rows, colWidths=col_w, repeatRows=1)
        ts = TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0),  NAVY),
            ("TEXTCOLOR",     (0, 0), (-1, 0),  WHITE),
            ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0), (-1, 0),  9),
            ("ALIGN",         (0, 0), (-1, 0),  "CENTER"),
            ("TOPPADDING",    (0, 0), (-1, 0),  8),
            ("BOTTOMPADDING", (0, 0), (-1, 0),  8),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1), [WHITE, STRIPE]),
            ("FONTSIZE",      (0, 1), (-1, -1), 9),
            ("TOPPADDING",    (0, 1), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
            ("ALIGN",         (0, 1), (0, -1),  "CENTER"),   # priority
            ("ALIGN",         (2, 1), (4, -1),  "CENTER"),   # status, %, due
            ("BOX",           (0, 0), (-1, -1), 1,   BORDER),
            ("LINEBELOW",     (0, 0), (-1, 0),  1.5, NAVY),
            ("INNERGRID",     (0, 1), (-1, -1), 0.5, GRID),
            ("LEFTPADDING",   (0, 0), (-1, -1), 7),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 7),
        ])
        for i, p in enumerate(active_projects, start=1):
            c = PRIORITY_COLOR.get(p.get("priority", "Medium"), GRAY)
            ts.add("TEXTCOLOR", (0, i), (0, i), c)
            ts.add("FONTNAME",  (0, i), (0, i), "Helvetica-Bold")
        pt.setStyle(ts)
        story.append(pt)
        story.append(Spacer(1, 0.22 * inch))

    # ── Entries table ──────────────────────────────────────────────────────
    story.append(Paragraph("TIME ENTRIES", section_hdr))
    story.append(HRFlowable(width="100%", thickness=1.5, color=NAVY, spaceAfter=6))

    if entries:
        rows = [['Date', 'Time', 'Hrs', 'Category', 'Description']]
        for e in entries:
            rows.append([
                e['date'],
                _fmt_time_range(e.get('start_time'), e.get('end_time')),
                f"{e['hours']:.2f}",
                Paragraph(e.get('category', 'Other'), cell_normal),
                Paragraph(e['description'], cell_normal),
            ])
        rows.append(['', '', f"{total_hours:.2f}", 'TOTAL', ''])

        col_w = [0.88 * inch, 1.38 * inch, 0.52 * inch, 1.52 * inch, 3.45 * inch]
        et = Table(rows, colWidths=col_w, repeatRows=1)
        et.setStyle(TableStyle([
            # Header
            ('BACKGROUND',    (0, 0), (-1, 0), NAVY),
            ('TEXTCOLOR',     (0, 0), (-1, 0), WHITE),
            ('FONTNAME',      (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE',      (0, 0), (-1, 0), 9),
            ('ALIGN',         (0, 0), (-1, 0), 'CENTER'),
            ('TOPPADDING',    (0, 0), (-1, 0), 8),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            # Data rows
            ('ROWBACKGROUNDS',(0, 1), (-1, -2), [WHITE, STRIPE]),
            ('FONTSIZE',      (0, 1), (-1, -2), 9),
            ('TOPPADDING',    (0, 1), (-1, -2), 6),
            ('BOTTOMPADDING', (0, 1), (-1, -2), 6),
            # Total row
            ('BACKGROUND',    (0, -1), (-1, -1), ACCENT),
            ('FONTNAME',      (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE',      (0, -1), (-1, -1), 10),
            ('TOPPADDING',    (0, -1), (-1, -1), 7),
            ('BOTTOMPADDING', (0, -1), (-1, -1), 7),
            # Borders
            ('BOX',           (0, 0), (-1, -1), 1, BORDER),
            ('LINEBELOW',     (0, 0), (-1, 0),  1.5, NAVY),
            ('LINEABOVE',     (0, -1), (-1, -1), 1, BORDER),
            ('INNERGRID',     (0, 1), (-1, -2), 0.5, GRID),
            # Alignment
            ('ALIGN',         (2, 1), (2, -1), 'CENTER'),  # hrs
            ('LEFTPADDING',   (0, 0), (-1, -1), 7),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 7),
        ]))
        story.append(et)
    else:
        story.append(Paragraph("No entries recorded for this week.", styles['Normal']))

    # ── Footer note ────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.2 * inch))
    story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER))
    story.append(Spacer(1, 4))
    footer_style = ParagraphStyle('Footer', fontSize=8, textColor=GRAY, alignment=TA_CENTER)
    story.append(Paragraph(
        f"{your_name}  ·  {company}  ·  Week of {week_range}",
        footer_style
    ))

    doc.build(story)
    return output_path
