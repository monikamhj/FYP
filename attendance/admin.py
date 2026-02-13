# attendance/admin.py
from datetime import date

from django.contrib import admin, messages
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import path
from django.utils.html import format_html
from django.http import HttpResponseRedirect

from django.db.models import Min, Max
from import_export import resources
from import_export.admin import ExportMixin

from .models import Student, Attendance, PasswordReset, LeaveRequest, AttendanceDeletionLog


# -----------------------
# CUSTOM ADMIN ACTIONS
# -----------------------

def delete_daily_attendance_action(modeladmin, request, queryset):
    """Admin action to delete selected attendance records"""
    count = queryset.count()
    queryset.delete()
    messages.success(request, f"Successfully deleted {count} attendance records.")

delete_daily_attendance_action.short_description = "Delete selected attendance records"


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
# ATTENDANCE ADMIN (daily summary + breaks + bulk delete)
# -----------------------

@admin.register(Attendance)
class AttendanceAdmin(ExportMixin, admin.ModelAdmin):
    resource_class = AttendanceResource

    # We will render our own summary table, so keep list_display simple
    list_display = ("student", "date", "check_in", "check_out")
    search_fields = ("student__name", "student__student_id")
    list_filter = ("date", "student")
    ordering = ("-date", "student__name")
    actions = [delete_daily_attendance_action]

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
        # Check if it's a delete request from the summary page
        if 'delete_all' in request.GET and request.GET.get('delete_all') == '1':
            student_id = request.GET.get('student__student_id__exact')
            date_str = request.GET.get('date__exact')
            
            if student_id and date_str:
                # Delete all attendance for that student on that date
                records = Attendance.objects.filter(
                    student__student_id=student_id,
                    date=date_str
                )
                count = records.count()
                records.delete()
                messages.success(request, f"Successfully deleted {count} attendance records for {date_str}")
                
                # Redirect to remove the query parameters
                return redirect('admin:attendance_attendance_changelist')
        
        # Add daily summary to context
        extra_context = extra_context or {}
        extra_context["daily_summary"] = self.get_daily_summary()
        return super().changelist_view(request, extra_context=extra_context)

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "bulk-delete-confirm-page/",
                self.admin_site.admin_view(self.bulk_delete_confirm_page),
                name="attendance_bulk_delete_confirm_page",
            ),
            path(
                "bulk-delete-confirm/",
                self.admin_site.admin_view(self.bulk_delete_confirm),
                name="attendance_bulk_delete_confirm",
            ),
            path(
                "breaks/<int:student_id>/<slug:day>/",
                self.admin_site.admin_view(self.daily_breaks_view),
                name="attendance_daily_breaks",
            ),
        ]
        return custom + urls

    def bulk_delete_confirm_page(self, request):
        """Show confirmation page with remarks field"""
        student_id = request.GET.get('student_id')
        date_str = request.GET.get('date')
        student_name = request.GET.get('student_name', 'Unknown')
        
        context = {
            'student_id': student_id,
            'student_name': student_name,
            'date': date_str,
        }
        return render(request, 'attendance/admin/attendance_delete_confirmation.html', context)

    def bulk_delete_confirm(self, request):
        """Handle delete with remarks and save to log"""
        if request.method == 'POST':
            student_id = request.POST.get('student_id')
            date_str = request.POST.get('date')
            student_name = request.POST.get('student_name')
            remarks = request.POST.get('remarks')
            
            if student_id and date_str and remarks:
                # Get student and records before deletion
                try:
                    student = Student.objects.get(student_id=student_id)
                    records = Attendance.objects.filter(
                        student__student_id=student_id,
                        date=date_str
                    )
                    count = records.count()
                    
                    # Save to deletion log BEFORE deleting
                    AttendanceDeletionLog.objects.create(
                        student=student,
                        student_name=student_name,
                        student_code=student_id,  # Changed from student_id to student_code
                        date=date_str,
                        remarks=remarks,
                        deleted_by=request.user,
                        records_count=count
                        )
                    
                    # Now delete the records
                    records.delete()
                    
                    # Show success message with remarks
                    messages.success(request, f'Deleted {count} records for {student_name} on {date_str}. Remarks: {remarks}')
                except Student.DoesNotExist:
                    messages.error(request, 'Student not found')
            else:
                messages.error(request, 'Remarks are required')
                
        return redirect('admin:attendance_attendance_changelist')

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
            "attendance/admin/daily_attendance_details.html",
            context,
        )

    def get_form(self, request, obj=None, **kwargs):
        """Pre-fill form with student and date from URL parameters"""
        form = super().get_form(request, obj, **kwargs)
        
        # If it's an add form (obj is None), check for URL parameters
        if obj is None and request.method == 'GET':
            student_id = request.GET.get('student')
            date_str = request.GET.get('initial-date')
            
            if student_id:
                try:
                    student = Student.objects.get(student_id=student_id)
                    form.base_fields['student'].initial = student
                except Student.DoesNotExist:
                    pass
            
            if date_str:
                form.base_fields['date'].initial = date_str
        
        return form


# -----------------------
# ATTENDANCE DELETION LOG ADMIN (OPTION 3)
# -----------------------

@admin.register(AttendanceDeletionLog)
class AttendanceDeletionLogAdmin(admin.ModelAdmin):
    list_display = ('student_name', 'student_code', 'date', 'deleted_by', 'deleted_at', 'records_count')
    list_filter = ('deleted_at', 'date', 'deleted_by')
    search_fields = ('student_name', 'student_code', 'remarks')
    readonly_fields = ('student_name', 'student_id', 'date', 'remarks', 'deleted_by', 'deleted_at', 'records_count')
    date_hierarchy = 'deleted_at'
    
    def has_add_permission(self, request):
        return False  # Don't allow manual adding
    
    def has_change_permission(self, request, obj=None):
        return False  # Don't allow editing
    
    def has_delete_permission(self, request, obj=None):
        return False  # Don't allow deletion of logs


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
    # Added 'category' after student for better visibility
    list_display = ("student", "category", "from_date", "to_date", "reason", "status", "submitted_at")
    
    # Added 'category' to filters to easily find all "Illness" or "Family Matter" requests
    list_filter = ("status", "category", "from_date", "to_date")
    
    # Kept your existing search fields
    search_fields = ("student__name", "reason")