from django.shortcuts import render, redirect
from django.contrib import messages
from .models import Customer
from .forms import CustomerRegistrationForm

def home(request):
    """Public home page."""
    return render(request, 'home.html')


def customer_home(request):
    """Authenticated customer home page/dashboard."""
    # Check if user is logged in
    if 'customer_id' not in request.session:
        return redirect('login')
    
    return render(request, 'customer_home.html')


def login(request):
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')

        customer = Customer.objects.filter(email=email).only('id', 'password', 'first_name', 'last_name').first()
        if customer and customer.password == password:
            request.session['customer_id'] = customer.id
            request.session['customer_name'] = f"{customer.first_name} {customer.last_name}"
            return redirect('customer_home')

        messages.error(request, 'Invalid email or password.')
        return render(request, 'login.html', status=401)
    
    return render(request, 'login.html')


def signup(request):
    """Handle customer registration with validation."""
    if request.method == 'POST':
        form = CustomerRegistrationForm(request.POST)
        
        # Check for existing email (for extension 3.6)
        email = request.POST.get('email', '').strip()
        if email and Customer.objects.filter(email=email).exists():
            return render(request, 'signup.html', {
                'form': form,
                'email_exists': True,
            })
        
        # Check for existing phone number (for extension 3.5)
        phone_number = request.POST.get('phone_number', '').strip()
        if phone_number and Customer.objects.filter(phone_number=phone_number).exists():
            return render(request, 'signup.html', {
                'form': form,
                'phone_exists': True,
            })
        
        if form.is_valid():
            # Create new customer account
            customer = form.save(commit=False)
            customer.password = form.cleaned_data['password']
            customer.save()
            
            # Auto-login after registration
            request.session['customer_id'] = customer.id
            request.session['customer_name'] = f"{customer.first_name} {customer.last_name}"
            
            # Store success message and redirect to success page
            return render(request, 'signup.html', {
                'success': True,
                'customer_name': f"{customer.first_name} {customer.last_name}"
            })
        else:
            # Form has validation errors, re-render with errors
            return render(request, 'signup.html', {'form': form})
    else:
        # GET request - display empty form
        form = CustomerRegistrationForm()
    
    return render(request, 'signup.html', {'form': form})


def profile(request):
    """Display customer profile page."""
    # Check if user is logged in
    if 'customer_id' not in request.session:
        return redirect('login')
    
    customer = Customer.objects.get(id=request.session['customer_id'])
    return render(request, 'profile.html', {'customer': customer})


def edit_profile(request):
    """Handle customer profile editing."""
    # Check if user is logged in
    if 'customer_id' not in request.session:
        return redirect('login')
    
    customer = Customer.objects.get(id=request.session['customer_id'])
    
    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        phone_number = request.POST.get('phone_number', '').strip()
        
        # Validate phone number format
        import re
        if not re.match(r'^09\d{9}$', phone_number):
            return render(request, 'edit_profile.html', {
                'customer': customer,
                'error_phone': 'Phone Number must be 11 digits and start with 09-'
            })
        
        # Check if phone number already exists (excluding current customer)
        if Customer.objects.filter(phone_number=phone_number).exclude(id=customer.id).exists():
            return render(request, 'edit_profile.html', {
                'customer': customer,
                'error_phone': 'Phone number has already been registered. Please input a different phone number.'
            })
        
        # Update customer profile
        customer.first_name = first_name
        customer.last_name = last_name
        customer.phone_number = phone_number
        customer.save()
        
        # Update session name
        request.session['customer_name'] = f"{first_name} {last_name}"
        
        return redirect('profile')
    
    return render(request, 'edit_profile.html', {'customer': customer})
