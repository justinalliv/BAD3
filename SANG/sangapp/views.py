from django.shortcuts import render, redirect
from django.contrib import messages
from .models import Customer, Property
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


def pending_payment(request):
    """Display pending payments page (UC 05)."""
    # Check if user is logged in
    if 'customer_id' not in request.session:
        return redirect('login')
    
    # For now, show empty pending payments
    # TODO: Fetch actual pending payments from database
    return render(request, 'pending_payment.html')


def payment_instructions(request):
    """Display payment instructions page (UC 05)."""
    # Check if user is logged in
    if 'customer_id' not in request.session:
        return redirect('login')
    
    return render(request, 'payment_instructions.html')


def submit_payment_proof(request):
    """Handle payment proof submission (UC 05)."""
    # Check if user is logged in
    if 'customer_id' not in request.session:
        return redirect('login')
    
    if request.method == 'POST':
        payment_type = request.POST.get('payment_type', '').strip()
        bank_used = request.POST.get('bank_used', '').strip()
        reference_number = request.POST.get('reference_number', '').strip()
        amount_paid = request.POST.get('amount_paid', '').strip()
        proof_file = request.FILES.get('proof_file')
        
        # Validate all fields
        errors = {}
        if not payment_type:
            errors['payment_type'] = 'Payment type is required'
        if not bank_used:
            errors['bank_used'] = 'Bank is required'
        if not reference_number:
            errors['reference_number'] = 'Reference number is required'
        if not amount_paid:
            errors['amount_paid'] = 'Amount paid is required'
        if not proof_file:
            errors['file'] = 'Proof of payment is required'
        
        # Validate file format and size
        if proof_file:
            allowed_extensions = ['jpg', 'jpeg', 'png', 'pdf']
            max_size = 5 * 1024 * 1024  # 5 MB
            
            file_ext = proof_file.name.split('.')[-1].lower()
            if file_ext not in allowed_extensions:
                errors['file'] = 'File format not allowed. Only JPG, PNG, or PDF are accepted.'
            
            if proof_file.size > max_size:
                errors['file'] = 'File size exceeds 5 MB limit.'
        
        if errors:
            return render(request, 'submit_payment_proof.html', {'errors': errors})
        
        # TODO: Save payment proof to database
        # For now, payment submission is successful
        return render(request, 'submit_payment_proof.html', {'success': True})
    
    return render(request, 'submit_payment_proof.html')


def property_list(request):
    """Display list of registered properties for the customer (UC 06)."""
    # Check if user is logged in
    if 'customer_id' not in request.session:
        return redirect('login')
    
    customer = Customer.objects.get(id=request.session['customer_id'])
    properties = Property.objects.filter(customer=customer)
    
    return render(request, 'property_list.html', {
        'customer': customer,
        'properties': properties
    })


def register_property(request):
    """Handle property registration (UC 06)."""
    # Check if user is logged in
    if 'customer_id' not in request.session:
        return redirect('login')
    
    customer = Customer.objects.get(id=request.session['customer_id'])
    
    if request.method == 'POST':
        property_name = request.POST.get('property_name', '').strip()
        street_number = request.POST.get('street_number', '').strip()
        street = request.POST.get('street', '').strip()
        city = request.POST.get('city', '').strip()
        province = request.POST.get('province', '').strip()
        country = request.POST.get('country', '').strip()
        zip_code = request.POST.get('zip_code', '').strip()
        property_type = request.POST.get('property_type', '').strip()
        floor_area = request.POST.get('floor_area', '').strip()
        
        # Validate all fields are filled
        errors = {}
        if not property_name:
            errors['property_name'] = 'Property name is required'
        if not street_number:
            errors['street_number'] = 'Street number is required'
        if not street:
            errors['street'] = 'Street is required'
        if not city:
            errors['city'] = 'City is required'
        if not province:
            errors['province'] = 'Province is required'
        if not country:
            errors['country'] = 'Country is required'
        if not zip_code:
            errors['zip_code'] = 'ZIP code is required'
        if not property_type:
            errors['property_type'] = 'Property type is required'
        if not floor_area:
            errors['floor_area'] = 'Floor area is required'
        
        # Check if property name already exists for this customer (extension 5.1)
        if property_name and Property.objects.filter(customer=customer, property_name=property_name).exists():
            errors['property_name'] = 'Property name already registered into the system. Please replace property name.'
        
        if errors:
            return render(request, 'register_property.html', {
                'customer': customer,
                'errors': errors,
                'form_data': request.POST
            })
        
        # Create new property record
        try:
            property_obj = Property.objects.create(
                customer=customer,
                property_name=property_name,
                street_number=street_number,
                street=street,
                city=city,
                province=province,
                country=country,
                zip_code=zip_code,
                property_type=property_type,
                floor_area=float(floor_area)
            )
            
            # Show success message
            return render(request, 'register_property.html', {
                'customer': customer,
                'success': True,
                'property_name': property_name
            })
        except Exception as e:
            errors['general'] = f'An error occurred while registering the property: {str(e)}'
            return render(request, 'register_property.html', {
                'customer': customer,
                'errors': errors,
                'form_data': request.POST
            })
    
    return render(request, 'register_property.html', {'customer': customer})


def edit_property(request, property_id):
    """Handle property editing (UC 07)."""
    # Check if user is logged in
    if 'customer_id' not in request.session:
        return redirect('login')
    
    customer = Customer.objects.get(id=request.session['customer_id'])
    
    try:
        property_obj = Property.objects.get(id=property_id, customer=customer)
    except Property.DoesNotExist:
        return redirect('property_list')
    
    if request.method == 'POST':
        property_name = request.POST.get('property_name', '').strip()
        street_number = request.POST.get('street_number', '').strip()
        street = request.POST.get('street', '').strip()
        city = request.POST.get('city', '').strip()
        province = request.POST.get('province', '').strip()
        country = request.POST.get('country', '').strip()
        zip_code = request.POST.get('zip_code', '').strip()
        property_type = request.POST.get('property_type', '').strip()
        floor_area = request.POST.get('floor_area', '').strip()
        
        # Validate all fields are filled (extension 7.2)
        errors = {}
        if not property_name:
            errors['property_name'] = 'Property name is required'
        if not street_number:
            errors['street_number'] = 'Street number is required'
        if not street:
            errors['street'] = 'Street is required'
        if not city:
            errors['city'] = 'City is required'
        if not province:
            errors['province'] = 'Province is required'
        if not country:
            errors['country'] = 'Country is required'
        if not zip_code:
            errors['zip_code'] = 'ZIP code is required'
        if not property_type:
            errors['property_type'] = 'Property type is required'
        if not floor_area:
            errors['floor_area'] = 'Floor area is required'
        
        # Check if new property name already exists for this customer (excluding current property)
        if property_name and Property.objects.filter(
            customer=customer, 
            property_name=property_name
        ).exclude(id=property_id).exists():
            errors['property_name'] = 'Property name already registered into the system. Please replace property name.'
        
        if errors:
            return render(request, 'edit_property.html', {
                'customer': customer,
                'property': property_obj,
                'errors': errors,
                'form_data': request.POST
            })
        
        # Update property record
        try:
            property_obj.property_name = property_name
            property_obj.street_number = street_number
            property_obj.street = street
            property_obj.city = city
            property_obj.province = province
            property_obj.country = country
            property_obj.zip_code = zip_code
            property_obj.property_type = property_type
            property_obj.floor_area = float(floor_area)
            property_obj.save()
            
            # Show success message
            return render(request, 'edit_property.html', {
                'customer': customer,
                'property': property_obj,
                'success': True,
                'property_name': property_name
            })
        except Exception as e:
            errors['general'] = f'An error occurred while updating the property: {str(e)}'
            return render(request, 'edit_property.html', {
                'customer': customer,
                'property': property_obj,
                'errors': errors,
                'form_data': request.POST
            })
    
    return render(request, 'edit_property.html', {
        'customer': customer,
        'property': property_obj,
        'form_data': {
            'property_name': property_obj.property_name,
            'street_number': property_obj.street_number,
            'street': property_obj.street,
            'city': property_obj.city,
            'province': property_obj.province,
            'country': property_obj.country,
            'zip_code': property_obj.zip_code,
            'property_type': property_obj.property_type,
            'floor_area': property_obj.floor_area,
        }
    })


def delete_property(request, property_id):
    """Handle property deletion (UC 08)."""
    # Check if user is logged in
    if 'customer_id' not in request.session:
        return redirect('login')
    
    customer = Customer.objects.get(id=request.session['customer_id'])
    
    try:
        property_obj = Property.objects.get(id=property_id, customer=customer)
    except Property.DoesNotExist:
        return redirect('property_list')
    
    if request.method == 'POST':
        property_name = property_obj.property_name
        property_obj.delete()
        
        # Return success response that will trigger success modal in frontend
        return render(request, 'property_list.html', {
            'customer': customer,
            'properties': Property.objects.filter(customer=customer),
            'delete_success': True,
            'deleted_property_name': property_name
        })
    
    # GET request should not directly delete, redirect to property list
    return redirect('property_list')

