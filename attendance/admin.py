from datetime import date

from django.contrib import admin
from django.shortcuts import render, get_object_or_404
from django.urls import path
from django.utils.html import format_html

from django.db.models import Min, Max, F

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
# ATTENDANCE ADMIN (daily summary + details)
# -----------------------

@admin.register(Attendance)
class AttendanceAdmin(ExportMixin, admin.ModelAdmin):
    resource_class = AttendanceResource

    # use custom accessors but still list real model instances
    list_display = ("student", "date", "first_check_in", "last_check_out", "details_link")
    search_fields = ("student__name", "student__student_id")
    list_filter = ("date", "student")
    readonly_fields = ("student", "date", "check_in", "check_out")
    ordering = ("-date", "student__name")

    def get_queryset(self, request):
        """
        Return real Attendance instances but annotate each with
        the first check_in and last check_out for that student+date.
        There will still be multiple rows, but all rows for the same
        student+date share the same first/last times.
        """
        qs = super().get_queryset(request)
        return qs.annotate(
            first_in=Min("check_in"),
            last_out=Max("check_out"),
        )

    def first_check_in(self, obj):
        return obj.first_in
    first_check_in.short_description = "First check-in"

    def last_check_out(self, obj):
        return obj.last_out
    last_check_out.short_description = "Last check-out"

    # link to detail view to see all sessions for that student+date
    def details_link(self, obj):
        url = f"details/{obj.student.pk}/{obj.date.isoformat()}/"
        return format_html('<a href="{}">Details</a>', url)
    details_link.short_description = "Sessions"

    # add custom URL for the "Details" page
    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "details/<int:student_id>/<slug:day>/",
                self.admin_site.admin_view(self.daily_details_view),
                name="attendance_daily_details",
            ),
        ]
        return custom + urls

    # view that renders the sessions table
    def daily_details_view(self, request, student_id, day):
        student = get_object_or_404(Student, pk=student_id)
        target_date = date.fromisoformat(day)
        sessions = (
            Attendance.objects
            .filter(student=student, date=target_date)
            .order_by("check_in")
        )

        context = dict(
            self.admin_site.each_context(request),
            student=student,
            date=target_date,
            sessions=sessions,
        )
        return render(request, "admin/daily_attendance_details.html", context)



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
