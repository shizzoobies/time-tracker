from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable, Image as RLImage
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from datetime import datetime
import io
import urllib.parse

def _make_venmo_qr(url: str) -> io.BytesIO:
    import qrcode
    qr = qrcode.QRCode(version=1, box_size=5, border=3,
                       error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1c1917", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


DARK   = colors.HexColor('#1c1917')
PINK   = colors.HexColor('#c4006e')
ACCENT = colors.HexColor('#fff0f8')
GOLD   = colors.HexColor('#b8882a')
WHITE  = colors.white
STRIPE = colors.HexColor('#fceef5')
BORDER = colors.HexColor('#ddd6cf')
GRAY   = colors.HexColor('#5c5248')
LGRAY  = colors.HexColor('#ede8e3')


def generate_invoice(output_path, settings: dict, invoice_data: dict) -> str:
    """
    settings keys : your_name, company_name, client_email, retainer_amount
    invoice_data  : invoice_number, invoice_date, period_label, period_start,
                    period_end, service_description, hours_as_of, hours_in_period,
                    hours_total
    """
    your_name    = settings.get('your_name',    'Consultant')
    client_name  = settings.get('company_name', 'Client')
    amount_str   = settings.get('retainer_amount', '750.00')
    service_desc = invoice_data.get('service_description',
                                    'AI Integration & Web Development Services — Monthly Retainer')
    inv_num      = invoice_data['invoice_number']
    inv_date     = invoice_data['invoice_date']        # display string e.g. "May 1, 2026"
    period_label = invoice_data['period_label']        # e.g. "May 2026"
    hours_as_of  = invoice_data.get('hours_as_of', '')
    hrs_period   = invoice_data.get('hours_in_period', 0.0)
    hrs_total    = invoice_data.get('hours_total', 0.0)

    try:
        amount = float(amount_str.replace(',', '').replace('$', ''))
    except ValueError:
        amount = 750.0

    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.7 * inch,
        bottomMargin=0.7 * inch,
    )

    # ── Styles ────────────────────────────────────────────────────────────────
    s_title   = ParagraphStyle('InvTitle',  fontSize=32, fontName='Helvetica-Bold',
                               textColor=PINK,  leading=36)
    s_name    = ParagraphStyle('InvName',   fontSize=13, fontName='Helvetica-Bold',
                               textColor=DARK,  leading=17)
    s_sub     = ParagraphStyle('InvSub',    fontSize=9,  fontName='Helvetica',
                               textColor=GRAY,  leading=13)
    s_label   = ParagraphStyle('InvLabel',  fontSize=8,  fontName='Helvetica-Bold',
                               textColor=GRAY,  leading=11, spaceAfter=2)
    s_value   = ParagraphStyle('InvValue',  fontSize=11, fontName='Helvetica',
                               textColor=DARK,  leading=15)
    s_value_b = ParagraphStyle('InvValueB', fontSize=11, fontName='Helvetica-Bold',
                               textColor=DARK,  leading=15)
    s_note    = ParagraphStyle('InvNote',   fontSize=8,  fontName='Helvetica-Oblique',
                               textColor=GRAY,  leading=12)
    s_footer  = ParagraphStyle('InvFooter', fontSize=8,  fontName='Helvetica',
                               textColor=GRAY,  leading=11, alignment=TA_CENTER)

    story = []

    # ── Top: name/contact left, INVOICE + number right ───────────────────────
    left = [
        Paragraph(your_name, s_name),
        Spacer(1, 4),
        Paragraph("Independent Contractor", s_sub),
    ]
    right = [
        Paragraph("INVOICE", s_title),
        Spacer(1, 2),
        Paragraph(f"<b>{inv_num}</b>", ParagraphStyle('RNum', fontSize=11,
                  fontName='Helvetica-Bold', textColor=GRAY, alignment=TA_RIGHT)),
        Paragraph(inv_date, ParagraphStyle('RDate', fontSize=9,
                  fontName='Helvetica', textColor=GRAY, alignment=TA_RIGHT)),
    ]
    top = Table([[left, right]], colWidths=[3.6*inch, 3.5*inch])
    top.setStyle(TableStyle([
        ('VALIGN',  (0, 0), (-1, -1), 'TOP'),
        ('ALIGN',   (1, 0), (1, -1),  'RIGHT'),
        ('LEFTPADDING',  (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING',   (0,0), (-1,-1), 0),
        ('BOTTOMPADDING',(0,0), (-1,-1), 0),
    ]))
    story.append(top)
    story.append(Spacer(1, 0.18*inch))
    story.append(HRFlowable(width='100%', thickness=2, color=PINK, spaceAfter=14))

    # ── Bill To + Invoice Meta side by side ───────────────────────────────────
    bill_cell = [
        Paragraph("BILL TO", s_label),
        Paragraph(client_name, s_value_b),
    ]
    meta_rows = [
        ["Invoice Date",   inv_date],
        ["Covers",         f"All work — {period_label}"],
        ["Due",            inv_date],   # billed ahead — due on invoice date
    ]
    meta_tbl = Table(meta_rows, colWidths=[1.1*inch, 1.8*inch])
    meta_tbl.setStyle(TableStyle([
        ('FONTNAME',      (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME',      (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE',      (0, 0), (-1,-1), 9),
        ('TEXTCOLOR',     (0, 0), (0, -1), GRAY),
        ('TEXTCOLOR',     (1, 0), (1, -1), DARK),
        ('TOPPADDING',    (0, 0), (-1,-1), 3),
        ('BOTTOMPADDING', (0, 0), (-1,-1), 3),
        ('LEFTPADDING',   (0, 0), (-1,-1), 0),
        ('RIGHTPADDING',  (0, 0), (-1,-1), 0),
    ]))

    info_tbl = Table([[bill_cell, '', meta_tbl]], colWidths=[3.0*inch, 0.5*inch, 3.6*inch])
    info_tbl.setStyle(TableStyle([
        ('VALIGN',       (0,0), (-1,-1), 'TOP'),
        ('ALIGN',        (2,0), (2,-1),  'RIGHT'),
        ('LEFTPADDING',  (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING',   (0,0), (-1,-1), 0),
        ('BOTTOMPADDING',(0,0), (-1,-1), 0),
    ]))
    story.append(info_tbl)
    story.append(Spacer(1, 0.22*inch))

    # ── Line items ────────────────────────────────────────────────────────────
    item_rows = [
        ['Description', 'Amount'],
        [Paragraph(service_desc, ParagraphStyle('Desc', fontSize=10,
                   fontName='Helvetica', textColor=DARK, leading=14)),
         f"${amount:,.2f}"],
        ['', ''],
        [Paragraph('<b>TOTAL DUE</b>', ParagraphStyle('Tot', fontSize=11,
                   fontName='Helvetica-Bold', textColor=DARK)), f"<b>${amount:,.2f}</b>"],
    ]
    # Make total amount bold paragraph
    item_rows[3][1] = Paragraph(f"${amount:,.2f}", ParagraphStyle(
        'TotAmt', fontSize=12, fontName='Helvetica-Bold', textColor=PINK,
        alignment=TA_RIGHT))

    item_tbl = Table(item_rows, colWidths=[5.5*inch, 1.6*inch], repeatRows=1)
    item_tbl.setStyle(TableStyle([
        # Header
        ('BACKGROUND',    (0,0), (-1,0),  DARK),
        ('TEXTCOLOR',     (0,0), (-1,0),  WHITE),
        ('FONTNAME',      (0,0), (-1,0),  'Helvetica-Bold'),
        ('FONTSIZE',      (0,0), (-1,0),  9),
        ('TOPPADDING',    (0,0), (-1,0),  9),
        ('BOTTOMPADDING', (0,0), (-1,0),  9),
        ('LEFTPADDING',   (0,0), (-1,0),  10),
        ('ALIGN',         (1,0), (1,0),   'RIGHT'),
        # Service row
        ('BACKGROUND',    (0,1), (-1,1),  WHITE),
        ('TOPPADDING',    (0,1), (-1,1),  10),
        ('BOTTOMPADDING', (0,1), (-1,1),  10),
        ('LEFTPADDING',   (0,1), (-1,1),  10),
        ('RIGHTPADDING',  (0,1), (-1,1),  10),
        ('ALIGN',         (1,1), (1,1),   'RIGHT'),
        ('FONTSIZE',      (1,1), (1,1),   11),
        # Spacer row
        ('BACKGROUND',    (0,2), (-1,2),  LGRAY),
        ('TOPPADDING',    (0,2), (-1,2),  2),
        ('BOTTOMPADDING', (0,2), (-1,2),  2),
        # Total row
        ('BACKGROUND',    (0,3), (-1,3),  ACCENT),
        ('TOPPADDING',    (0,3), (-1,3),  10),
        ('BOTTOMPADDING', (0,3), (-1,3),  10),
        ('LEFTPADDING',   (0,3), (-1,3),  10),
        ('RIGHTPADDING',  (0,3), (-1,3),  10),
        # Borders
        ('BOX',           (0,0), (-1,-1), 1, BORDER),
        ('LINEBELOW',     (0,0), (-1,0),  1.5, PINK),
        ('LINEABOVE',     (0,3), (-1,3),  1, BORDER),
    ]))
    story.append(item_tbl)
    story.append(Spacer(1, 0.2*inch))

    # ── Hours note (informational) ────────────────────────────────────────────
    if hours_as_of:
        hrs_line = (f"Informational — Hours worked as of {hours_as_of}: "
                    f"{hrs_period:.1f} hrs this period  |  {hrs_total:.1f} hrs total on record")
        note_tbl = Table([[Paragraph(hrs_line, s_note)]],
                         colWidths=[7.1*inch])
        note_tbl.setStyle(TableStyle([
            ('BACKGROUND',    (0,0), (-1,-1), ACCENT),
            ('LEFTPADDING',   (0,0), (-1,-1), 10),
            ('RIGHTPADDING',  (0,0), (-1,-1), 10),
            ('TOPPADDING',    (0,0), (-1,-1), 7),
            ('BOTTOMPADDING', (0,0), (-1,-1), 7),
            ('BOX',           (0,0), (-1,-1), 0.5, BORDER),
        ]))
        story.append(note_tbl)
        story.append(Spacer(1, 0.18*inch))

    # ── Venmo payment block ───────────────────────────────────────────────────
    venmo_user = settings.get('venmo_username', '').strip().lstrip('@')
    if venmo_user:
        note      = urllib.parse.quote(f"Invoice {inv_num}")
        deep_link = (f"venmo://paycharge?txn=pay&recipients={venmo_user}"
                     f"&amount={amount:.2f}&note={note}")
        pay_params = urllib.parse.urlencode({
            "txn": "pay", "amount": f"{amount:.2f}", "note": f"Invoice {inv_num}"
        })
        is_phone = venmo_user.replace('-', '').replace('.', '').isdigit()
        if is_phone:
            # No standard venmo.com/u/ for phone — use account payment link
            web_link   = (f"https://account.venmo.com/payment-link?"
                          f"recipients={venmo_user}&{pay_params}")
            display_id = venmo_user
        else:
            web_link   = f"https://venmo.com/u/{venmo_user}?{pay_params}"
            display_id = f"@{venmo_user}"

        qr_buf = _make_venmo_qr(deep_link)
        qr_img = RLImage(qr_buf, width=0.95 * inch, height=0.95 * inch)

        s_pay  = ParagraphStyle('VPay',  fontSize=10, fontName='Helvetica-Bold',
                                textColor=DARK,  leading=14)
        s_link = ParagraphStyle('VLink', fontSize=9,  fontName='Helvetica',
                                textColor=PINK,  leading=13)
        s_hint = ParagraphStyle('VHint', fontSize=8,  fontName='Helvetica-Oblique',
                                textColor=GRAY,  leading=12)

        right = [
            Paragraph("Pay with Venmo", s_pay),
            Spacer(1, 3),
            Paragraph(f'<a href="{web_link}"><u>Click here to pay</u></a>', s_link),
            Spacer(1, 2),
            Paragraph(f"${amount:,.2f}  ·  {inv_num}", s_hint),
            Spacer(1, 3),
            Paragraph("Scan QR code with your phone camera to open Venmo and pay instantly.", s_hint),
        ]

        v_tbl = Table([[qr_img, right]], colWidths=[1.15 * inch, 6.0 * inch])
        v_tbl.setStyle(TableStyle([
            ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
            ('BACKGROUND',    (0, 0), (-1, -1), ACCENT),
            ('BOX',           (0, 0), (-1, -1), 0.5, BORDER),
            ('LEFTPADDING',   (0, 0), (-1, -1), 10),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 10),
            ('TOPPADDING',    (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ]))
        story.append(v_tbl)
        story.append(Spacer(1, 0.15 * inch))

    # ── Footer ────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.1*inch))
    story.append(HRFlowable(width='100%', thickness=0.5, color=BORDER))
    story.append(Spacer(1, 5))
    story.append(Paragraph(
        f"{your_name}  ·  {client_name}  ·  {inv_num}  ·  {period_label}",
        s_footer))

    doc.build(story)
    return output_path
