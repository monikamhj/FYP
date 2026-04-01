from django import forms
import re

from .models import LeaveRequest, Student


class StudentForm(forms.ModelForm):
    """
    Student registration form.

    Note: this file previously defined StudentForm twice, and the second definition
    overwrote the first (silently dropping validations). This single definition
    keeps all validations and adds confirm_password support.
    """

    password = forms.CharField(widget=forms.PasswordInput(), min_length=8)
    confirm_password = forms.CharField(widget=forms.PasswordInput(), min_length=8)

    class Meta:
        model = Student
        exclude = ["student_id"]
        widgets = {
            "password": forms.PasswordInput(),
        }

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if Student.objects.filter(email=email).exists():
            raise forms.ValidationError("This email is already in use.")
        return email

    def clean_phone_number(self):
        phone_number = self.cleaned_data.get("phone_number")
        # Basic check for digits and length (+ optional leading '+').
        if not re.match(r"^\+?\d{10,15}$", phone_number):
            raise forms.ValidationError("Enter a valid phone number.")
        return phone_number

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")

        if password and confirm_password and password != confirm_password:
            self.add_error("confirm_password", "Passwords do not match.")

        return cleaned_data

class LeaveRequestForm(forms.ModelForm):
    class Meta:
        model = LeaveRequest
        fields = ['category', 'from_date', 'to_date', 'reason']
        widgets = {
            'category': forms.Select(attrs={'class': 'form-select'}),
            'from_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-input'}),
            'to_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-input'}),
            'reason': forms.Textarea(attrs={'class': 'form-textarea', 'placeholder': 'Reason...'}),
        }