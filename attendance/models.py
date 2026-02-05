from django.db import models
from django.core.exceptions import ValidationError
import uuid
from django.utils import timezone

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
