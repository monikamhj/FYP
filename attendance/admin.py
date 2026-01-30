from datetime import date

from django.contrib import admin
from django.shortcuts import render, get_object_or_404
from django.urls import path
from django.utils.html import format_html

from django.db.models import Min, Max
from import_export import resources
from import_export.admin import ExportMixin

from .models import Student, Attendance, PasswordReset, LeaveRequest


# -----------------------
# IMPORT-EXPORT RESOURCES
# -----------------------

class StudentResource(resources.ModelResource):
    class Meta:
        model = Student

class AttendanceResource(resources.ModelResource):
    class Meta:
        model = Attendance


# -----------------------
# INLINE ATTENDANCE FOR STUDENT
# -----------------------

class AttendanceInline(admin.TabularInline):
    model = Attendance
    extra = 0
    readonly_fields = ("date", "check_in", "check_out")
    can_delete = False


# -----------------------
# STUDENT ADMIN
# -----------------------

@admin.register(Student)
class StudentAdmin(ExportMixin, admin.ModelAdmin):
    resource_class = StudentResource
    list_display = ("student_id", "name", "email", "course", "dob")
    list_display_links = ("student_id", "name")
    search_fields = ("name", "student_id", "email")
    list_filter = ("course",)
    ordering = ("student_id",)
    inlines = [AttendanceInline]


# -----------------------
# ATTENDANCE ADMIN (daily summary + breaks)
# -----------------------

@admin.register(Attendance)
class AttendanceAdmin(ExportMixin, admin.ModelAdmin):
    resource_class = AttendanceResource

    # We will render our own summary table, so keep list_display simple
    list_display = ("student", "date", "check_in", "check_out")
    search_fields = ("student__name", "student__student_id")
    list_filter = ("date", "student")
    ordering = ("-date", "student__name")

    change_list_template = "attendance/admin/attendance_summary_changelist.html"

    def get_daily_summary(self):
        """Returns one row per (student, date) with first_in and last_out."""
        return (
            Attendance.objects
            .values("student__student_id", "student__name", "date")
            .annotate(
                first_in=Min("check_in"),
                last_out=Max("check_out"),
            )
            .order_by("-date", "student__name")
        )

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["daily_summary"] = self.get_daily_summary()
        return super().changelist_view(request, extra_context=extra_context)

    # ---------- breaks page for a single day ----------
    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "breaks/<int:student_id>/<slug:day>/",
                self.admin_site.admin_view(self.daily_breaks_view),
                name="attendance_daily_breaks",
            ),
        ]
        return custom + urls

    def daily_breaks_view(self, request, student_id, day):
        student = get_object_or_404(Student, student_id=student_id)
        target_date = date.fromisoformat(day)
        
        # Get all sessions for this student on this date
        sessions = (
            Attendance.objects
            .filter(student=student, date=target_date)
            .order_by("check_in")
        )
        
        # Compute breaks between consecutive sessions
        breaks = []
        for i in range(1, len(sessions)):
            prev = sessions[i-1]
            curr = sessions[i]
            if prev.check_out and curr.check_in:
                break_start = prev.check_out
                break_end = curr.check_in
                break_duration = break_end - break_start
                breaks.append({
                    'start': break_start,
                    'end': break_end,
                    'duration': str(break_duration),
                })
        
        context = dict(
            self.admin_site.each_context(request),
            student=student,
            date=target_date,
            breaks=breaks,
        )
        return render(
            request,
            "attendance/admin/daily_attendance_details.html",  # reuse your existing template
            context,
        )


# -----------------------
# PASSWORD RESET ADMIN
# -----------------------

@admin.register(PasswordReset)
class PasswordResetAdmin(admin.ModelAdmin):
    list_display = ["user", "reset_id", "created_when"]
    search_fields = ("user__email",)
    list_filter = ("created_when",)


# -----------------------
# LEAVE REQUEST ADMIN
# -----------------------

@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ("student", "from_date", "to_date", "reason", "status", "submitted_at")
    list_filter = ("status", "from_date", "to_date")
    search_fields = ("student__name", "reason")
