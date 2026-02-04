from django import forms
from .models import Student
from .models import LeaveRequest
import re

class StudentForm(forms.ModelForm):
    class Meta:
        model = Student
        exclude = ['student_id']

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if Student.objects.filter(email=email).exists():
            raise forms.ValidationError("This email is already in use.")
        return email

    def clean_phone_number(self):
        phone_number = self.cleaned_data.get('phone_number')
        # Ensure phone number is valid (basic check for digits and length)
        if not re.match(r'^\+?\d{10,15}$', phone_number):
            raise forms.ValidationError("Enter a valid phone number.")
        return phone_number

    password = forms.CharField(widget=forms.PasswordInput(), min_length=8)

class StudentForm(forms.ModelForm):
    confirm_password = forms.CharField(widget=forms.PasswordInput(), min_length=8)

    class Meta:
        model = Student
        exclude = ['student_id']
        widgets = {
            'password': forms.PasswordInput(),
        }

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")

        if password and confirm_password and password != confirm_password:
            self.add_error('confirm_password', "Passwords do not match.")

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