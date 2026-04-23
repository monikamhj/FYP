from django.db import models
from django.core.exceptions import ValidationError
import uuid
from django.utils import timezone
from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password, check_password
from datetime import timedelta
from django.conf import settings
import secrets

class Student(models.Model):
    student_id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=15)
    address = models.TextField()
    password = models.CharField(max_length=100)
    dob = models.DateField()
    course = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class Attendance(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)   # FIXED
    date = models.DateField()
    check_in = models.DateTimeField(null=True, blank=True)
    check_out = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.student.name} - {self.date}"


class PasswordReset(models.Model):
    user = models.ForeignKey(Student, on_delete=models.CASCADE)
    reset_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_when = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Password reset for {self.user.email} at {self.created_when}"


class PasswordResetOTP(models.Model):
    user = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="password_reset_otps")
    otp_hash = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    attempts = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"OTP reset for {self.user.email}"

    @classmethod
    def generate_for_user(cls, user):
        otp = f"{secrets.randbelow(1000000):06d}"
        expiry_minutes = getattr(settings, "PASSWORD_RESET_OTP_EXPIRY_MINUTES", 10)

        cls.objects.filter(user=user, is_used=False, expires_at__gt=timezone.now()).update(
            is_used=True
        )

        obj = cls.objects.create(
            user=user,
            otp_hash=make_password(otp),
            expires_at=timezone.now() + timedelta(minutes=expiry_minutes),
        )
        return obj, otp

    def is_expired(self):
        return timezone.now() > self.expires_at

    def verify_otp(self, raw_otp):
        if self.is_used or self.is_expired():
            return False
        return check_password(raw_otp, self.otp_hash)


class LeaveRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    # Added Leave Categories
    CATEGORY_CHOICES = [
        ('illness', 'Illness'),
        ('appointment', 'Appointment'),
        ('family', 'Family Matter'),
        ('other', 'Other'),
    ]

    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other') # New Field
    from_date = models.DateField()
    to_date = models.DateField()
    reason = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    submitted_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        """Custom validation to restrict leave requests to 2 per month."""
        # Check how many requests the student has already made this month
        current_month = self.from_date.month
        current_year = self.from_date.year
        
        leave_count = LeaveRequest.objects.filter(
            student=self.student,
            from_date__month=current_month,
            from_date__year=current_year
        ).count()

        # If this is a new request (not an edit) and count is already 2
        if not self.pk and leave_count >= 2:
            raise ValidationError(f"You have already submitted {leave_count} leave requests for this month. The limit is 2.")

    def save(self, *args, **kwargs):
        self.full_clean() # Ensures clean() is called before saving
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.student.name} ({self.category}) - {self.from_date}"

# AttendanceDeletionLog class - MOVED OUTSIDE LeaveRequest (FIXED INDENTATION)
class AttendanceDeletionLog(models.Model):
    """Log for tracking attendance deletions with remarks"""
    student = models.ForeignKey(Student, on_delete=models.SET_NULL, null=True)
    student_name = models.CharField(max_length=100, blank=True)
    student_code = models.CharField(max_length=50, blank=True)  # Changed from student_id to student_code
    date = models.DateField()
    remarks = models.TextField()
    deleted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL, 
        null=True
    )
    deleted_at = models.DateTimeField(auto_now_add=True)
    records_count = models.IntegerField(default=0)
    
    def save(self, *args, **kwargs):
        # Auto-fill student name and ID if student exists
        if self.student and not self.student_name:
            self.student_name = self.student.name
            self.student_code = self.student.student_id  # Changed here too
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"Deletion: {self.student_name} on {self.date}"
    
    class Meta:
        ordering = ['-deleted_at']
        verbose_name = "Attendance Deletion Log"
        verbose_name_plural = "Attendance Deletion Logs"