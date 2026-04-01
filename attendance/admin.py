# attendance/admin.py
from datetime import date, datetime
from django.contrib import admin, messages
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import path
from django.db.models import Min, Max
from django.utils import timezone  # Required for dashboard logic
from import_export import resources
from import_export.admin import ExportMixin

from .models import Student, Attendance, PasswordReset, LeaveRequest, AttendanceDeletionLog

# -----------------------
# CUSTOM ADMIN ACTIONS
# -----------------------
def delete_daily_attendance_action(modeladmin, request, queryset):
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
# CUSTOM FILTERS
# -----------------------
class FromDateFilter(admin.SimpleListFilter):
    title = 'From Date'
    parameter_name = 'from_date'
    template = 'attendance/admin/date_filter.html'

    def lookups(self, request, model_admin):
        return [('custom', 'Select date')]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(date__gte=self.value())
        return queryset

class ToDateFilter(admin.SimpleListFilter):
    title = 'To Date'
    parameter_name = 'to_date'
    template = 'attendance/admin/date_filter.html'

    def lookups(self, request, model_admin):
        return [('custom', 'Select date')]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(date__lte=self.value())
        return queryset

class StudentFilter(admin.SimpleListFilter):
    title = 'Students'
    parameter_name = 'student'

    def lookups(self, request, model_admin):
        students = Student.objects.filter(attendance__isnull=False).distinct().order_by('name')
        return [(s.student_id, f"{s.name} ({s.student_id})") for s in students]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(student__student_id=self.value())
        return queryset

# -----------------------
# ATTENDANCE ADMIN
# -----------------------
@admin.register(Attendance)
class AttendanceAdmin(ExportMixin, admin.ModelAdmin):
    resource_class = AttendanceResource
    list_display = ("student", "date", "check_in", "check_out")
    list_filter = [FromDateFilter, ToDateFilter, StudentFilter]
    ordering = ("-date", "student__name")
    actions = [delete_daily_attendance_action]
    
    # Default template for the Summary View
    change_list_template = "attendance/admin/attendance_summary_changelist.html"

    def changelist_view(self, request, extra_context=None):
        # 1. Get the filtered queryset using Django's built-in ChangeList
        cl = self.get_changelist_instance(request)
        filtered_query = cl.get_queryset(request)

        # 2. Check if this is a detailed view (specific student & date filters)
        is_detailed_view = ('student__student_id__exact' in request.GET or 'date__exact' in request.GET)
        
        # 3. If it's a detailed view, use the default template to show individual records
        if is_detailed_view:
            self.change_list_template = None  # Use default Django template
            extra_context = extra_context or {}
            extra_context.update({
                "current_from": request.GET.get('from_date', ''),
                "current_to": request.GET.get('to_date', ''),
                "current_student": request.GET.get('student', ''),
                "all_students": Student.objects.filter(attendance__isnull=False).distinct().order_by('name'),
            })
            return super().changelist_view(request, extra_context=extra_context)
        
        # 4. Otherwise, show the summary view (default behavior)
        self.change_list_template = "attendance/admin/attendance_summary_changelist.html"
        
        # 5. Aggregated Summary (First In / Last Out)
        daily_summary = (
            filtered_query
            .values("student__student_id", "student__name", "date")
            .annotate(
                first_in=Min("check_in"),
                last_out=Max("check_out"),
            )
            .order_by("-date", "student__name")
        )

        # 6. Prepare Context for the template
        extra_context = extra_context or {}
        extra_context.update({
            "daily_summary": daily_summary,
            "current_from": request.GET.get('from_date', ''),
            "current_to": request.GET.get('to_date', ''),
            "current_student": request.GET.get('student', ''),
            "all_students": Student.objects.filter(attendance__isnull=False).distinct().order_by('name'),
            "title": "Attendance Summary"
        })

        return super().changelist_view(request, extra_context=extra_context)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path("bulk-delete-confirm-page/", self.admin_site.admin_view(self.bulk_delete_confirm_page), name="attendance_bulk_delete_confirm_page"),
            path("bulk-delete-confirm/", self.admin_site.admin_view(self.bulk_delete_confirm), name="attendance_bulk_delete_confirm"),
            path("breaks/<int:student_id>/<slug:day>/", self.admin_site.admin_view(self.daily_breaks_view), name="attendance_daily_breaks"),
        ]
        return custom_urls + urls

    def bulk_delete_confirm_page(self, request):
        context = {
            'student_id': request.GET.get('student_id'),
            'student_name': request.GET.get('student_name', 'Unknown'),
            'date': request.GET.get('date'),
        }
        return render(request, 'attendance/admin/attendance_delete_confirmation.html', context)

    def bulk_delete_confirm(self, request):
        if request.method == 'POST':
            sid = request.POST.get('student_id')
            dt = request.POST.get('date')
            rem = request.POST.get('remarks')
            if sid and dt and rem:
                student = Student.objects.get(student_id=sid)
                recs = Attendance.objects.filter(student__student_id=sid, date=dt)
                count = recs.count()
                AttendanceDeletionLog.objects.create(
                    student=student, student_name=student.name, student_code=sid,
                    date=dt, remarks=rem, deleted_by=request.user, records_count=count
                )
                recs.delete()
                messages.success(request, f'Deleted {count} records for {dt}.')
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
# OTHER ADMIN REGISTRATIONS
# -----------------------
@admin.register(Student)
class StudentAdmin(ExportMixin, admin.ModelAdmin):
    resource_class = StudentResource
    list_display = ("student_id", "name", "email", "course")
    search_fields = ("name", "student_id")

@admin.register(AttendanceDeletionLog)
class AttendanceDeletionLogAdmin(admin.ModelAdmin):
    list_display = ('student_name', 'student_code', 'date', 'deleted_by', 'deleted_at')
    readonly_fields = ('student_name', 'student_code', 'date', 'remarks', 'deleted_by', 'deleted_at', 'records_count')

@admin.register(PasswordReset)
class PasswordResetAdmin(admin.ModelAdmin):
    list_display = ["user", "reset_id", "created_when"]

@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ("student", "category", "from_date", "to_date", "status")



# Save the original admin index function
admin_index_original = admin.site.index

def custom_admin_index(request, extra_context=None):
    # Calculate stats for the current day
    today = timezone.now().date()
    
    total_students = Student.objects.count()
    # Count unique students who checked in today
    today_present = Attendance.objects.filter(date=today).values('student').distinct().count()
    today_absent = max(0, total_students - today_present)

    # Add variables to the context (Names match your HTML template exactly)
    extra_context = extra_context or {}
    extra_context.update({
        'total_students': total_students,
        'today_present': today_present,
        'today_absent': today_absent,
    })

    # Return the original index but with our new calculated numbers
    return admin_index_original(request, extra_context)

# Inject our custom function into the admin site
admin.site.index = custom_admin_index