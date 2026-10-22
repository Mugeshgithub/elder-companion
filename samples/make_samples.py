"""Writes two FICTIONAL sample medical documents for demos and tests: a memory clinic consultation letter and a
prescription. Every page is watermarked SAMPLE. The clinic, doctor and patient are made up.

    python samples/make_samples.py                 # patient "Test Person"
    python samples/make_samples.py --name Mugesh   # use your own demo name
"""
import argparse
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

CLINIC = "Example University Hospital, Memory Clinic"
ADDRESS = "1 Example Street, 75000 Paris (fictional)  |  Tel 01 00 00 00 00"
DOCTOR = "Dr Claire Fontaine, Consultant Neurologist"

ss = getSampleStyleSheet()
body = ParagraphStyle("body", parent=ss["Normal"], fontName="Helvetica", fontSize=10.5, leading=15, spaceAfter=6)
h = ParagraphStyle("h", parent=body, fontName="Helvetica-Bold", fontSize=11.5, spaceBefore=8, spaceAfter=4, textColor=colors.HexColor("#1F3A5F"))
title = ParagraphStyle("title", parent=body, fontName="Helvetica-Bold", fontSize=15, spaceAfter=2)
small = ParagraphStyle("small", parent=body, fontSize=8.5, leading=11, textColor=colors.HexColor("#555555"))


def page(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(colors.HexColor("#1F3A5F"))
    canvas.setFont("Helvetica-Bold", 11)
    canvas.drawString(20 * mm, 280 * mm, CLINIC)
    canvas.setFont("Helvetica", 8.5)
    canvas.setFillColor(colors.HexColor("#555555"))
    canvas.drawString(20 * mm, 275.5 * mm, ADDRESS)
    canvas.setStrokeColor(colors.HexColor("#1F3A5F"))
    canvas.line(20 * mm, 273 * mm, 190 * mm, 273 * mm)
    # watermark
    canvas.setFillColor(colors.Color(0.8, 0.1, 0.1, alpha=0.10))
    canvas.setFont("Helvetica-Bold", 62)
    canvas.translate(105 * mm, 150 * mm)
    canvas.rotate(35)
    canvas.drawCentredString(0, 0, "SAMPLE - FICTIONAL")
    canvas.restoreState()
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#777777"))
    canvas.drawString(20 * mm, 12 * mm, "Fictional document for software demonstration. Not a real patient, clinic or prescription.")
    canvas.drawRightString(190 * mm, 12 * mm, f"Page {doc.page}")
    canvas.restoreState()


def letter(path: Path, name: str):
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=34 * mm, bottomMargin=22 * mm,
                            title="Memory clinic consultation letter (sample)", author=DOCTOR)
    s = []
    s.append(Paragraph("CONSULTATION LETTER", title))
    s.append(Paragraph("Date of letter: 14 October 2026", body))
    s.append(Table([
        ["Patient:", name, "Date of birth:", "14 March 1947 (fictional)"],
        ["Referred by:", "Dr Paul Garnier, General Practitioner", "Seen on:", "12 October 2026"],
    ], colWidths=[24 * mm, 66 * mm, 28 * mm, 52 * mm], style=TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 9.5), ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 9.5), ("FONT", (2, 0), (2, -1), "Helvetica-Bold", 9.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3), ("TOPPADDING", (0, 0), (-1, -1), 3)])))
    s.append(Spacer(1, 6))
    s.append(Paragraph(f"Dear Dr Garnier,", body))
    s.append(Paragraph(f"Thank you for referring {name}, who attended the Memory Clinic with a family member on 12 October 2026.", body))
    s.append(Paragraph("Reason for referral", h))
    s.append(Paragraph("Progressive difficulty over about two years with remembering recent events, repeating questions, and misplacing "
                       "everyday objects. Their family reports that they sometimes become anxious in the late afternoon and evening.", body))
    s.append(Paragraph("Assessment", h))
    s.append(Paragraph("Mini-Mental State Examination 22/30. Montreal Cognitive Assessment 19/30, with the main losses in delayed recall and orientation "
                       "to date. Mood screen: mild low mood, no thoughts of self-harm. Examination was otherwise unremarkable.", body))
    s.append(Paragraph("Investigations", h))
    s.append(Paragraph("MRI brain (30 September 2026): mild generalised atrophy with more marked hippocampal volume loss; no significant small-vessel "
                       "disease and no space-occupying lesion. Blood tests (28 September 2026): vitamin B12, folate, thyroid function, calcium and "
                       "kidney function all within normal limits.", body))
    s.append(PageBreak())
    s.append(Paragraph("Impression", h))
    s.append(Paragraph("Findings are consistent with probable Alzheimer's disease, mild stage. I discussed this with the patient and their family, "
                       "and explained that the treatment aims to support memory and daily function. It does not cure the condition.", body))
    s.append(Paragraph("Plan", h))
    s.append(Paragraph("1. Start donepezil 5 mg once a day, taken in the evening, for 4 weeks. If it is well tolerated, increase to donepezil 10 mg "
                       "once a day in the evening. Common side effects include nausea, loose stools, vivid dreams and reduced appetite; "
                       "please let us know if these are troublesome.", body))
    s.append(Paragraph("2. Continue vitamin D3 1000 IU once a day with a meal, as prescribed by the GP.", body))
    s.append(Paragraph("3. A family member should supervise medicines and keep a written list of what is taken and when.", body))
    s.append(Paragraph("4. Please avoid driving until the driving assessment has been completed.", body))
    s.append(Paragraph("5. Report any fall, new confusion, fainting, a very slow pulse, or repeated vomiting to the GP or the clinic the same day.", body))
    s.append(Paragraph("Follow-up", h))
    s.append(Paragraph("Review at the Memory Clinic on 14 January 2027 at 10:30, second floor, with Dr Fontaine. An occupational therapy home "
                       "assessment will be arranged and the team will contact the family directly.", body))
    s.append(Spacer(1, 10))
    s.append(Paragraph("Yours sincerely,", body))
    s.append(Spacer(1, 16))
    s.append(Paragraph(f"<b>{DOCTOR}</b><br/>Memory Clinic, Example University Hospital<br/>Staff ID: 000000 (fictional)", body))
    s.append(Paragraph("Copy to: the patient and their family.", small))
    doc.build(s, onFirstPage=page, onLaterPages=page)


def prescription(path: Path, name: str):
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=34 * mm, bottomMargin=22 * mm,
                            title="Prescription (sample)", author=DOCTOR)
    s = [Paragraph("PRESCRIPTION", title), Paragraph("Date: 14 October 2026", body)]
    s.append(Table([
        ["Patient:", name, "Date of birth:", "14 March 1947 (fictional)"],
        ["Prescriber:", DOCTOR, "Staff ID:", "000000 (fictional)"],
    ], colWidths=[24 * mm, 66 * mm, 28 * mm, 52 * mm], style=TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 9.5), ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 9.5), ("FONT", (2, 0), (2, -1), "Helvetica-Bold", 9.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3), ("TOPPADDING", (0, 0), (-1, -1), 3)])))
    s.append(Spacer(1, 10))
    rows = [
        ["Medicine", "How to take it", "Duration"],
        ["Donepezil 5 mg tablets", "1 tablet once a day, in the evening", "28 days (1 box of 28)"],
        ["Donepezil 10 mg tablets", "1 tablet once a day, in the evening. Start only after 4 weeks of the 5 mg dose, "
                                    "as directed by the Memory Clinic", "Prescribed after review"],
        ["Vitamin D3 (cholecalciferol) 1000 IU", "1 capsule once a day with a meal", "3 months"],
    ]
    t = Table([[Paragraph(c, body if i else ParagraphStyle("hd", parent=body, fontName="Helvetica-Bold")) for c in r] for i, r in enumerate(rows)],
              colWidths=[52 * mm, 78 * mm, 40 * mm])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#999999")), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EEF5")),
                           ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    s.append(t)
    s.append(Spacer(1, 12))
    s.append(Paragraph("Instructions", h))
    s.append(Paragraph("Take donepezil in the evening, with or after food. Do not stop it suddenly without speaking to the clinic. "
                       "A family member should keep the medicines and give them each day. Bring all medicines to the next appointment.", body))
    s.append(Paragraph("Repeat: none. Next review: Memory Clinic, 14 January 2027, 10:30.", body))
    s.append(Spacer(1, 18))
    s.append(Paragraph(f"Signed: <b>{DOCTOR}</b> (fictional)", body))
    doc.build(s, onFirstPage=page, onLaterPages=page)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="Test Person")
    out = Path(__file__).parent
    a = ap.parse_args()
    letter(out / "sample-memory-clinic-letter.pdf", a.name)
    prescription(out / "sample-prescription.pdf", a.name)
    print("wrote", out / "sample-memory-clinic-letter.pdf", "and", out / "sample-prescription.pdf")
