from io import BytesIO
from django.http import HttpResponse  # ✅ Add this
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet


def export_attendance_pdf(request, student, attendance_status, month, year):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=60, bottomMargin=40)

    elements = []
    styles = getSampleStyleSheet()

    # Header
    title = Paragraph(f"<b>Attendance Report - {student.name}</b>", styles['Title'])
    month_year = Paragraph(f"<b>Month:</b> {month} &nbsp;&nbsp;&nbsp; <b>Year:</b> {year}", styles['Normal'])
    elements.extend([title, month_year, Spacer(1, 12)])

    # Table data
    data = [['Date', 'Status']] + [[str(record['date']), record['status']] for record in attendance_status]

    # Table styling
    table = Table(data, colWidths=[200, 100])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
    ]))
    elements.append(table)

    # Totals
    total_present = sum(1 for r in attendance_status if r['status'] == 'Present')
    total_absent = sum(1 for r in attendance_status if r['status'] == 'Absent')
    summary = Paragraph(f"<br/><b>Total Present:</b> {total_present} &nbsp;&nbsp;&nbsp;&nbsp; <b>Total Absent:</b> {total_absent}", styles['Normal'])
    elements.append(summary)

    # Build PDF
    doc.build(elements)
    buffer.seek(0)
    return HttpResponse(buffer, content_type='application/pdf')
