import os
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from app.core.config import settings

def generate_sample_contract(file_path: str):
    """Generates a professional legal contract PDF."""
    doc = SimpleDocTemplate(file_path, pagesize=letter, rightMargin=54, leftMargin=54, topMargin=54, bottomMargin=54)
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontSize=18,
        leading=22,
        alignment=1, # Center
        textColor=colors.HexColor("#1e293b"),
        spaceAfter=15
    )
    section_style = ParagraphStyle(
        'SectionHeader',
        parent=styles['Heading2'],
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#0f172a"),
        spaceBefore=10,
        spaceAfter=6
    )
    body_style = ParagraphStyle(
        'DocBody',
        parent=styles['Normal'],
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#334155"),
        spaceAfter=8
    )

    story = [
        Paragraph("MASTER SERVICES AND NON-DISCLOSURE AGREEMENT", title_style),
        Spacer(1, 10),
        Paragraph("<b>THIS AGREEMENT</b> is made and entered into effective as of <b>October 15, 2026</b> (the \"Effective Date\"), by and between <b>Apex Technologies Inc.</b>, a Delaware corporation having its principal office at 100 Innovation Way, Suite 400, San Francisco, CA 94105 (\"Client\"), and <b>Starlight Global Solutions LLC</b>, a New York limited liability company having its principal office at 450 Lexington Ave, New York, NY 10017 (\"Vendor\").", body_style),
        Spacer(1, 8),
        Paragraph("1. Purpose & Confidentiality", section_style),
        Paragraph("Each party may disclose confidential proprietary trade secrets. The recipient shall safeguard all Confidential Information. Confidentiality obligations shall survive for a period of <b>3 years</b> following termination of this Agreement.", body_style),
        Paragraph("2. Term & Termination", section_style),
        Paragraph("The term of this Agreement shall commence on the Effective Date and shall continue until it shall terminate on <b>October 15, 2028</b>, unless earlier terminated. Either party may terminate upon <b>30 days</b> prior written notice for convenience.", body_style),
        Paragraph("3. Limitation of Liability", section_style),
        Paragraph("Except for gross negligence or willful misconduct, each party's maximum aggregate liability shall not exceed <b>$2,500,000</b> (Two Million Five Hundred Thousand Dollars). In no event shall either party be liable for punitive damages.", body_style),
        Paragraph("4. Governing Law & Dispute Resolution", section_style),
        Paragraph("This Agreement and all claims arising out of or related to this Agreement shall be governed by the laws of the <b>State of Delaware</b>, without regard to conflict of law principles.", body_style),
        Paragraph("5. Indemnification & Risk Notice", section_style),
        Paragraph("Vendor agrees to defend, indemnify and hold harmless Client against third-party claims arising from intellectual property infringement.", body_style),
        Spacer(1, 15),
        Paragraph("IN WITNESS WHEREOF, the authorized representatives of the parties have executed this Agreement.", body_style),
        Spacer(1, 20),
        Table([
            ["CLIENT: Apex Technologies Inc.", "VENDOR: Starlight Global Solutions LLC"],
            ["By: ____________________________", "By: ____________________________"],
            ["Name: Sarah Jenkins", "Name: David Miller"],
            ["Title: Chief Operating Officer", "Title: Managing Director"]
        ], colWidths=[250, 250], style=[
            ('TEXTCOLOR', (0,0), (-1,-1), colors.HexColor("#1e293b")),
            ('FONTSIZE', (0,0), (-1,-1), 9),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ])
    ]
    doc.build(story)

def generate_sample_passport(file_path: str):
    """Generates an ICAO-compliant passport preview PDF."""
    doc = SimpleDocTemplate(file_path, pagesize=letter, rightMargin=54, leftMargin=54, topMargin=54, bottomMargin=54)
    styles = getSampleStyleSheet()

    header_style = ParagraphStyle(
        'PassportHeader',
        parent=styles['Heading1'],
        fontSize=16,
        leading=20,
        alignment=1,
        textColor=colors.HexColor("#0f172a")
    )
    sub_header = ParagraphStyle(
        'SubHeader',
        parent=styles['Normal'],
        fontSize=10,
        alignment=1,
        textColor=colors.HexColor("#64748b"),
        spaceAfter=15
    )
    label_style = ParagraphStyle(
        'PLabel',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.HexColor("#64748b")
    )
    val_style = ParagraphStyle(
        'PVal',
        parent=styles['Normal'],
        fontSize=11,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#0f172a")
    )
    mrz_style = ParagraphStyle(
        'MRZ',
        parent=styles['Normal'],
        fontName="Courier",
        fontSize=13,
        leading=16,
        alignment=1,
        textColor=colors.HexColor("#0f172a")
    )

    data = [
        [Paragraph("Type / Type / Tipo", label_style), Paragraph("Code / Code / Código", label_style), Paragraph("Passport No. / No du Passeport / No. de Pasaporte", label_style)],
        [Paragraph("P", val_style), Paragraph("USA", val_style), Paragraph("563927418", val_style)],
        [Paragraph("Surname / Nom / Apellidos", label_style), "", ""],
        [Paragraph("SMITH", val_style), "", ""],
        [Paragraph("Given Names / Prénoms / Nombres", label_style), "", ""],
        [Paragraph("JOHN MICHAEL", val_style), "", ""],
        [Paragraph("Nationality / Nationalité / Nacionalidad", label_style), Paragraph("Date of Birth / Date de naissance", label_style), Paragraph("Sex / Sexe / Sexo", label_style)],
        [Paragraph("UNITED STATES OF AMERICA", val_style), Paragraph("1985-01-01", val_style), Paragraph("M", val_style)],
        [Paragraph("Authority / Autorité / Autoridad", label_style), Paragraph("Date of Issue / Date de délivrance", label_style), Paragraph("Date of Expiration / Date d'expiration", label_style)],
        [Paragraph("United States Department of State", val_style), Paragraph("2020-01-01", val_style), Paragraph("2030-01-01", val_style)]
    ]

    t = Table(data, colWidths=[160, 160, 160])
    t.setStyle(TableStyle([
        ('SPAN', (0, 2), (2, 2)),
        ('SPAN', (0, 3), (2, 3)),
        ('SPAN', (0, 4), (2, 4)),
        ('SPAN', (0, 5), (2, 5)),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
    ]))

    story = [
        Paragraph("UNITED STATES OF AMERICA", header_style),
        Paragraph("PASSPORT / PASSEPORT / PASAPORTE", sub_header),
        Spacer(1, 10),
        t,
        Spacer(1, 40),
        Paragraph("--------------------------------------------------------------------------------", sub_header),
        Spacer(1, 10),
    ]
    from app.engine.pipelines.identity import build_td3_mrz
    for line in build_td3_mrz("SMITH", "JOHN MICHAEL", "USA", "563927418", "USA", "850101", "M", "300101"):
        story.append(Paragraph(line.replace("<", "&lt;"), mrz_style))
    doc.build(story)

def generate_sample_invoice(file_path: str):
    """Generates a commercial business invoice PDF."""
    doc = SimpleDocTemplate(file_path, pagesize=letter, rightMargin=54, leftMargin=54, topMargin=54, bottomMargin=54)
    styles = getSampleStyleSheet()

    header_style = ParagraphStyle(
        'InvHeader',
        parent=styles['Heading1'],
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#0f172a")
    )
    body_style = ParagraphStyle(
        'InvBody',
        parent=styles['Normal'],
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#334155")
    )
    bold_style = ParagraphStyle(
        'InvBold',
        parent=styles['Normal'],
        fontSize=10,
        leading=14,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#0f172a")
    )

    items_data = [
        [Paragraph("Description", bold_style), Paragraph("Hours/Qty", bold_style), Paragraph("Rate", bold_style), Paragraph("Amount", bold_style)],
        [Paragraph("Cloud Architecture Advisory", body_style), Paragraph("20 hrs", body_style), Paragraph("$150.00", body_style), Paragraph("$3,000.00", body_style)],
        [Paragraph("Automated Pipeline Implementation", body_style), Paragraph("10 hrs", body_style), Paragraph("$125.00", body_style), Paragraph("$1,250.00", body_style)],
        ["", "", Paragraph("Subtotal:", bold_style), Paragraph("$4,250.00", bold_style)],
        ["", "", Paragraph("Tax (VAT 9%):", bold_style), Paragraph("$382.50", bold_style)],
        ["", "", Paragraph("Total Amount:", bold_style), Paragraph("$4,632.50", bold_style)],
    ]

    items_table = Table(items_data, colWidths=[240, 70, 90, 100])
    items_table.setStyle(TableStyle([
        ('LINEBELOW', (0, 0), (-1, 0), 1, colors.HexColor("#cbd5e1")),
        ('LINEBELOW', (0, 2), (-1, 2), 1, colors.HexColor("#e2e8f0")),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BACKGROUND', (2, 5), (3, 5), colors.HexColor("#f1f5f9")),
    ]))

    story = [
        Paragraph("INVOICE #INV-2026-8891", header_style),
        Spacer(1, 10),
        Paragraph("<b>FROM:</b> CloudScale Networks Inc.<br/>742 Evergreen Terrace, Suite 100<br/>Austin, TX 78701<br/>Tax ID: US-84920194", body_style),
        Spacer(1, 6),
        Paragraph("<b>BILL TO:</b> Meridian Enterprise Group<br/>1200 Market Street<br/>Philadelphia, PA 19107", body_style),
        Spacer(1, 10),
        Paragraph("<b>Date:</b> March 20, 2026 &nbsp;&nbsp;&nbsp;&nbsp; <b>Due Date:</b> April 19, 2026 &nbsp;&nbsp;&nbsp;&nbsp; <b>Currency:</b> USD", body_style),
        Spacer(1, 15),
        items_table,
        Spacer(1, 20),
        Paragraph("Payment Terms: Net 30. Wire transfer to routing #021000021, Account #889201928.", body_style)
    ]
    doc.build(story)

def create_all_samples():
    """Generates all standard sample documents."""
    contract_path = os.path.join(settings.SAMPLE_DOCS_DIR, "Master_Services_Agreement.pdf")
    passport_path = os.path.join(settings.SAMPLE_DOCS_DIR, "US_Passport_Verification.pdf")
    invoice_path = os.path.join(settings.SAMPLE_DOCS_DIR, "CloudScale_Invoice_8891.pdf")

    if not os.path.exists(contract_path):
        generate_sample_contract(contract_path)
    if not os.path.exists(passport_path):
        generate_sample_passport(passport_path)
    if not os.path.exists(invoice_path):
        generate_sample_invoice(invoice_path)

    return {
        "contract": contract_path,
        "passport": passport_path,
        "invoice": invoice_path
    }
