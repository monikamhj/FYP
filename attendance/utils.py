from io import BytesIO
from datetime import date, timedelta
import calendar

from django.db.models import Min, Max
from django.http import HttpResponse
from django.utils import timezone
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet

NEPAL_UTC_OFFSET = timedelta(hours=5, minutes=45)
LATE_CHECK_IN_HOUR = 10
LATE_CHECK_IN_MINUTE = 0

PUBLIC_HOLIDAYS = {
    date(2026, 1, 11): "Prithvi Jayanti",
    date(2026, 1, 14): "Maghe Sankranti",
    date(2026, 1, 30): "Martyrs' Day",
    date(2026, 2, 15): "Maha Shivaratri",
    date(2026, 2, 18): "Gyalpo Lhosar",
    date(2026, 2, 19): "Prajatantra Diwas",
    date(2026, 3, 2): "Holi (Hilly Region)",
    date(2026, 3, 3): "Holi (Terai Region)",
    date(2026, 3, 8): "Women's Day",
    date(2026, 4, 14): "Nepali New Year",
    date(2026, 5, 1): "Labour Day / Buddha Jayanti",
    date(2026, 5, 29): "Republic Day",
    date(2026, 9, 19): "Constitution Day",
    date(2026, 10, 21): "Dashain (Vijaya Dashami)",
    date(2026, 11, 11): "Bhai Tika (Tihar)",
}


def _to_nepal_time(utc_dt):
    if not utc_dt:
        return None
    return utc_dt + NEPAL_UTC_OFFSET


def _is_late_check_in(nepal_dt):
    if not nepal_dt:
        return False
    if nepal_dt.hour > LATE_CHECK_IN_HOUR:
        return True
    return nepal_dt.hour == LATE_CHECK_IN_HOUR and nepal_dt.minute > LATE_CHECK_IN_MINUTE


def build_monthly_attendance_status(student, month=None, year=None):
    """
    Build per-day attendance rows using the same rules as the attendance report page.
    Returns summary counts and the full day-by-day list.
    """
    from .models import Attendance, LeaveRequest

    today = timezone.localdate()
    month = month or today.month
    year = year or today.year

    _, num_days = calendar.monthrange(year, month)
    last_day_date = date(year, month, num_days)
    limit_date = min(last_day_date, today)
    all_dates = [date(year, month, day) for day in range(1, limit_date.day + 1)]

    attendance_agg = (
        Attendance.objects.filter(student=student, date__year=year, date__month=month)
        .values("date")
        .annotate(first_check_in=Min("check_in"), last_check_out=Max("check_out"))
    )
    attendance_map = {
        rec["date"]: {
            "check_in": rec["first_check_in"],
            "check_out": rec["last_check_out"],
        }
        for rec in attendance_agg
    }

    leaves = LeaveRequest.objects.filter(
        student=student,
        from_date__lte=last_day_date,
        to_date__gte=date(year, month, 1),
    )

    attendance_status = []
    late_arrivals = 0

    for d in all_dates:
        record = attendance_map.get(d)
        on_leave = leaves.filter(from_date__lte=d, to_date__gte=d).exists()
        holiday_name = PUBLIC_HOLIDAYS.get(d)
        is_saturday = d.weekday() == 5

        if is_saturday:
            status = "Weekend"
        elif holiday_name:
            status = f"Holiday ({holiday_name})"
        elif on_leave:
            status = "On Leave"
        elif record:
            status = "Present"
        else:
            status = "Absent"

        check_in_str = "—"
        check_out_str = "—"
        if record and record["check_in"]:
            nepal_in = _to_nepal_time(record["check_in"])
            check_in_str = nepal_in.strftime("%H:%M:%S")
            if status == "Present" and _is_late_check_in(nepal_in):
                late_arrivals += 1
        if record and record["check_out"]:
            check_out_str = _to_nepal_time(record["check_out"]).strftime("%H:%M:%S")

        attendance_status.append(
            {
                "date": d.strftime("%Y-%m-%d"),
                "date_obj": d,
                "day": d.strftime("%A"),
                "status": status,
                "check_in": check_in_str,
                "check_out": check_out_str,
            }
        )

    total_present = sum(1 for r in attendance_status if r["status"] == "Present")
    total_absent = sum(1 for r in attendance_status if r["status"] == "Absent")
    total_leave = sum(1 for r in attendance_status if r["status"] == "On Leave")
    working_days = total_present + total_absent
    attendance_rate = round((total_present / working_days) * 100) if working_days else 0

    return {
        "attendance_status": attendance_status,
        "total_present": total_present,
        "total_absent": total_absent,
        "total_leave": total_leave,
        "late_arrivals": late_arrivals,
        "attendance_rate": attendance_rate,
        "working_days": working_days,
        "month": month,
        "year": year,
    }


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
