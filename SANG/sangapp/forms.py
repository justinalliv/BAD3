from django import forms
from django.core.exceptions import ValidationError
from .models import Customer
import re


class CustomerRegistrationForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput(),
        required=True,
        label='Password'
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(),
        required=True,
        label='Confirm Password'
    )

    class Meta:
        model = Customer
        fields = ['first_name', 'last_name', 'email', 'phone_number']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def clean_first_name(self):
        first_name = self.cleaned_data.get('first_name', '').strip()
        if not first_name:
            raise ValidationError("Required fields must be filled in")
        return first_name

    def clean_last_name(self):
        last_name = self.cleaned_data.get('last_name', '').strip()
        if not last_name:
            raise ValidationError("Required fields must be filled in")
        return last_name

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip()
        
        if not email:
            raise ValidationError("Required fields must be filled in")
        
        # Validate email format (must contain @domain)
        if not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
            raise ValidationError("Please enter a valid email address")
        
        # Check if email already exists
        if Customer.objects.filter(email=email).exists():
            raise ValidationError("Email already registered")
        
        return email

    def clean_phone_number(self):
        phone_number = self.cleaned_data.get('phone_number', '').strip()
        
        if not phone_number:
            raise ValidationError("Required fields must be filled in")
        
        # Validate phone number format: must be 11 digits and start with 09-
        if not re.match(r'^09\d{9}$', phone_number.replace('-', '')):
            raise ValidationError("Phone Number must be 11 digits and start with 09-")
        
        # Check if phone number already exists
        if Customer.objects.filter(phone_number=phone_number).exists():
            raise ValidationError("Phone number already registered")
        
        return phone_number

    def clean_password(self):
        password = self.cleaned_data.get('password', '')
        
        if not password:
            raise ValidationError("Required fields must be filled in")
        
        return password

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password', '')
        confirm_password = cleaned_data.get('confirm_password', '')

        if password and confirm_password:
            if password != confirm_password:
                self.add_error('confirm_password', 'Password and Confirm Password do not match')

        return cleaned_data
