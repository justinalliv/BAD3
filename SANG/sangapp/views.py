from django.shortcuts import render, redirect
from django.contrib.auth.hashers import make_password
from django.contrib import messages
from .models import Customer
from .forms import CustomerRegistrationForm


def hello_world(request):
    return render(request, 'hello_world.html')


def home(request):
    """Display customer home page (UC37)."""
    return render(request, 'UC37: View_Customer_Home_Page.html')


def login(request):
    """Login page placeholder - TODO: implement full login functionality."""
    return render(request, 'login.html')


def register(request):
    """Handle customer registration with validation."""
    if request.method == 'POST':
        form = CustomerRegistrationForm(request.POST)
        
        # Check for existing email (for extension 3.6)
        email = request.POST.get('email', '').strip()
        if email and Customer.objects.filter(email=email).exists():
            return render(request, 'UC01: Register_Customer_Account.html', {
                'form': form,
                'email_exists': True,
            })
        
        # Check for existing phone number (for extension 3.5)
        phone_number = request.POST.get('phone_number', '').strip()
        if phone_number and Customer.objects.filter(phone_number=phone_number).exists():
            return render(request, 'UC01: Register_Customer_Account.html', {
                'form': form,
                'phone_exists': True,
            })
        
        if form.is_valid():
            # Create new customer account
            customer = form.save(commit=False)
            customer.password = make_password(form.cleaned_data['password'])
            customer.save()
            
            # Store success message and redirect to success page
            return render(request, 'UC01: Register_Customer_Account.html', {
                'success': True,
                'customer_name': f"{customer.first_name} {customer.last_name}"
            })
        else:
            # Form has validation errors, re-render with errors
            return render(request, 'UC01: Register_Customer_Account.html', {'form': form})
    else:
        # GET request - display empty form
        form = CustomerRegistrationForm()
    
    return render(request, 'UC01: Register_Customer_Account.html', {'form': form})


