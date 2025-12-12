from django.contrib import admin
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
    readonly_fields = ('date', 'check_in', 'check_out')
    can_delete = False


# -----------------------
# STUDENT ADMIN
# -----------------------

@admin.register(Student)
class StudentAdmin(ExportMixin, admin.ModelAdmin):
    resource_class = StudentResource
    list_display = ('student_id', 'name', 'email', 'course', 'dob')
    list_display_links = ('student_id', 'name')
    search_fields = ('name', 'student_id', 'email')
    list_filter = ('course',)
    ordering = ('student_id',)
    inlines = [AttendanceInline]


# -----------------------
# ATTENDANCE ADMIN
# -----------------------

@admin.register(Attendance)
class AttendanceAdmin(ExportMixin, admin.ModelAdmin):
    resource_class = AttendanceResource
    list_display = ('student', 'date', 'check_in', 'check_out')
    search_fields = ('student__name', 'student__student_id')
    list_filter = ('date',)
    readonly_fields = ('student', 'date', 'check_in', 'check_out')


# -----------------------
# PASSWORD RESET ADMIN
# -----------------------

@admin.register(PasswordReset)
class PasswordResetAdmin(admin.ModelAdmin):
    list_display = ['user', 'reset_id', 'created_when']
    search_fields = ('user__email',)
    list_filter = ('created_when',)


# -----------------------
# LEAVE REQUEST ADMIN
# -----------------------

@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ('student', 'from_date', 'to_date', 'reason', 'status', 'submitted_at')
    list_filter = ('status', 'from_date', 'to_date')
    search_fields = ('student__name', 'reason')
