from django.shortcuts import render, redirect
from django.contrib import messages
from django.db import transaction
from django.db.models import Case, When, IntegerField, Count, Max, Q
from django.core.mail import send_mail
from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from decimal import Decimal, InvalidOperation
from io import BytesIO
import json
import re
from collections import defaultdict
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from .models import (
    Customer,
    Property,
    Service,
    OperationsManager,
    TreatmentBooking,
    Technician,
    ServiceReport,
    ServiceReportChemical,
    ServiceReportArea,
    EstimatedBill,
    EstimatedBillItem,
    Chemical,
    Invoice,
    InvoiceItem,
    InvoiceItemOption,
    ServiceFormOption,
)
from .forms import CustomerRegistrationForm


OM_STATUS_WORKFLOW = [
    'For Confirmation',
    'For Inspection',
    'Ongoing Inspection',
    'Estimated Bill Created',
    'For Treatment Booking',
    'For Treatment',
    'Ongoing Treatment',
    'Pending Payment',
    'Payment Confirmed',
    'Completed',
    'Cancelled',
]

OM_STATUS_TRANSITIONS = {
    'For Confirmation': ['For Inspection'],
    'For Inspection': ['Ongoing Inspection'],
    'Ongoing Inspection': ['Estimated Bill Created', 'Ongoing Inspection'],
    'Estimated Bill Created': ['For Treatment Booking', 'Ongoing Inspection'],
    'For Treatment Booking': ['For Treatment'],
    'For Treatment': ['Ongoing Treatment'],
    'Ongoing Treatment': ['Pending Payment', 'For Treatment'],
    'Pending Payment': ['Payment Confirmed',],
    'Payment Confirmed': ['Completed'],
}


SERVICE_FORM_FIELD_CATALOG = {
    'Inspection': ['Type of Property', 'Preferred Service', 'Pest Problems'],
    'Treatment': ['Treatment Service'],
    'Service Report Submission': ['Service Done', 'Chemicals Used', 'Levels of Infestation'],
    'Payment Proof Submission': ['Bank Used for Payment', 'Payment Type'],
}

def home(request):
    """Public home page."""
    if request.session.get('om_id'):
        return redirect('om_home')
    if request.session.get('technician_id'):
        return redirect('technician_home')
    return render(request, 'home.html')


def login(request):
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')

        om = OperationsManager.objects.filter(email__iexact=email).only('id', 'password', 'first_name', 'last_name').first()
        if om and om.password == password:
            request.session.flush()
            request.session['om_id'] = om.id
            request.session['om_name'] = f"{om.first_name} {om.last_name}"
            return redirect('om_home')

        technician = Technician.objects.filter(email__iexact=email).only('id', 'password', 'first_name', 'last_name').first()
        if technician and technician.password == password:
            request.session.flush()
            request.session['technician_id'] = technician.id
            request.session['technician_name'] = f"{technician.first_name} {technician.last_name}"
            return redirect('technician_home')

        customer = Customer.objects.filter(email=email).only('id', 'password', 'first_name', 'last_name').first()
        if customer and customer.password == password:
            request.session.flush()
            request.session['customer_id'] = customer.id
            request.session['customer_name'] = f"{customer.first_name} {customer.last_name}"
            return redirect('home')

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
    
    try:
        customer = Customer.objects.get(id=request.session['customer_id'])
    except Customer.DoesNotExist:
        request.session.flush()
        return redirect('login')
    
    # Get ongoing services (not completed or cancelled)
    services = Service.objects.filter(
        customer=customer
    ).exclude(
        status__in=['Completed', 'Cancelled']
    ).select_related('property').order_by('-created_at')
    
    return render(request, 'profile.html', {
        'customer': customer,
        'services': services,
    })


def logout(request):
    """Log out current customer and return to home."""
    request.session.flush()
    return redirect('home')


def edit_profile(request):
    """Handle customer profile editing."""
    # Check if user is logged in
    if 'customer_id' not in request.session:
        return redirect('login')
    
    try:
        customer = Customer.objects.get(id=request.session['customer_id'])
    except Customer.DoesNotExist:
        request.session.flush()
        return redirect('login')
    
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


def change_password(request):
    """Handle password change on a dedicated screen."""
    if 'customer_id' not in request.session:
        return redirect('login')

    try:
        customer = Customer.objects.get(id=request.session['customer_id'])
    except Customer.DoesNotExist:
        request.session.flush()
        return redirect('login')

    if request.method == 'POST':
        current_password = request.POST.get('current_password', '').strip()
        new_password = request.POST.get('new_password', '').strip()
        confirm_new_password = request.POST.get('confirm_new_password', '').strip()

        errors = {}
        if not current_password:
            errors['current_password'] = 'Current password is required.'
        if not new_password:
            errors['new_password'] = 'New password is required.'
        if not confirm_new_password:
            errors['confirm_new_password'] = 'Please confirm your new password.'

        if current_password and current_password != customer.password:
            errors['current_password'] = 'Current password is incorrect.'

        if new_password and confirm_new_password and new_password != confirm_new_password:
            errors['confirm_new_password'] = 'New passwords do not match.'

        if new_password and len(new_password) < 8:
            errors['new_password'] = 'New password must be at least 8 characters.'

        if not errors:
            customer.password = new_password
            customer.save(update_fields=['password'])
            return render(request, 'change_password.html', {
                'customer': customer,
                'success': True,
            })

        return render(request, 'change_password.html', {
            'customer': customer,
            'errors': errors,
        })

    return render(request, 'change_password.html', {'customer': customer})


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
    
    try:
        customer = Customer.objects.get(id=request.session['customer_id'])
    except Customer.DoesNotExist:
        request.session.flush()
        return redirect('login')
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
    
    try:
        customer = Customer.objects.get(id=request.session['customer_id'])
    except Customer.DoesNotExist:
        request.session.flush()
        return redirect('login')
    
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
        else:
            try:
                floor_area_float = float(floor_area)
                if floor_area_float <= 0:
                    errors['floor_area'] = 'Floor area must be a positive number'
            except ValueError:
                errors['floor_area'] = 'Floor area must be a valid number'
        
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
    
    try:
        customer = Customer.objects.get(id=request.session['customer_id'])
    except Customer.DoesNotExist:
        request.session.flush()
        return redirect('login')
    
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
        else:
            try:
                floor_area_float = float(floor_area)
                if floor_area_float <= 0:
                    errors['floor_area'] = 'Floor area must be a positive number'
            except ValueError:
                errors['floor_area'] = 'Floor area must be a valid number'
        
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
    
    try:
        customer = Customer.objects.get(id=request.session['customer_id'])
    except Customer.DoesNotExist:
        request.session.flush()
        return redirect('login')
    
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


def book_inspection(request):
    """Handle inspection booking (UC 10)."""
    from datetime import date
    
    # Check if user is logged in
    if 'customer_id' not in request.session:
        return redirect('login')
    
    try:
        customer = Customer.objects.get(id=request.session['customer_id'])
    except Customer.DoesNotExist:
        request.session.flush()
        return redirect('login')
    properties = Property.objects.filter(customer=customer)
    
    # Check if customer has any properties
    if not properties.exists():
        messages.error(request, 'You need to register a property before booking an inspection.')
        return redirect('register_property')
    
    if request.method == 'POST':
        property_id = request.POST.get('property_id', '').strip()
        preferred_service = request.POST.get('preferred_service', '').strip()
        preferred_service_other = request.POST.get('preferred_service_other', '').strip()
        pest_problem = request.POST.get('pest_problem', '').strip()
        pest_problem_other = request.POST.get('pest_problem_other', '').strip()
        date = request.POST.get('date', '').strip()
        time_slot = request.POST.get('time_slot', '').strip()
        
        # Validate all required fields (extension 4.2)
        errors = {}
        if not property_id:
            errors['property_id'] = 'Property address is required'
        if not preferred_service:
            errors['preferred_service'] = 'Preferred service is required'
        if preferred_service == 'Other' and not preferred_service_other:
            errors['preferred_service_other'] = 'Please specify the preferred service'
        if not pest_problem:
            errors['pest_problem'] = 'Pest problem is required'
        if pest_problem == 'Other' and not pest_problem_other:
            errors['pest_problem_other'] = 'Please specify the pest problem'
        if not date:
            errors['date'] = 'Date is required'
        if not time_slot:
            errors['time_slot'] = 'Time slot is required'
        
        if errors:
            return render(request, 'book_inspection.html', {
                'customer': customer,
                'properties': properties,
                'errors': errors,
                'form_data': request.POST,
                'service_choices': Service.PREFERRED_SERVICE_CHOICES,
                'pest_choices': Service.PEST_PROBLEM_CHOICES,
                'time_slot_choices': Service.TIME_SLOT_CHOICES,
                'today': date.today().isoformat(),
            })
        
        # Get the selected property
        try:
            property_obj = Property.objects.get(id=property_id, customer=customer)
        except Property.DoesNotExist:
            errors['property_id'] = 'Invalid property selected'
            return render(request, 'book_inspection.html', {
                'customer': customer,
                'properties': properties,
                'errors': errors,
                'form_data': request.POST,
                'service_choices': Service.PREFERRED_SERVICE_CHOICES,
                'pest_choices': Service.PEST_PROBLEM_CHOICES,
                'time_slot_choices': Service.TIME_SLOT_CHOICES,
                'today': date.today().isoformat(),
            })
        
        # Determine the final values for preferred_service and pest_problem
        final_preferred_service = preferred_service_other if preferred_service == 'Other' else preferred_service
        final_pest_problem = pest_problem_other if pest_problem == 'Other' else pest_problem
        
        # Create the service record
        try:
            service = Service.objects.create(
                customer=customer,
                property=property_obj,
                preferred_service=final_preferred_service,
                preferred_service_other=preferred_service_other if preferred_service == 'Other' else None,
                pest_problem=final_pest_problem,
                pest_problem_other=pest_problem_other if pest_problem == 'Other' else None,
                date=date,
                time_slot=time_slot,
                status='For Confirmation'
            )
            
            # Show success state
            return render(request, 'book_inspection.html', {
                'customer': customer,
                'success': True,
                'service_id': service.id
            })
        except Exception as e:
            errors['general'] = f'An error occurred while booking the inspection: {str(e)}'
            return render(request, 'book_inspection.html', {
                'customer': customer,
                'properties': properties,
                'errors': errors,
                'form_data': request.POST,
                'service_choices': Service.PREFERRED_SERVICE_CHOICES,
                'pest_choices': Service.PEST_PROBLEM_CHOICES,
                'time_slot_choices': Service.TIME_SLOT_CHOICES,
                'today': date.today().isoformat(),
            })
    
    # GET request - display the form
    return render(request, 'book_inspection.html', {
        'customer': customer,
        'properties': properties,
        'service_choices': Service.PREFERRED_SERVICE_CHOICES,
        'pest_choices': Service.PEST_PROBLEM_CHOICES,
        'time_slot_choices': Service.TIME_SLOT_CHOICES,
        'form_data': {},
        'today': date.today().isoformat(),
    })


def service_status(request):
    """Display customer's ongoing service status (UC 16)."""
    # Check if user is logged in
    if 'customer_id' not in request.session:
        return redirect('login')
    
    try:
        customer = Customer.objects.get(id=request.session['customer_id'])
    except Customer.DoesNotExist:
        request.session.flush()
        return redirect('login')
    
    # Get all services that are not completed or cancelled (ongoing services)
    services = Service.objects.filter(
        customer=customer
    ).exclude(
        status__in=['Completed', 'Cancelled']
    ).select_related('property', 'estimated_bill', 'service_report').order_by('-created_at')
    
    return render(request, 'service_status.html', {
        'customer': customer,
        'services': services,
    })


def customer_delete_booking(request, service_id):
    if 'customer_id' not in request.session:
        return redirect('login')

    if request.method != 'POST':
        return redirect('service_status')

    try:
        customer = Customer.objects.get(id=request.session['customer_id'])
    except Customer.DoesNotExist:
        request.session.flush()
        return redirect('login')

    service = Service.objects.filter(id=service_id, customer=customer).first()
    if not service:
        messages.error(request, 'Service record not found.')
        return redirect('service_status')

    service.delete()
    messages.success(request, 'Service deleted successfully.')
    return redirect('service_status')


def customer_view_estimated_bill(request, service_id):
    if 'customer_id' not in request.session:
        return redirect('login')

    try:
        customer = Customer.objects.get(id=request.session['customer_id'])
    except Customer.DoesNotExist:
        request.session.flush()
        return redirect('login')

    estimated_bill = EstimatedBill.objects.select_related(
        'service__customer', 'service__property', 'operations_manager'
    ).prefetch_related('items').filter(
        service_id=service_id,
        service__customer=customer,
    ).first()

    if not estimated_bill:
        messages.error(request, 'Estimated bill not found.')
        return redirect('service_status')

    service = estimated_bill.service
    can_confirm = service.status == 'Estimated Bill Created'

    if request.method == 'POST' and request.POST.get('action') == 'confirm':
        if not can_confirm:
            messages.error(request, 'This estimated bill cannot be confirmed at the current service status.')
            return redirect('service_status')

        next_statuses = OM_STATUS_TRANSITIONS.get(service.status, [])
        next_status = next_statuses[0] if next_statuses else None
        if not next_status:
            messages.error(request, 'No valid next status found for this service.')
            return redirect('service_status')

        service.status = next_status
        service.save(update_fields=['status'])
        messages.success(request, 'Estimated bill confirmed successfully.')
        return redirect('service_status')

    return render(request, 'om_estimated_bill_view.html', {
        'estimated_bill': estimated_bill,
        'role': 'customer',
        'back_url_name': 'service_status',
        'allow_confirm': can_confirm,
    })


def customer_view_service_report(request, service_id):
    if 'customer_id' not in request.session:
        return redirect('login')

    try:
        customer = Customer.objects.get(id=request.session['customer_id'])
    except Customer.DoesNotExist:
        request.session.flush()
        return redirect('login')

    report = ServiceReport.objects.select_related(
        'service__customer', 'service__property', 'technician'
    ).prefetch_related('chemicals', 'treated_areas').filter(
        service_id=service_id,
        service__customer=customer,
    ).first()

    if not report:
        messages.error(request, 'Service report not found.')
        return redirect('service_status')

    return render(request, 'service_report_view.html', {
        'report': report,
        'role': 'customer',
        'back_url_name': 'service_status',
    })


def om_home(request):
    """Display OM home page."""
    if 'om_id' not in request.session:
        return redirect('login')

    try:
        om = OperationsManager.objects.get(id=request.session['om_id'])
    except OperationsManager.DoesNotExist:
        request.session.flush()
        return redirect('login')

    return render(request, 'om_home.html', {'om': om})


def om_profile(request):
    """Display OM profile page."""
    if 'om_id' not in request.session:
        return redirect('login')

    try:
        om = OperationsManager.objects.get(id=request.session['om_id'])
    except OperationsManager.DoesNotExist:
        request.session.flush()
        return redirect('login')

    return render(request, 'om_profile.html', {'om': om})


def om_change_password(request):
    """Handle OM password change."""
    if 'om_id' not in request.session:
        return redirect('login')

    try:
        om = OperationsManager.objects.get(id=request.session['om_id'])
    except OperationsManager.DoesNotExist:
        request.session.flush()
        return redirect('login')

    if request.method == 'POST':
        current_password = request.POST.get('current_password', '').strip()
        new_password = request.POST.get('new_password', '').strip()
        confirm_new_password = request.POST.get('confirm_new_password', '').strip()

        errors = {}
        if not current_password:
            errors['current_password'] = 'Current password is required.'
        if not new_password:
            errors['new_password'] = 'New password is required.'
        if not confirm_new_password:
            errors['confirm_new_password'] = 'Please confirm your new password.'

        if current_password and current_password != om.password:
            errors['current_password'] = 'Current password is incorrect.'

        if new_password and confirm_new_password and new_password != confirm_new_password:
            errors['confirm_new_password'] = 'New passwords do not match.'

        if new_password and len(new_password) < 8:
            errors['new_password'] = 'New password must be at least 8 characters.'

        if not errors:
            om.password = new_password
            om.save(update_fields=['password'])
            return render(request, 'om_change_password.html', {
                'om': om,
                'success': True,
            })

        return render(request, 'om_change_password.html', {
            'om': om,
            'errors': errors,
        })

    return render(request, 'om_change_password.html', {'om': om})


def om_placeholder(request, page_title):
    """Render inactive OM pages."""
    if 'om_id' not in request.session:
        return redirect('login')

    try:
        om = OperationsManager.objects.get(id=request.session['om_id'])
    except OperationsManager.DoesNotExist:
        request.session.flush()
        return redirect('login')

    return render(request, 'om_placeholder.html', {
        'om': om,
        'page_title': page_title,
    })


def om_service_history(request):
    return om_placeholder(request, 'Service History')


def om_billing(request):
    if 'om_id' not in request.session:
        return redirect('login')

    try:
        om = OperationsManager.objects.get(id=request.session['om_id'])
    except OperationsManager.DoesNotExist:
        request.session.flush()
        return redirect('login')

    return render(request, 'om_billing.html', {'om': om})


def om_estimated_bills(request):
    if 'om_id' not in request.session:
        return redirect('login')

    try:
        om = OperationsManager.objects.get(id=request.session['om_id'])
    except OperationsManager.DoesNotExist:
        request.session.flush()
        return redirect('login')

    estimated_bills = EstimatedBill.objects.select_related(
        'service__customer', 'service__property'
    ).order_by('-created_at')

    return render(request, 'om_estimated_bills.html', {
        'om': om,
        'estimated_bills': estimated_bills,
    })


def om_view_estimated_bill(request, estimated_bill_id):
    if 'om_id' not in request.session:
        return redirect('login')

    estimated_bill = EstimatedBill.objects.select_related(
        'service__customer', 'service__property', 'operations_manager'
    ).prefetch_related('items').filter(id=estimated_bill_id).first()

    if not estimated_bill:
        messages.error(request, 'Estimated bill not found.')
        return redirect('om_estimated_bills')

    return render(request, 'om_estimated_bill_view.html', {
        'estimated_bill': estimated_bill,
        'role': 'om',
        'back_url_name': 'om_estimated_bills',
        'allow_confirm': False,
    })


def om_edit_estimated_bill(request, estimated_bill_id):
    if 'om_id' not in request.session:
        return redirect('login')

    estimated_bill = EstimatedBill.objects.select_related(
        'service__customer', 'service__property'
    ).prefetch_related('items').filter(id=estimated_bill_id).first()

    if not estimated_bill:
        messages.error(request, 'Estimated bill not found.')
        return redirect('om_estimated_bills')

    if request.method == 'POST':
        if request.POST.get('action') == 'cancel':
            return redirect('om_estimated_bills')

        raw_items = _parse_estimated_items(request.POST.get('items_json'))
        items, has_invalid_items = _clean_estimated_items(raw_items)
        errors = {}

        if not items or has_invalid_items:
            errors['general'] = 'Required fields must be filled in.'

        if errors:
            return render(request, 'om_edit_estimated_bill.html', {
                'estimated_bill': estimated_bill,
                'errors': errors,
                'items_json': json.dumps(raw_items if raw_items else [{'service_type': '', 'quantity': ''}]),
                'service_type_choices_json': json.dumps([
                    {'value': value, 'label': label}
                    for value, label in Service.PREFERRED_SERVICE_CHOICES
                ]),
            })

        price_map = {
            'General Pest Control Treatment': Decimal('2500.00'),
            'Termite Control': Decimal('3000.00'),
            'Rodent Control': Decimal('2200.00'),
            'Mosquito Control': Decimal('1800.00'),
            'Bed Bug Treatment': Decimal('2800.00'),
            'Cockroach Control': Decimal('2000.00'),
            'Other': Decimal('1500.00'),
        }

        with transaction.atomic():
            estimated_bill.items.all().delete()
            EstimatedBillItem.objects.bulk_create([
                EstimatedBillItem(
                    estimated_bill=estimated_bill,
                    service_type=item['service_type'],
                    quantity=item['quantity'],
                    unit_price=price_map.get(item['service_type'], Decimal('1500.00')),
                )
                for item in items
            ])

        messages.success(request, 'Estimated bill updated successfully.')
        return redirect('om_estimated_bills')

    return render(request, 'om_edit_estimated_bill.html', {
        'estimated_bill': estimated_bill,
        'errors': {},
        'items_json': json.dumps([
            {
                'service_type': item.service_type,
                'quantity': item.quantity,
            }
            for item in estimated_bill.items.all()
        ]),
        'service_type_choices_json': json.dumps([
            {'value': value, 'label': label}
            for value, label in Service.PREFERRED_SERVICE_CHOICES
        ]),
    })


def om_delete_estimated_bill(request, estimated_bill_id):
    if 'om_id' not in request.session:
        return redirect('login')

    if request.method != 'POST':
        return redirect('om_estimated_bills')

    estimated_bill = EstimatedBill.objects.select_related('service').filter(id=estimated_bill_id).first()
    if not estimated_bill:
        messages.error(request, 'Estimated bill not found.')
        return redirect('om_estimated_bills')

    service = estimated_bill.service
    estimated_bill.delete()
    service.status = 'Ongoing Inspection'
    service.save(update_fields=['status'])

    messages.success(request, 'Estimated bill deleted successfully.')
    return redirect('om_estimated_bills')


def om_invoices(request):
    if 'om_id' not in request.session:
        return redirect('login')

    try:
        om = OperationsManager.objects.get(id=request.session['om_id'])
    except OperationsManager.DoesNotExist:
        request.session.flush()
        return redirect('login')

    invoices = Invoice.objects.select_related(
        'service__customer', 'service__property'
    ).order_by('-created_at')

    return render(request, 'om_invoices.html', {
        'om': om,
        'invoices': invoices,
    })


def om_view_invoice(request, invoice_id):
    if 'om_id' not in request.session:
        return redirect('login')

    invoice = Invoice.objects.select_related(
        'service__customer', 'service__property', 'operations_manager'
    ).prefetch_related('items').filter(id=invoice_id).first()

    if not invoice:
        messages.error(request, 'Invoice not found.')
        return redirect('om_invoices')

    return render(request, 'om_invoice_view.html', {
        'invoice': invoice,
        'back_url_name': 'om_invoices',
    })


def om_download_invoice_pdf(request, invoice_id):
    if 'om_id' not in request.session:
        return redirect('login')

    invoice = Invoice.objects.select_related(
        'service__customer', 'service__property'
    ).prefetch_related('items').filter(id=invoice_id).first()

    if not invoice:
        messages.error(request, 'Invoice not found.')
        return redirect('om_invoices')

    pdf_bytes = _render_simple_pdf(
        title='Invoice',
        header_lines=[
            f"Invoice ID: INV{invoice.id:04d}",
            f"Service ID: {invoice.service.id:07d}",
            f"Customer: {invoice.service.customer.first_name} {invoice.service.customer.last_name}",
            f"Address: {invoice.service.property.street_number} {invoice.service.property.street}, {invoice.service.property.city}",
            f"Date Created: {invoice.created_at:%m/%d/%Y}",
        ],
        table_headers=['Item', 'Qty', 'Unit Price', 'Line Total'],
        table_rows=[
            [
                item.item_type,
                item.quantity,
                f"₱ {item.unit_price}",
                f"₱ {item.line_total}",
            ]
            for item in invoice.items.all()
        ],
        total_line=f"Total: ₱ {invoice.total_amount}",
    )

    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="invoice_INV{invoice.id:04d}.pdf"'
    return response


def om_edit_invoice(request, invoice_id):
    if 'om_id' not in request.session:
        return redirect('login')

    invoice = Invoice.objects.select_related(
        'service__customer', 'service__property'
    ).prefetch_related('items', 'service__estimated_bill__items').filter(id=invoice_id).first()

    if not invoice:
        messages.error(request, 'Invoice not found.')
        return redirect('om_invoices')

    existing_item_ids = list(
        invoice.items.exclude(service_item_id__isnull=True).values_list('service_item_id', flat=True)
    )
    service_item_options = InvoiceItemOption.objects.filter(
        Q(is_active=True) | Q(id__in=existing_item_ids)
    ).order_by('name')
    allowed_item_map = {option.id: option.name for option in service_item_options}
    service_item_choices = [
        {
            'value': str(option.id),
            'label': option.name,
            'description': option.description,
            'default_unit_price': str(option.default_unit_price),
        }
        for option in service_item_options
    ]

    if request.method == 'POST':
        if request.POST.get('action') == 'cancel':
            return redirect('om_invoices')

        raw_items = _parse_invoice_items(request.POST.get('items_json'))
        items, has_invalid = _clean_invoice_items(raw_items, allowed_item_map=allowed_item_map)
        errors = {}

        if not service_item_choices:
            errors['general'] = 'Please create at least one Service Item in Service Configuration first.'

        if not items or has_invalid:
            errors['general'] = 'Required fields must be filled in.'

        if errors:
            return render(request, 'om_edit_invoice.html', {
                'invoice': invoice,
                'errors': errors,
                'items_json': json.dumps(raw_items if raw_items else [{'service_item_id': '', 'quantity': '', 'unit_price': ''}]),
                'service_item_choices_json': json.dumps(service_item_choices),
            })

        with transaction.atomic():
            invoice.items.all().delete()
            InvoiceItem.objects.bulk_create([
                InvoiceItem(
                    invoice=invoice,
                    service_item_id=item['service_item_id'],
                    item_type=item['item_type'],
                    quantity=item['quantity'],
                    unit_price=item['unit_price'],
                )
                for item in items
            ])

        messages.success(request, 'Invoice updated successfully.')
        return redirect('om_invoices')

    return render(request, 'om_edit_invoice.html', {
        'invoice': invoice,
        'errors': {},
        'items_json': json.dumps([
            {
                'service_item_id': str(item.service_item_id) if item.service_item_id else '',
                'quantity': item.quantity,
                'unit_price': str(item.unit_price),
            }
            for item in invoice.items.all()
        ]),
        'service_item_choices_json': json.dumps(service_item_choices),
    })


def om_delete_invoice(request, invoice_id):
    if 'om_id' not in request.session:
        return redirect('login')

    if request.method != 'POST':
        return redirect('om_invoices')

    invoice = Invoice.objects.select_related('service').filter(id=invoice_id).first()
    if not invoice:
        messages.error(request, 'Invoice not found.')
        return redirect('om_invoices')

    service = invoice.service
    invoice.delete()
    service.status = 'Ongoing Treatment'
    service.save(update_fields=['status'])

    messages.success(request, 'Invoice deleted successfully.')
    return redirect('om_invoices')


def _parse_estimated_items(raw_payload):
    if not raw_payload:
        return []
    try:
        parsed = json.loads(raw_payload)
        return parsed if isinstance(parsed, list) else []
    except (TypeError, ValueError):
        return []


def _clean_estimated_items(raw_items):
    cleaned_items = []
    has_invalid = False

    for item in raw_items:
        if not isinstance(item, dict):
            continue

        service_type = (item.get('service_type') or '').strip()
        quantity_raw = str(item.get('quantity') or '').strip()

        if not (service_type or quantity_raw):
            continue

        if not service_type or not quantity_raw:
            has_invalid = True
            continue

        try:
            quantity = int(quantity_raw)
            if quantity <= 0:
                has_invalid = True
                continue
        except (ValueError, TypeError):
            has_invalid = True
            continue

        cleaned_items.append({
            'service_type': service_type,
            'quantity': quantity,
        })

    return cleaned_items, has_invalid


def _parse_invoice_items(raw_payload):
    if not raw_payload:
        return []
    try:
        parsed = json.loads(raw_payload)
        return parsed if isinstance(parsed, list) else []
    except (TypeError, ValueError):
        return []


def _clean_invoice_items(raw_items, allowed_item_map=None):
    cleaned_items = []
    has_invalid = False
    allowed_map = allowed_item_map or {}

    for item in raw_items:
        if not isinstance(item, dict):
            continue

        service_item_id_raw = str(item.get('service_item_id') or '').strip()
        quantity_raw = str(item.get('quantity') or '').strip()
        unit_price_raw = str(item.get('unit_price') or '').strip()

        if not (service_item_id_raw or quantity_raw or unit_price_raw):
            continue

        if not service_item_id_raw or not quantity_raw or not unit_price_raw:
            has_invalid = True
            continue

        try:
            service_item_id = int(service_item_id_raw)
        except (TypeError, ValueError):
            has_invalid = True
            continue

        if allowed_map and service_item_id not in allowed_map:
            has_invalid = True
            continue

        try:
            quantity = int(quantity_raw)
            if quantity <= 0:
                has_invalid = True
                continue
        except (TypeError, ValueError):
            has_invalid = True
            continue

        try:
            unit_price = Decimal(unit_price_raw)
            if unit_price <= 0:
                has_invalid = True
                continue
        except (InvalidOperation, TypeError, ValueError):
            has_invalid = True
            continue

        cleaned_items.append({
            'service_item_id': service_item_id,
            'item_type': allowed_map.get(service_item_id, ''),
            'quantity': quantity,
            'unit_price': unit_price,
        })

    return cleaned_items, has_invalid


def _render_simple_pdf(title, header_lines, table_headers, table_rows, total_line=''):
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    y = height - 50

    pdf.setFont('Helvetica-Bold', 16)
    pdf.drawString(50, y, title)
    y -= 24

    pdf.setFont('Helvetica', 10)
    for line in header_lines:
        if y < 70:
            pdf.showPage()
            y = height - 50
            pdf.setFont('Helvetica', 10)
        pdf.drawString(50, y, str(line))
        y -= 14

    y -= 6
    if table_headers:
        pdf.setFont('Helvetica-Bold', 10)
        x_positions = [50, 250, 340, 440]
        for idx, header in enumerate(table_headers[:4]):
            pdf.drawString(x_positions[idx], y, str(header))
        y -= 14

    pdf.setFont('Helvetica', 10)
    for row in table_rows:
        if y < 70:
            pdf.showPage()
            y = height - 50
            pdf.setFont('Helvetica', 10)
        x_positions = [50, 250, 340, 440]
        for idx, value in enumerate(row[:4]):
            pdf.drawString(x_positions[idx], y, str(value))
        y -= 14

    if total_line:
        y -= 8
        pdf.setFont('Helvetica-Bold', 11)
        pdf.drawString(50, y, str(total_line))

    pdf.showPage()
    pdf.save()
    buffer.seek(0)
    return buffer.getvalue()


def _get_invoice_eligible_services_queryset():
    return Service.objects.filter(
        status__in=['Ongoing Treatment', 'Pending Payment'],
        estimated_bill__isnull=False,
    ).select_related('customer', 'property', 'estimated_bill').prefetch_related(
        'estimated_bill__items',
        'invoices__items',
    ).order_by('-treatment_confirmed_date', '-confirmed_date', '-date', '-created_at')


def _filter_invoice_eligible_services(services):
    eligible_services = []
    for service in services:
        has_previous_invoice = service.invoices.exists()
        if service.status == 'Pending Payment' and not has_previous_invoice:
            continue
        eligible_services.append(service)
    return eligible_services


def om_create_invoice(request):
    if 'om_id' not in request.session:
        return redirect('login')

    try:
        om = OperationsManager.objects.get(id=request.session['om_id'])
    except OperationsManager.DoesNotExist:
        request.session.flush()
        return redirect('login')

    service_candidates = _get_invoice_eligible_services_queryset()
    selectable_services = _filter_invoice_eligible_services(service_candidates)
    service_item_options = InvoiceItemOption.objects.filter(is_active=True).order_by('name')
    allowed_item_map = {option.id: option.name for option in service_item_options}
    service_item_choices = [
        {
            'value': str(option.id),
            'label': option.name,
            'description': option.description,
            'default_unit_price': str(option.default_unit_price),
        }
        for option in service_item_options
    ]

    if request.method == 'POST':
        if request.POST.get('action') == 'cancel':
            return redirect('om_invoices')

        selected_service_id = request.POST.get('selected_service_id', '').strip()
        raw_items = _parse_invoice_items(request.POST.get('items_json'))
        cleaned_items, has_invalid = _clean_invoice_items(raw_items, allowed_item_map=allowed_item_map)

        selected_service = next(
            (service for service in selectable_services if str(service.id) == selected_service_id),
            None,
        )
        errors = {}

        if not selected_service:
            errors['general'] = 'Required fields must be filled in.'

        if not service_item_choices:
            errors['general'] = 'Please create at least one Service Item in Service Configuration first.'

        if not cleaned_items:
            errors['general'] = 'Required fields must be filled in.'
        elif has_invalid:
            errors['general'] = 'Required fields must be filled in.'

        if errors:
            return render(request, 'om_create_invoice.html', {
                'om': om,
                'services': selectable_services,
                'selected_service_id': selected_service_id,
                'errors': errors,
                'items_json': json.dumps(raw_items if raw_items else [{'service_item_id': '', 'quantity': '', 'unit_price': ''}]),
                'service_item_choices_json': json.dumps(service_item_choices),
            })

        with transaction.atomic():
            invoice = Invoice.objects.create(
                service=selected_service,
                operations_manager=om,
            )

            InvoiceItem.objects.bulk_create([
                InvoiceItem(
                    invoice=invoice,
                    service_item_id=item['service_item_id'],
                    item_type=item['item_type'],
                    quantity=item['quantity'],
                    unit_price=item['unit_price'],
                )
                for item in cleaned_items
            ])

            selected_service.status = 'Pending Payment'
            selected_service.save(update_fields=['status'])

        email_subject = 'Your Invoice from Supreme Biotech Solutions'
        email_body = (
            f"Hello {selected_service.customer.first_name},\n\n"
            f"Your invoice (ID: INV{invoice.id:04d}) has been created for Service {selected_service.id:07d}.\n"
            "Please log in to your account to view the details and settle your balance.\n\n"
            "Thank you."
        )

        send_mail(
            subject=email_subject,
            message=email_body,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@supreme.local'),
            recipient_list=[selected_service.customer.email],
            fail_silently=True,
        )

        messages.success(request, 'You have successfully created an invoice.')
        return redirect('om_invoices')

    return render(request, 'om_create_invoice.html', {
        'om': om,
        'services': selectable_services,
        'selected_service_id': '',
        'errors': {},
        'items_json': json.dumps([{'service_item_id': '', 'quantity': '', 'unit_price': ''}]),
        'service_item_choices_json': json.dumps(service_item_choices),
    })


def om_create_estimated_bill(request):
    if 'om_id' not in request.session:
        return redirect('login')

    try:
        om = OperationsManager.objects.get(id=request.session['om_id'])
    except OperationsManager.DoesNotExist:
        request.session.flush()
        return redirect('login')

    ongoing_inspection_services = Service.objects.filter(
        status='Ongoing Inspection',
        estimated_bill__isnull=True,
    ).select_related('customer', 'property').order_by('-date', '-created_at')

    default_items = [{'service_type': '', 'quantity': ''}]
    errors = {}

    if request.method == 'POST':
        if request.POST.get('action') == 'cancel':
            return redirect('om_estimated_bills')

        selected_service_id = request.POST.get('selected_service_id', '').strip()
        raw_items = _parse_estimated_items(request.POST.get('items_json'))
        items, has_invalid_items = _clean_estimated_items(raw_items)

        selected_service = ongoing_inspection_services.filter(id=selected_service_id).first()
        if not selected_service:
            errors['general'] = 'Required fields must be filled in.'

        if not items:
            errors['general'] = 'Required fields must be filled in.'
        elif has_invalid_items:
            errors['general'] = 'Required fields must be filled in.'

        if errors:
            return render(request, 'om_create_estimated_bill.html', {
                'om': om,
                'services': ongoing_inspection_services,
                'selected_service_id': selected_service_id,
                'errors': errors,
                'items_json': json.dumps(raw_items if raw_items else default_items),
                'service_type_choices': Service.PREFERRED_SERVICE_CHOICES,
                'service_type_choices_json': json.dumps([
                    {'value': value, 'label': label}
                    for value, label in Service.PREFERRED_SERVICE_CHOICES
                ]),
            })

        if EstimatedBill.objects.filter(service=selected_service).exists():
            messages.error(request, 'An estimated bill for this service already exists.')
            return redirect('om_estimated_bills')

        price_map = {
            'General Pest Control Treatment': Decimal('2500.00'),
            'Termite Control': Decimal('3000.00'),
            'Rodent Control': Decimal('2200.00'),
            'Mosquito Control': Decimal('1800.00'),
            'Bed Bug Treatment': Decimal('2800.00'),
            'Cockroach Control': Decimal('2000.00'),
            'Other': Decimal('1500.00'),
        }

        with transaction.atomic():
            estimated_bill = EstimatedBill.objects.create(
                service=selected_service,
                operations_manager=om,
            )

            EstimatedBillItem.objects.bulk_create([
                EstimatedBillItem(
                    estimated_bill=estimated_bill,
                    service_type=item['service_type'],
                    quantity=item['quantity'],
                    unit_price=price_map.get(item['service_type'], Decimal('1500.00')),
                )
                for item in items
            ])

            selected_service.status = 'Estimated Bill Created'
            selected_service.save(update_fields=['status'])

        email_subject = 'Your Estimated Bill from Supreme Biotech Solutions'
        email_body = (
            f"Hello {selected_service.customer.first_name},\n\n"
            f"Your estimated bill (ID: {estimated_bill.id:07d}) has been created for Service {selected_service.id:07d}.\n"
            "Please log in to your account to view the details.\n\n"
            "Thank you."
        )

        send_mail(
            subject=email_subject,
            message=email_body,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@supreme.local'),
            recipient_list=[selected_service.customer.email],
            fail_silently=True,
        )

        messages.success(request, 'You have successfully created an estimated bill.')
        return redirect('om_estimated_bills')

    return render(request, 'om_create_estimated_bill.html', {
        'om': om,
        'services': ongoing_inspection_services,
        'selected_service_id': '',
        'errors': {},
        'items_json': json.dumps(default_items),
        'service_type_choices': Service.PREFERRED_SERVICE_CHOICES,
        'service_type_choices_json': json.dumps([
            {'value': value, 'label': label}
            for value, label in Service.PREFERRED_SERVICE_CHOICES
        ]),
    })


def om_service_reports(request):
    if 'om_id' not in request.session:
        return redirect('login')

    try:
        om = OperationsManager.objects.get(id=request.session['om_id'])
    except OperationsManager.DoesNotExist:
        request.session.flush()
        return redirect('login')

    reports = ServiceReport.objects.select_related(
        'service__customer', 'service__property'
    ).order_by('-created_at')

    return render(request, 'om_service_reports.html', {
        'om': om,
        'reports': reports,
    })


def om_remittance_records(request):
    return om_placeholder(request, 'Remittance Records')


def om_manage_service_forms(request):
    if 'om_id' not in request.session:
        return redirect('login')

    try:
        om = OperationsManager.objects.get(id=request.session['om_id'])
    except OperationsManager.DoesNotExist:
        request.session.flush()
        return redirect('login')

    return render(request, 'om_manage_service_forms.html', {'om': om})


def om_service_forms(request):
    if 'om_id' not in request.session:
        return redirect('login')

    try:
        om = OperationsManager.objects.get(id=request.session['om_id'])
    except OperationsManager.DoesNotExist:
        request.session.flush()
        return redirect('login')

    if request.method == 'POST':
        action = request.POST.get('action', '').strip()
        option_id = request.POST.get('option_id', '').strip()
        form_section = request.POST.get('form_section', '').strip()
        field_name = request.POST.get('field_name', '').strip()
        option_value = request.POST.get('option_value', '').strip()

        valid_field_names = SERVICE_FORM_FIELD_CATALOG.get(form_section, [])
        if action in {'create', 'update'}:
            if not form_section or field_name not in valid_field_names or not option_value:
                messages.error(request, 'Required fields must be filled in.')
                return redirect('om_service_forms')

        if action == 'create':
            existing = ServiceFormOption.objects.filter(
                form_section=form_section,
                field_name=field_name,
                option_value__iexact=option_value,
            ).first()

            if existing and existing.is_active:
                messages.error(request, 'Entered option already exists.')
                return redirect('om_service_forms')

            if existing and not existing.is_active:
                existing.option_value = option_value
                existing.is_active = True
                existing.save(update_fields=['option_value', 'is_active', 'updated_at'])
                messages.success(request, 'Field option restored successfully.')
                return redirect('om_service_forms')

            ServiceFormOption.objects.create(
                form_section=form_section,
                field_name=field_name,
                option_value=option_value,
                is_active=True,
            )
            messages.success(request, 'Field option added successfully.')
            return redirect('om_service_forms')

        if action == 'update':
            if not option_id.isdigit():
                messages.error(request, 'Invalid field option.')
                return redirect('om_service_forms')

            option = ServiceFormOption.objects.filter(id=int(option_id)).first()
            if not option:
                messages.error(request, 'Field option not found.')
                return redirect('om_service_forms')

            duplicate = ServiceFormOption.objects.filter(
                form_section=form_section,
                field_name=field_name,
                option_value__iexact=option_value,
                is_active=True,
            ).exclude(id=option.id).exists()

            if duplicate:
                messages.error(request, 'Entered option already exists.')
                return redirect('om_service_forms')

            option.form_section = form_section
            option.field_name = field_name
            option.option_value = option_value
            option.save(update_fields=['form_section', 'field_name', 'option_value', 'updated_at'])
            messages.success(request, 'Field option updated successfully.')
            return redirect('om_service_forms')

        if action == 'delete':
            if not option_id.isdigit():
                messages.error(request, 'Invalid field option.')
                return redirect('om_service_forms')

            option = ServiceFormOption.objects.filter(id=int(option_id)).first()
            if not option:
                messages.error(request, 'Field option not found.')
                return redirect('om_service_forms')

            if not option.is_active:
                messages.info(request, 'Field option is already inactive.')
                return redirect('om_service_forms')

            option.is_active = False
            option.save(update_fields=['is_active', 'updated_at'])
            messages.success(request, 'Field option deleted successfully.')
            return redirect('om_service_forms')

        messages.error(request, 'Unsupported action.')
        return redirect('om_service_forms')

    active_options = ServiceFormOption.objects.filter(is_active=True).order_by(
        'form_section', 'field_name', 'option_value'
    )

    grouped_options = defaultdict(lambda: defaultdict(list))
    for option in active_options:
        grouped_options[option.form_section][option.field_name].append(option)

    return render(request, 'om_service_forms.html', {
        'om': om,
        'field_catalog': SERVICE_FORM_FIELD_CATALOG,
        'field_catalog_json': json.dumps(SERVICE_FORM_FIELD_CATALOG),
        'grouped_options': dict(grouped_options),
    })


def om_service_items(request):
    if 'om_id' not in request.session:
        return redirect('login')

    try:
        om = OperationsManager.objects.get(id=request.session['om_id'])
    except OperationsManager.DoesNotExist:
        request.session.flush()
        return redirect('login')

    if request.method == 'POST':
        action = request.POST.get('action', '').strip()
        item_id = request.POST.get('item_id', '').strip()

        if action in {'create', 'update'}:
            name = request.POST.get('name', '').strip()
            description = request.POST.get('description', '').strip()
            default_unit_price_raw = request.POST.get('default_unit_price', '').strip()
            is_active = request.POST.get('is_active') == 'on'

            if not name:
                messages.error(request, 'Service item name is required.')
                return redirect('om_service_items')

            if default_unit_price_raw:
                try:
                    default_unit_price = Decimal(default_unit_price_raw)
                    if default_unit_price <= 0:
                        raise InvalidOperation
                except (InvalidOperation, TypeError, ValueError):
                    messages.error(request, 'Default price must be a positive amount.')
                    return redirect('om_service_items')
            else:
                default_unit_price = Decimal('1500.00')

            if action == 'create':
                existing_item = InvoiceItemOption.objects.filter(name__iexact=name).first()
                if existing_item and existing_item.is_active:
                    messages.error(request, 'A service item with this name already exists.')
                    return redirect('om_service_items')
                if existing_item and not existing_item.is_active:
                    existing_item.name = name
                    existing_item.description = description
                    existing_item.default_unit_price = default_unit_price
                    existing_item.is_active = True
                    existing_item.save(update_fields=['name', 'description', 'default_unit_price', 'is_active'])
                    messages.success(request, 'Service item restored successfully.')
                    return redirect('om_service_items')
                InvoiceItemOption.objects.create(
                    name=name,
                    description=description,
                    default_unit_price=default_unit_price,
                    is_active=True,
                )
                messages.success(request, 'Service item created successfully.')
                return redirect('om_service_items')

            if not item_id.isdigit():
                messages.error(request, 'Invalid service item.')
                return redirect('om_service_items')

            service_item = InvoiceItemOption.objects.filter(id=int(item_id)).first()
            if not service_item:
                messages.error(request, 'Service item not found.')
                return redirect('om_service_items')

            duplicate = InvoiceItemOption.objects.filter(name__iexact=name).exclude(id=service_item.id).exists()
            if duplicate:
                messages.error(request, 'A service item with this name already exists.')
                return redirect('om_service_items')

            service_item.name = name
            service_item.description = description
            service_item.default_unit_price = default_unit_price
            service_item.is_active = is_active
            service_item.save(update_fields=['name', 'description', 'default_unit_price', 'is_active'])
            messages.success(request, 'Service item updated successfully.')
            return redirect('om_service_items')

        if action == 'delete':
            if not item_id.isdigit():
                messages.error(request, 'Invalid service item.')
                return redirect('om_service_items')
            service_item = InvoiceItemOption.objects.filter(id=int(item_id)).first()
            if not service_item:
                messages.error(request, 'Service item not found.')
                return redirect('om_service_items')

            if not service_item.is_active:
                messages.info(request, 'Service item is already inactive.')
                return redirect('om_service_items')

            service_item.is_active = False
            service_item.save(update_fields=['is_active'])
            messages.success(request, 'Service item deactivated successfully.')
            return redirect('om_service_items')

        messages.error(request, 'Unsupported action.')
        return redirect('om_service_items')

    service_items = list(InvoiceItemOption.objects.order_by('name'))
    usage_rows = InvoiceItem.objects.values('item_type').annotate(
        usage_count=Count('id'),
        last_used_unit_price=Max('unit_price'),
    )
    usage_map = {
        row['item_type']: {
            'usage_count': row['usage_count'],
            'last_used_unit_price': row['last_used_unit_price'],
        }
        for row in usage_rows
    }

    service_item_rows = []
    for item in service_items:
        usage = usage_map.get(item.name, {})
        service_item_rows.append({
            'id': item.id,
            'name': item.name,
            'description': item.description,
            'default_unit_price': item.default_unit_price,
            'is_active': item.is_active,
            'usage_count': usage.get('usage_count', 0),
            'last_used_unit_price': usage.get('last_used_unit_price'),
        })

    return render(request, 'om_invoice_items.html', {
        'om': om,
        'service_items': service_item_rows,
    })


def om_chemicals(request):
    if 'om_id' not in request.session:
        return redirect('login')

    try:
        om = OperationsManager.objects.get(id=request.session['om_id'])
    except OperationsManager.DoesNotExist:
        request.session.flush()
        return redirect('login')

    if request.method == 'POST':
        action = request.POST.get('action', '').strip()
        chemical_id = request.POST.get('chemical_id', '').strip()

        if action in {'create', 'update'}:
            name = request.POST.get('name', '').strip()
            standard_unit_measure = request.POST.get('standard_unit_measure', '').strip()
            is_active = request.POST.get('is_active') == 'on'

            if not name or not standard_unit_measure:
                messages.error(request, 'Chemical name and standard unit measure are required.')
                return redirect('om_chemicals')

            if action == 'create':
                existing = Chemical.objects.filter(name__iexact=name).first()
                if existing and existing.is_active:
                    messages.error(request, 'A chemical with this name already exists.')
                    return redirect('om_chemicals')
                if existing and not existing.is_active:
                    existing.name = name
                    existing.standard_unit_measure = standard_unit_measure
                    existing.is_active = True
                    existing.save(update_fields=['name', 'standard_unit_measure', 'is_active'])
                    messages.success(request, 'Chemical restored successfully.')
                    return redirect('om_chemicals')

                Chemical.objects.create(
                    name=name,
                    standard_unit_measure=standard_unit_measure,
                    is_active=True,
                )
                messages.success(request, 'Chemical created successfully.')
                return redirect('om_chemicals')

            if not chemical_id.isdigit():
                messages.error(request, 'Invalid chemical.')
                return redirect('om_chemicals')

            chemical = Chemical.objects.filter(id=int(chemical_id)).first()
            if not chemical:
                messages.error(request, 'Chemical not found.')
                return redirect('om_chemicals')

            duplicate = Chemical.objects.filter(name__iexact=name).exclude(id=chemical.id).exists()
            if duplicate:
                messages.error(request, 'A chemical with this name already exists.')
                return redirect('om_chemicals')

            chemical.name = name
            chemical.standard_unit_measure = standard_unit_measure
            chemical.is_active = is_active
            chemical.save(update_fields=['name', 'standard_unit_measure', 'is_active'])
            messages.success(request, 'Chemical updated successfully.')
            return redirect('om_chemicals')

        if action == 'delete':
            if not chemical_id.isdigit():
                messages.error(request, 'Invalid chemical.')
                return redirect('om_chemicals')

            chemical = Chemical.objects.filter(id=int(chemical_id)).first()
            if not chemical:
                messages.error(request, 'Chemical not found.')
                return redirect('om_chemicals')

            if not chemical.is_active:
                messages.info(request, 'Chemical is already inactive.')
                return redirect('om_chemicals')

            chemical.is_active = False
            chemical.save(update_fields=['is_active'])
            messages.success(request, 'Chemical deactivated successfully.')
            return redirect('om_chemicals')

        messages.error(request, 'Unsupported action.')
        return redirect('om_chemicals')

    usage_rows = ServiceReportChemical.objects.values('chemical_id').annotate(
        usage_count=Count('id'),
    )
    usage_map = {
        row['chemical_id']: row['usage_count']
        for row in usage_rows
        if row['chemical_id'] is not None
    }

    chemical_rows = []
    for chemical in Chemical.objects.order_by('name'):
        chemical_rows.append({
            'id': chemical.id,
            'name': chemical.name,
            'standard_unit_measure': chemical.standard_unit_measure,
            'is_active': chemical.is_active,
            'usage_count': usage_map.get(chemical.id, 0),
        })

    return render(request, 'om_chemicals.html', {
        'om': om,
        'chemicals': chemical_rows,
    })


def om_invoice_items(request):
    return redirect('om_service_items')


def om_manage_accounts(request):
    if 'om_id' not in request.session:
        return redirect('login')

    try:
        om = OperationsManager.objects.get(id=request.session['om_id'])
    except OperationsManager.DoesNotExist:
        request.session.flush()
        return redirect('login')

    if request.method == 'POST':
        action = request.POST.get('action', '').strip()

        if action == 'create_technician':
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            password = request.POST.get('password', '').strip()

            errors = {}
            if not first_name:
                errors['first_name'] = 'First name is required.'
            if not last_name:
                errors['last_name'] = 'Last name is required.'
            if not password:
                errors['password'] = 'Password is required.'

            if errors:
                return render(request, 'om_manage_accounts.html', {
                    'om': om,
                    'errors': errors,
                    'form_data': request.POST,
                    'technicians': Technician.objects.all().order_by('technician_id'),
                })

            existing_ids = []
            for tech in Technician.objects.only('technician_id'):
                digits = re.sub(r'\D', '', tech.technician_id or '')
                if digits:
                    existing_ids.append(int(digits))

            next_id = (max(existing_ids) + 1) if existing_ids else 1
            technician_id = str(next_id)
            email = f"tech{technician_id}@companyemail.com"

            Technician.objects.create(
                technician_id=technician_id,
                first_name=first_name,
                last_name=last_name,
                email=email,
                password=password,
            )
            messages.success(request, f'Technician account created: ID {technician_id} ({email})')
            return redirect('om_manage_accounts')

        if action == 'change_technician_password':
            technician_pk = request.POST.get('technician_pk', '').strip()
            new_password = request.POST.get('new_password', '').strip()

            if not technician_pk or not new_password:
                messages.error(request, 'Technician and new password are required.')
                return redirect('om_manage_accounts')

            technician = Technician.objects.filter(id=technician_pk).first()
            if not technician:
                messages.error(request, 'Technician account not found.')
                return redirect('om_manage_accounts')

            technician.password = new_password
            technician.save(update_fields=['password'])
            messages.success(request, f'Password updated for {technician.email}.')
            return redirect('om_manage_accounts')

        if action == 'delete_technician':
            technician_pk = request.POST.get('technician_pk', '').strip()

            if not technician_pk:
                messages.error(request, 'Technician account not found.')
                return redirect('om_manage_accounts')

            technician = Technician.objects.filter(id=technician_pk).first()
            if not technician:
                messages.error(request, 'Technician account not found.')
                return redirect('om_manage_accounts')

            deleted_email = technician.email
            technician.delete()
            messages.success(request, f'Technician account deleted: {deleted_email}')
            return redirect('om_manage_accounts')

    return render(request, 'om_manage_accounts.html', {
        'om': om,
        'technicians': Technician.objects.all().order_by('technician_id'),
        'form_data': {},
    })


def om_edit_technician_account(request, technician_pk):
    if 'om_id' not in request.session:
        return redirect('login')

    try:
        om = OperationsManager.objects.get(id=request.session['om_id'])
    except OperationsManager.DoesNotExist:
        request.session.flush()
        return redirect('login')

    technician = Technician.objects.filter(id=technician_pk).first()
    if not technician:
        messages.error(request, 'Technician account not found.')
        return redirect('om_manage_accounts')

    if request.method == 'POST':
        if request.POST.get('action') == 'cancel':
            return redirect('om_manage_accounts')

        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        new_password = request.POST.get('password', '').strip()

        errors = {}
        if not first_name:
            errors['first_name'] = 'First name is required.'
        if not last_name:
            errors['last_name'] = 'Last name is required.'

        if errors:
            return render(request, 'om_edit_technician_account.html', {
                'om': om,
                'technician': technician,
                'errors': errors,
                'form_data': request.POST,
            })

        technician.first_name = first_name
        technician.last_name = last_name
        update_fields = ['first_name', 'last_name']

        if new_password:
            technician.password = new_password
            update_fields.append('password')

        technician.save(update_fields=update_fields)
        messages.success(request, f'Technician account updated: {technician.email}')
        return redirect('om_manage_accounts')

    return render(request, 'om_edit_technician_account.html', {
        'om': om,
        'technician': technician,
        'form_data': {
            'first_name': technician.first_name,
            'last_name': technician.last_name,
        },
    })


def technician_home(request):
    if 'technician_id' not in request.session:
        return redirect('login')

    try:
        technician = Technician.objects.get(id=request.session['technician_id'])
    except Technician.DoesNotExist:
        request.session.flush()
        return redirect('login')

    return render(request, 'technician_home.html', {'technician': technician})


def technician_profile(request):
    if 'technician_id' not in request.session:
        return redirect('login')

    try:
        technician = Technician.objects.get(id=request.session['technician_id'])
    except Technician.DoesNotExist:
        request.session.flush()
        return redirect('login')

    return render(request, 'technician_profile.html', {'technician': technician})


def technician_service_status(request):
    if 'technician_id' not in request.session:
        return redirect('login')

    try:
        technician = Technician.objects.get(id=request.session['technician_id'])
    except Technician.DoesNotExist:
        request.session.flush()
        return redirect('login')

    created_order = request.GET.get('created_order', 'newest').strip().lower()
    if created_order not in {'newest', 'oldest'}:
        created_order = 'newest'
    order_by = 'created_at' if created_order == 'oldest' else '-created_at'

    status_order_cases = [
        When(status=status_value, then=position)
        for position, status_value in enumerate(OM_STATUS_WORKFLOW)
    ]

    services = Service.objects.exclude(
        status__in=['Completed', 'Cancelled']
    ).select_related('customer', 'property', 'service_report').annotate(
        workflow_order=Case(
            *status_order_cases,
            default=len(OM_STATUS_WORKFLOW),
            output_field=IntegerField(),
        )
    ).order_by(order_by, 'workflow_order')

    return render(request, 'technician_service_status.html', {
        'technician': technician,
        'services': services,
        'created_order': created_order,
    })


def technician_view_booking(request, service_id):
    """Display read-only booking details for technician."""
    if 'technician_id' not in request.session:
        return redirect('login')

    try:
        technician = Technician.objects.get(id=request.session['technician_id'])
    except Technician.DoesNotExist:
        request.session.flush()
        return redirect('login')

    service = Service.objects.select_related('customer', 'property').filter(id=service_id).first()
    if not service:
        messages.error(request, 'Service record not found.')
        return redirect('technician_service_status')

    return render(request, 'view_booking.html', {
        'technician': technician,
        'service': service,
        'identified_as': 'Technician',
        'back_url_name': 'technician_service_status',
    })


def technician_update_service_status(request, service_id):
    if 'technician_id' not in request.session:
        return redirect('login')

    try:
        technician = Technician.objects.get(id=request.session['technician_id'])
    except Technician.DoesNotExist:
        request.session.flush()
        return redirect('login')

    try:
        service = Service.objects.select_related('customer').get(id=service_id)
    except Service.DoesNotExist:
        messages.error(request, 'Service record not found.')
        return redirect('technician_service_status')

    technician_transitions = {
        'For Inspection': ['Ongoing Inspection'],
        'For Treatment': ['Ongoing Treatment'],
    }
    allowed_next_statuses = technician_transitions.get(service.status, [])
    status_choices = [(value, value) for value in allowed_next_statuses]
    allowed_statuses = set(allowed_next_statuses)

    if request.method == 'POST':
        if request.POST.get('action') == 'cancel':
            return redirect('technician_service_status')

        new_status = request.POST.get('new_status', '').strip()
        errors = {}

        if not new_status:
            errors['new_status'] = 'Required fields must be filled in.'
        elif new_status not in allowed_statuses:
            errors['new_status'] = 'Invalid status transition for current service status.'

        if errors:
            return render(request, 'technician_update_service_status.html', {
                'technician': technician,
                'service': service,
                'errors': errors,
                'form_data': request.POST,
                'status_choices': status_choices,
            })

        service.status = new_status
        service.save(update_fields=['status'])
        messages.success(request, 'Service status updated successfully.')
        return redirect('technician_service_status')

    return render(request, 'technician_update_service_status.html', {
        'technician': technician,
        'service': service,
        'status_choices': status_choices,
        'form_data': {},
    })


def technician_edit_booking(request, service_id):
    from datetime import date as date_cls

    if 'technician_id' not in request.session:
        return redirect('login')

    try:
        technician = Technician.objects.get(id=request.session['technician_id'])
    except Technician.DoesNotExist:
        request.session.flush()
        return redirect('login')

    try:
        service = Service.objects.select_related('customer', 'property').get(id=service_id)
    except Service.DoesNotExist:
        messages.error(request, 'Service record not found.')
        return redirect('technician_service_status')

    if service.status not in {'For Confirmation', 'For Inspection', 'For Treatment'}:
        messages.error(request, 'Edit booking is only available for For Confirmation, For Inspection, or For Treatment statuses.')
        return redirect('technician_service_status')

    customer_properties = Property.objects.filter(customer=service.customer)
    is_treatment = service.status == 'For Treatment'
    treatment_service_choices = [choice for choice in Service.PREFERRED_SERVICE_CHOICES if choice[0] != 'Other']

    if request.method == 'POST':
        if request.POST.get('action') == 'cancel':
            return redirect('technician_service_status')

        errors = {}
        booking_date = request.POST.get('date', '').strip()
        time_slot = request.POST.get('time_slot', '').strip()

        if not booking_date:
            errors['date'] = 'Required fields must be filled in.'
        if not time_slot:
            errors['time_slot'] = 'Required fields must be filled in.'

        if is_treatment:
            treatment_service = request.POST.get('treatment_service', '').strip()
            if not treatment_service:
                errors['treatment_service'] = 'Required fields must be filled in.'
        else:
            property_id = request.POST.get('property_id', '').strip()
            preferred_service = request.POST.get('preferred_service', '').strip()
            pest_problem = request.POST.get('pest_problem', '').strip()

            if not property_id:
                errors['property_id'] = 'Required fields must be filled in.'
            if not preferred_service:
                errors['preferred_service'] = 'Required fields must be filled in.'
            if not pest_problem:
                errors['pest_problem'] = 'Required fields must be filled in.'

            property_obj = None
            if property_id:
                property_obj = customer_properties.filter(id=property_id).first()
                if not property_obj:
                    errors['property_id'] = 'Invalid property selected.'

        if errors:
            return render(request, 'technician_edit_booking.html', {
                'technician': technician,
                'service': service,
                'is_treatment': is_treatment,
                'customer_properties': customer_properties,
                'treatment_service_choices': treatment_service_choices,
                'errors': errors,
                'form_data': request.POST,
                'time_slot_choices': Service.TIME_SLOT_CHOICES,
                'service_choices': Service.PREFERRED_SERVICE_CHOICES,
                'pest_choices': Service.PEST_PROBLEM_CHOICES,
                'today': date_cls.today().isoformat(),
            })

        if is_treatment:
            latest_booking = service.treatment_bookings.order_by('-created_at').first()
            if latest_booking:
                latest_booking.treatment_service = treatment_service
                latest_booking.date = booking_date
                latest_booking.time_slot = time_slot
                latest_booking.save(update_fields=['treatment_service', 'date', 'time_slot'])
            else:
                TreatmentBooking.objects.create(
                    service=service,
                    treatment_service=treatment_service,
                    date=booking_date,
                    time_slot=time_slot,
                )

            service.preferred_service = treatment_service
            service.date = booking_date
            service.confirmed_date = booking_date
            service.treatment_confirmed_date = booking_date
            service.time_slot = time_slot
            service.save(update_fields=['preferred_service', 'date', 'confirmed_date', 'treatment_confirmed_date', 'time_slot'])
        else:
            service.property = property_obj
            service.preferred_service = preferred_service
            service.pest_problem = pest_problem
            service.date = booking_date
            service.inspection_confirmed_date = booking_date
            service.time_slot = time_slot
            service.save(update_fields=['property', 'preferred_service', 'pest_problem', 'date', 'inspection_confirmed_date', 'time_slot'])

        messages.success(request, 'Booking updated successfully.')
        return redirect('technician_service_status')

    form_data = {
        'property_id': str(service.property_id),
        'preferred_service': service.preferred_service,
        'pest_problem': service.pest_problem,
        'date': service.date,
        'time_slot': service.time_slot,
        'treatment_service': service.preferred_service,
    }

    latest_booking = service.treatment_bookings.order_by('-created_at').first()
    if is_treatment and latest_booking:
        form_data.update({
            'date': latest_booking.date,
            'time_slot': latest_booking.time_slot,
            'treatment_service': latest_booking.treatment_service,
        })

    return render(request, 'technician_edit_booking.html', {
        'technician': technician,
        'service': service,
        'is_treatment': is_treatment,
        'customer_properties': customer_properties,
        'treatment_service_choices': treatment_service_choices,
        'form_data': form_data,
        'time_slot_choices': Service.TIME_SLOT_CHOICES,
        'service_choices': Service.PREFERRED_SERVICE_CHOICES,
        'pest_choices': Service.PEST_PROBLEM_CHOICES,
        'today': date_cls.today().isoformat(),
    })


def technician_delete_booking(request, service_id):
    if 'technician_id' not in request.session:
        return redirect('login')

    if request.method != 'POST':
        return redirect('technician_service_status')

    try:
        service = Service.objects.get(id=service_id)
    except Service.DoesNotExist:
        messages.error(request, 'Service record not found.')
        return redirect('technician_service_status')

    if service.status not in {'For Confirmation', 'For Inspection', 'For Treatment'}:
        messages.error(request, 'Only services with For Confirmation, For Inspection, or For Treatment status can be deleted.')
        return redirect('technician_service_status')

    service.delete()
    messages.success(request, 'Service deleted successfully.')
    return redirect('technician_service_status')


def technician_service_history(request):
    if 'technician_id' not in request.session:
        return redirect('login')

    return render(request, 'technician_placeholder.html', {'page_title': 'Service History'})


def technician_service_reports(request):
    if 'technician_id' not in request.session:
        return redirect('login')

    try:
        technician = Technician.objects.get(id=request.session['technician_id'])
    except Technician.DoesNotExist:
        request.session.flush()
        return redirect('login')

    reports = ServiceReport.objects.select_related(
        'service__customer', 'service__property'
    ).order_by('-created_at')

    return render(request, 'technician_service_reports.html', {
        'technician': technician,
        'reports': reports,
    })


def _parse_report_json(raw_payload):
    if not raw_payload:
        return []
    try:
        parsed = json.loads(raw_payload)
        return parsed if isinstance(parsed, list) else []
    except (TypeError, ValueError):
        return []


def _clean_chemical_rows(raw_rows, chemical_map=None):
    cleaned_rows = []
    has_invalid = False
    allowed_map = chemical_map or {}

    for row in raw_rows:
        if not isinstance(row, dict):
            continue

        chemical_id_raw = str(row.get('chemical_id') or '').strip()
        amount_raw = str(row.get('amount') or '').strip()

        if not (chemical_id_raw or amount_raw):
            continue

        if not (chemical_id_raw and amount_raw):
            has_invalid = True
            continue

        try:
            chemical_id = int(chemical_id_raw)
        except (TypeError, ValueError):
            has_invalid = True
            continue

        chemical_data = allowed_map.get(chemical_id)
        if not chemical_data:
            has_invalid = True
            continue

        try:
            amount_value = Decimal(amount_raw)
            if amount_value <= 0:
                has_invalid = True
                continue
        except (InvalidOperation, ValueError):
            has_invalid = True
            continue

        cleaned_rows.append({
            'chemical_id': chemical_id,
            'chemical_name': chemical_data['name'],
            'unit_measure': chemical_data['standard_unit_measure'],
            'amount': amount_value,
        })

    return cleaned_rows, has_invalid


def _clean_area_rows(raw_rows):
    cleaned_rows = []
    has_invalid = False
    infestation_values = {'Low', 'Medium', 'High'}

    for row in raw_rows:
        if not isinstance(row, dict):
            continue

        area_name = (row.get('area_name') or '').strip()
        infestation_level = (row.get('infestation_level') or '').strip()
        spray = bool(row.get('spray'))
        mist = bool(row.get('mist'))
        rat_bait = bool(row.get('rat_bait'))
        powder = bool(row.get('powder'))
        remarks = (row.get('remarks') or '').strip()
        recommendation = (row.get('recommendation') or '').strip()

        has_any_input = (
            area_name
            or infestation_level
            or spray
            or mist
            or rat_bait
            or powder
            or remarks
            or recommendation
        )

        if not has_any_input:
            continue

        if not area_name or infestation_level not in infestation_values:
            has_invalid = True
            continue

        cleaned_rows.append({
            'area_name': area_name,
            'infestation_level': infestation_level,
            'spray': spray,
            'mist': mist,
            'rat_bait': rat_bait,
            'powder': powder,
            'remarks': remarks,
            'recommendation': recommendation,
        })

    return cleaned_rows, has_invalid


def technician_create_service_report(request):
    if 'technician_id' not in request.session:
        return redirect('login')

    try:
        technician = Technician.objects.get(id=request.session['technician_id'])
    except Technician.DoesNotExist:
        request.session.flush()
        return redirect('login')

    draft = request.session.get('tech_service_report_draft', {})
    selected_service_id = draft.get('service_id')
    active_chemicals = list(Chemical.objects.filter(is_active=True).order_by('name'))
    chemical_map = {
        chemical.id: {
            'name': chemical.name,
            'standard_unit_measure': chemical.standard_unit_measure,
        }
        for chemical in active_chemicals
    }
    chemical_choices = [
        {
            'value': str(chemical.id),
            'label': chemical.name,
            'standard_unit_measure': chemical.standard_unit_measure,
        }
        for chemical in active_chemicals
    ]

    default_chemicals = draft.get('chemicals') or [
        {'chemical_id': '', 'amount': ''}
    ]
    default_areas = draft.get('treated_areas') or [
        {
            'area_name': '',
            'infestation_level': 'Low',
            'spray': False,
            'mist': False,
            'rat_bait': False,
            'powder': False,
            'remarks': '',
            'recommendation': '',
        }
    ]

    selectable_services = Service.objects.filter(
        status='Ongoing Treatment',
        service_report__isnull=True,
    ).select_related('customer', 'property').order_by('-confirmed_date', '-date', '-created_at')

    def render_step_one(errors=None):
        return render(request, 'technician_create_service_report.html', {
            'technician': technician,
            'step': 'select',
            'services': selectable_services,
            'errors': errors or {},
            'selected_service_id': str(selected_service_id or ''),
        })

    def render_step_two(service, errors=None, chemicals=None, treated_areas=None):
        return render(request, 'technician_create_service_report.html', {
            'technician': technician,
            'step': 'details',
            'service': service,
            'errors': errors or {},
            'chemicals_json': json.dumps(chemicals if chemicals is not None else default_chemicals),
            'treated_areas_json': json.dumps(treated_areas if treated_areas is not None else default_areas),
            'chemical_choices_json': json.dumps(chemical_choices),
        })

    if request.method == 'POST':
        action = request.POST.get('action', '').strip()
        step = request.POST.get('step', 'select').strip()

        if action == 'confirm_cancel':
            request.session.pop('tech_service_report_draft', None)
            return redirect('technician_home')

        if step == 'select':
            if action == 'continue':
                chosen_service_id = request.POST.get('selected_service_id', '').strip()
                selected_service = selectable_services.filter(id=chosen_service_id).first()

                if not selected_service:
                    return render_step_one({'selected_service': 'Please select an Ongoing Treatment service record.'})

                if str(selected_service_id or '') != str(selected_service.id):
                    default_chemicals = [{'chemical_id': '', 'amount': ''}]
                    default_areas = [{
                        'area_name': '',
                        'infestation_level': 'Low',
                        'spray': False,
                        'mist': False,
                        'rat_bait': False,
                        'powder': False,
                        'remarks': '',
                        'recommendation': '',
                    }]

                request.session['tech_service_report_draft'] = {
                    'service_id': selected_service.id,
                    'chemicals': default_chemicals,
                    'treated_areas': default_areas,
                }
                request.session.modified = True
                return render_step_two(selected_service)

            return render_step_one()

        if step == 'details':
            selected_service = None
            if selected_service_id:
                selected_service = selectable_services.filter(id=selected_service_id).first()

            if not selected_service:
                request.session.pop('tech_service_report_draft', None)
                return render_step_one({'selected_service': 'Selected service is no longer available for report creation.'})

            raw_chemicals = _parse_report_json(request.POST.get('chemicals_json'))
            raw_areas = _parse_report_json(request.POST.get('treated_areas_json'))

            request.session['tech_service_report_draft'] = {
                'service_id': selected_service.id,
                'chemicals': raw_chemicals,
                'treated_areas': raw_areas,
            }
            request.session.modified = True

            if action == 'go_back':
                return render_step_one()

            if action == 'submit':
                errors = {}
                chemicals, chemical_has_invalid = _clean_chemical_rows(raw_chemicals, chemical_map=chemical_map)
                treated_areas, area_has_invalid = _clean_area_rows(raw_areas)

                if not chemicals:
                    errors['chemicals'] = 'At least one chemical used must be filled in.'
                elif chemical_has_invalid:
                    errors['chemicals'] = 'Please complete each filled chemical row with valid values.'

                if not treated_areas:
                    errors['treated_areas'] = 'At least one area must be filled in.'
                elif area_has_invalid:
                    errors['treated_areas'] = 'Please complete each filled treated area row with valid values.'

                if errors:
                    return render_step_two(selected_service, errors=errors, chemicals=raw_chemicals, treated_areas=raw_areas)

                if ServiceReport.objects.filter(service=selected_service).exists():
                    request.session.pop('tech_service_report_draft', None)
                    messages.error(request, 'A service report for this service already exists.')
                    return redirect('technician_service_reports')

                with transaction.atomic():
                    report = ServiceReport.objects.create(
                        service=selected_service,
                        technician=technician,
                    )

                    ServiceReportChemical.objects.bulk_create([
                        ServiceReportChemical(
                            report=report,
                            chemical_id=row['chemical_id'],
                            chemical_name=row['chemical_name'],
                            unit_measure=row['unit_measure'],
                            amount=row['amount'],
                        )
                        for row in chemicals
                    ])

                    ServiceReportArea.objects.bulk_create([
                        ServiceReportArea(
                            report=report,
                            area_name=row['area_name'],
                            infestation_level=row['infestation_level'],
                            spray=row['spray'],
                            mist=row['mist'],
                            rat_bait=row['rat_bait'],
                            powder=row['powder'],
                            remarks=row['remarks'],
                            recommendation=row['recommendation'],
                        )
                        for row in treated_areas
                    ])

                request.session.pop('tech_service_report_draft', None)
                return render(request, 'technician_create_service_report.html', {
                    'technician': technician,
                    'step': 'success',
                })

            return render_step_two(selected_service, chemicals=raw_chemicals, treated_areas=raw_areas)

    if selected_service_id:
        selected_service = selectable_services.filter(id=selected_service_id).first()
        if selected_service:
            return render_step_two(selected_service)
        request.session.pop('tech_service_report_draft', None)

    return render_step_one()


def technician_view_service_report(request, report_id):
    if 'technician_id' not in request.session:
        return redirect('login')

    report = ServiceReport.objects.select_related(
        'service__customer', 'service__property', 'technician'
    ).prefetch_related('chemicals', 'treated_areas').filter(id=report_id).first()

    if not report:
        messages.error(request, 'Service report not found.')
        return redirect('technician_service_reports')

    return render(request, 'service_report_view.html', {
        'report': report,
        'role': 'technician',
        'back_url_name': 'technician_service_reports',
    })


def _service_report_redirect_name(request):
    if request.session.get('technician_id'):
        return 'technician_service_reports'
    return 'om_service_reports'


def edit_service_report(request, report_id):
    if 'technician_id' not in request.session and 'om_id' not in request.session:
        return redirect('login')

    report = ServiceReport.objects.select_related(
        'service__customer', 'service__property'
    ).prefetch_related('chemicals', 'treated_areas').filter(id=report_id).first()

    active_chemicals = list(Chemical.objects.filter(is_active=True).order_by('name'))
    chemical_map = {
        chemical.id: {
            'name': chemical.name,
            'standard_unit_measure': chemical.standard_unit_measure,
        }
        for chemical in active_chemicals
    }
    chemical_choices = [
        {
            'value': str(chemical.id),
            'label': chemical.name,
            'standard_unit_measure': chemical.standard_unit_measure,
        }
        for chemical in active_chemicals
    ]

    if not report:
        messages.error(request, 'Service report not found.')
        return redirect(_service_report_redirect_name(request))

    if request.method == 'POST':
        if request.POST.get('action') == 'cancel':
            return redirect(_service_report_redirect_name(request))

        raw_chemicals = _parse_report_json(request.POST.get('chemicals_json'))
        raw_areas = _parse_report_json(request.POST.get('treated_areas_json'))

        errors = {}
        chemicals, chemical_has_invalid = _clean_chemical_rows(raw_chemicals, chemical_map=chemical_map)
        treated_areas, area_has_invalid = _clean_area_rows(raw_areas)

        if not chemicals:
            errors['chemicals'] = 'At least one chemical used must be filled in.'
        elif chemical_has_invalid:
            errors['chemicals'] = 'Please complete each filled chemical row with valid values.'

        if not treated_areas:
            errors['treated_areas'] = 'At least one area must be filled in.'
        elif area_has_invalid:
            errors['treated_areas'] = 'Please complete each filled treated area row with valid values.'

        if errors:
            return render(request, 'edit_service_report.html', {
                'report': report,
                'errors': errors,
                'chemicals_json': json.dumps(raw_chemicals),
                'treated_areas_json': json.dumps(raw_areas),
                'chemical_choices_json': json.dumps(chemical_choices),
                'back_url_name': _service_report_redirect_name(request),
            })

        with transaction.atomic():
            report.chemicals.all().delete()
            report.treated_areas.all().delete()

            ServiceReportChemical.objects.bulk_create([
                ServiceReportChemical(
                    report=report,
                    chemical_id=row['chemical_id'],
                    chemical_name=row['chemical_name'],
                    unit_measure=row['unit_measure'],
                    amount=row['amount'],
                )
                for row in chemicals
            ])

            ServiceReportArea.objects.bulk_create([
                ServiceReportArea(
                    report=report,
                    area_name=row['area_name'],
                    infestation_level=row['infestation_level'],
                    spray=row['spray'],
                    mist=row['mist'],
                    rat_bait=row['rat_bait'],
                    powder=row['powder'],
                    remarks=row['remarks'],
                    recommendation=row['recommendation'],
                )
                for row in treated_areas
            ])

        messages.success(request, 'Service report updated successfully.')
        return redirect(_service_report_redirect_name(request))

    return render(request, 'edit_service_report.html', {
        'report': report,
        'errors': {},
        'chemicals_json': json.dumps([
            {
                'chemical_id': str(chemical.chemical_id) if chemical.chemical_id else '',
                'amount': str(chemical.amount),
            }
            for chemical in report.chemicals.all()
        ]),
        'treated_areas_json': json.dumps([
            {
                'area_name': area.area_name,
                'infestation_level': area.infestation_level,
                'spray': area.spray,
                'mist': area.mist,
                'rat_bait': area.rat_bait,
                'powder': area.powder,
                'remarks': area.remarks,
                'recommendation': area.recommendation,
            }
            for area in report.treated_areas.all()
        ]),
        'back_url_name': _service_report_redirect_name(request),
        'chemical_choices_json': json.dumps(chemical_choices),
    })


def delete_service_report(request, report_id):
    if 'technician_id' not in request.session and 'om_id' not in request.session:
        return redirect('login')

    if request.method != 'POST':
        return redirect(_service_report_redirect_name(request))

    report = ServiceReport.objects.select_related('service').filter(id=report_id).first()
    if not report:
        messages.error(request, 'Service report not found.')
        return redirect(_service_report_redirect_name(request))

    service = report.service
    report.delete()
    service.status = 'Ongoing Treatment'
    service.save(update_fields=['status'])

    messages.success(request, 'Service report deleted successfully.')
    return redirect(_service_report_redirect_name(request))


def om_view_service_report(request, report_id):
    if 'om_id' not in request.session:
        return redirect('login')

    report = ServiceReport.objects.select_related(
        'service__customer', 'service__property', 'technician'
    ).prefetch_related('chemicals', 'treated_areas').filter(id=report_id).first()

    if not report:
        messages.error(request, 'Service report not found.')
        return redirect('om_service_reports')

    return render(request, 'service_report_view.html', {
        'report': report,
        'role': 'om',
        'back_url_name': 'om_service_reports',
    })


def om_service_status(request):
    """Display OM service status page with ongoing services."""
    if 'om_id' not in request.session:
        return redirect('login')

    try:
        om = OperationsManager.objects.get(id=request.session['om_id'])
    except OperationsManager.DoesNotExist:
        request.session.flush()
        return redirect('login')

    created_order = request.GET.get('created_order', 'newest').strip().lower()
    if created_order not in {'newest', 'oldest'}:
        created_order = 'newest'
    order_by = 'created_at' if created_order == 'oldest' else '-created_at'

    status_order_cases = [
        When(status=status_value, then=position)
        for position, status_value in enumerate(OM_STATUS_WORKFLOW)
    ]

    services_qs = Service.objects.exclude(
        status__in=['Completed', 'Cancelled']
    ).select_related('customer', 'property', 'service_report').annotate(
        workflow_order=Case(
            *status_order_cases,
            default=len(OM_STATUS_WORKFLOW),
            output_field=IntegerField(),
        )
    ).order_by(order_by, 'workflow_order')

    unseen_confirmation_ids = list(
        services_qs.filter(status='For Confirmation', om_seen_at__isnull=True).values_list('id', flat=True)
    )
    if unseen_confirmation_ids:
        Service.objects.filter(id__in=unseen_confirmation_ids).update(om_seen_at=timezone.now())

    services = list(services_qs)

    return render(request, 'om_service_status.html', {
        'om': om,
        'services': services,
        'created_order': created_order,
    })


def om_update_service_status(request, service_id):
    """Handle OM service status update (UC 14)."""
    if 'om_id' not in request.session:
        return redirect('login')

    try:
        om = OperationsManager.objects.get(id=request.session['om_id'])
    except OperationsManager.DoesNotExist:
        request.session.flush()
        return redirect('login')

    try:
        service = Service.objects.select_related('customer').get(id=service_id)
    except Service.DoesNotExist:
        messages.error(request, 'Service record not found.')
        return redirect('om_service_status')

    allowed_next_statuses = OM_STATUS_TRANSITIONS.get(service.status, [])
    status_choices = [(value, value) for value in allowed_next_statuses]
    allowed_statuses = set(allowed_next_statuses)
    allowed_time_slots = {value for value, _ in Service.TIME_SLOT_CHOICES}

    if request.method == 'POST':
        if request.POST.get('action') == 'cancel':
            return redirect('om_service_status')

        new_status = request.POST.get('new_status', '').strip()
        inspection_confirmed_date = request.POST.get('inspection_confirmed_date', '').strip()
        inspection_confirmed_time = request.POST.get('inspection_confirmed_time', '').strip()
        treatment_confirmed_date = request.POST.get('treatment_confirmed_date', '').strip()
        treatment_confirmed_time = request.POST.get('treatment_confirmed_time', '').strip()
        errors = {}

        if not new_status:
            errors['new_status'] = 'Required fields must be filled in.'
        elif new_status not in allowed_statuses:
            errors['new_status'] = 'Invalid status transition for current service status.'

        if new_status == 'For Inspection' and not inspection_confirmed_date:
            errors['inspection_confirmed_date'] = 'Required fields must be filled in.'

        if new_status == 'For Inspection' and not inspection_confirmed_time:
            errors['inspection_confirmed_time'] = 'Required fields must be filled in.'
        elif inspection_confirmed_time and inspection_confirmed_time not in allowed_time_slots:
            errors['inspection_confirmed_time'] = 'Invalid time slot selected.'

        if new_status == 'For Treatment' and not treatment_confirmed_date:
            errors['treatment_confirmed_date'] = 'Required fields must be filled in.'

        if new_status == 'For Treatment' and not treatment_confirmed_time:
            errors['treatment_confirmed_time'] = 'Required fields must be filled in.'
        elif treatment_confirmed_time and treatment_confirmed_time not in allowed_time_slots:
            errors['treatment_confirmed_time'] = 'Invalid time slot selected.'

        if errors:
            return render(request, 'om_update_service_status.html', {
                'om': om,
                'service': service,
                'errors': errors,
                'form_data': request.POST,
                'status_choices': status_choices,
                'time_slot_choices': Service.TIME_SLOT_CHOICES,
            })

        update_fields = ['status']
        service.status = new_status

        if new_status == 'For Inspection':
            service.inspection_confirmed_date = inspection_confirmed_date
            service.inspection_confirmed_time = inspection_confirmed_time
            service.confirmed_date = inspection_confirmed_date
            update_fields.extend(['inspection_confirmed_date', 'inspection_confirmed_time', 'confirmed_date'])

        if new_status == 'For Treatment':
            service.treatment_confirmed_date = treatment_confirmed_date
            service.treatment_confirmed_time = treatment_confirmed_time
            service.confirmed_date = treatment_confirmed_date
            update_fields.extend(['treatment_confirmed_date', 'treatment_confirmed_time', 'confirmed_date'])

        service.save(update_fields=update_fields)
        messages.success(request, 'Service status updated successfully.')
        return redirect('om_service_status')

    return render(request, 'om_update_service_status.html', {
        'om': om,
        'service': service,
        'status_choices': status_choices,
        'time_slot_choices': Service.TIME_SLOT_CHOICES,
        'form_data': {},
    })


def om_edit_booking(request, service_id):
    """Handle OM booking edit for inspection/treatment (UC 15)."""
    from datetime import date as date_cls

    if 'om_id' not in request.session:
        return redirect('login')

    try:
        om = OperationsManager.objects.get(id=request.session['om_id'])
    except OperationsManager.DoesNotExist:
        request.session.flush()
        return redirect('login')

    try:
        service = Service.objects.select_related('customer', 'property').get(id=service_id)
    except Service.DoesNotExist:
        messages.error(request, 'Service record not found.')
        return redirect('om_service_status')

    if service.status not in {'For Confirmation', 'For Inspection', 'For Treatment', 'For Booking'}:
        messages.error(request, 'Edit booking is only available for For Confirmation, For Inspection, For Booking, or For Treatment statuses.')
        return redirect('om_service_status')

    customer_properties = Property.objects.filter(customer=service.customer)
    is_treatment = service.status in {'For Treatment', 'For Booking'}
    treatment_service_choices = [choice for choice in Service.PREFERRED_SERVICE_CHOICES if choice[0] != 'Other']

    if request.method == 'POST':
        if request.POST.get('action') == 'cancel':
            return redirect('om_service_status')

        errors = {}
        booking_date = request.POST.get('date', '').strip()
        time_slot = request.POST.get('time_slot', '').strip()

        if not booking_date:
            errors['date'] = 'Required fields must be filled in.'
        if not time_slot:
            errors['time_slot'] = 'Required fields must be filled in.'

        if is_treatment:
            treatment_service = request.POST.get('treatment_service', '').strip()
            if not treatment_service:
                errors['treatment_service'] = 'Required fields must be filled in.'
        else:
            property_id = request.POST.get('property_id', '').strip()
            preferred_service = request.POST.get('preferred_service', '').strip()
            pest_problem = request.POST.get('pest_problem', '').strip()

            if not property_id:
                errors['property_id'] = 'Required fields must be filled in.'
            if not preferred_service:
                errors['preferred_service'] = 'Required fields must be filled in.'
            if not pest_problem:
                errors['pest_problem'] = 'Required fields must be filled in.'

            property_obj = None
            if property_id:
                property_obj = customer_properties.filter(id=property_id).first()
                if not property_obj:
                    errors['property_id'] = 'Invalid property selected.'

        if errors:
            return render(request, 'om_edit_booking.html', {
                'om': om,
                'service': service,
                'is_treatment': is_treatment,
                'customer_properties': customer_properties,
                'treatment_service_choices': treatment_service_choices,
                'errors': errors,
                'form_data': request.POST,
                'time_slot_choices': Service.TIME_SLOT_CHOICES,
                'service_choices': Service.PREFERRED_SERVICE_CHOICES,
                'pest_choices': Service.PEST_PROBLEM_CHOICES,
                'today': date_cls.today().isoformat(),
            })

        if is_treatment:
            latest_booking = service.treatment_bookings.order_by('-created_at').first()
            if latest_booking:
                latest_booking.treatment_service = treatment_service
                latest_booking.date = booking_date
                latest_booking.time_slot = time_slot
                latest_booking.save(update_fields=['treatment_service', 'date', 'time_slot'])
            else:
                TreatmentBooking.objects.create(
                    service=service,
                    treatment_service=treatment_service,
                    date=booking_date,
                    time_slot=time_slot,
                )

            service.preferred_service = treatment_service
            service.date = booking_date
            service.confirmed_date = booking_date
            service.treatment_confirmed_date = booking_date
            service.time_slot = time_slot
            service.save(update_fields=['preferred_service', 'date', 'confirmed_date', 'treatment_confirmed_date', 'time_slot'])
        else:
            service.property = property_obj
            service.preferred_service = preferred_service
            service.pest_problem = pest_problem
            service.date = booking_date
            service.confirmed_date = booking_date
            service.inspection_confirmed_date = booking_date
            service.time_slot = time_slot
            update_fields = ['property', 'preferred_service', 'pest_problem', 'date', 'confirmed_date', 'inspection_confirmed_date', 'time_slot']
            if service.status == 'For Confirmation':
                service.status = 'For Inspection'
                update_fields.append('status')
            service.save(update_fields=update_fields)

        messages.success(request, 'Booking updated successfully.')
        return redirect('om_service_status')

    form_data = {
        'property_id': str(service.property_id),
        'preferred_service': service.preferred_service,
        'pest_problem': service.pest_problem,
        'date': service.date,
        'time_slot': service.time_slot,
        'treatment_service': service.preferred_service,
    }

    latest_booking = service.treatment_bookings.order_by('-created_at').first()
    if is_treatment and latest_booking:
        form_data.update({
            'date': latest_booking.date,
            'time_slot': latest_booking.time_slot,
            'treatment_service': latest_booking.treatment_service,
        })

    return render(request, 'om_edit_booking.html', {
        'om': om,
        'service': service,
        'is_treatment': is_treatment,
        'customer_properties': customer_properties,
        'treatment_service_choices': treatment_service_choices,
        'form_data': form_data,
        'time_slot_choices': Service.TIME_SLOT_CHOICES,
        'service_choices': Service.PREFERRED_SERVICE_CHOICES,
        'pest_choices': Service.PEST_PROBLEM_CHOICES,
        'today': date_cls.today().isoformat(),
    })


def om_view_booking(request, service_id):
    """Display read-only booking details for OM."""
    if 'om_id' not in request.session:
        return redirect('login')

    try:
        om = OperationsManager.objects.get(id=request.session['om_id'])
    except OperationsManager.DoesNotExist:
        request.session.flush()
        return redirect('login')

    service = Service.objects.select_related('customer', 'property').filter(id=service_id).first()
    if not service:
        messages.error(request, 'Service record not found.')
        return redirect('om_service_status')

    return render(request, 'view_booking.html', {
        'om': om,
        'service': service,
        'identified_as': 'Operations Manager',
        'back_url_name': 'om_service_status',
    })


def om_delete_booking(request, service_id):
    """Handle OM booking deletion (UC 16)."""
    if 'om_id' not in request.session:
        return redirect('login')

    if request.method != 'POST':
        return redirect('om_service_status')

    try:
        service = Service.objects.get(id=service_id)
    except Service.DoesNotExist:
        messages.error(request, 'Service record not found.')
        return redirect('om_service_status')

    if service.status not in {'For Confirmation', 'For Inspection', 'For Treatment', 'For Booking'}:
        messages.error(request, 'Only services with For Confirmation, For Inspection, For Booking, or For Treatment status can be deleted.')
        return redirect('om_service_status')

    service.delete()
    messages.success(request, 'Service deleted successfully.')
    return redirect('om_service_status')


def om_book_treatment(request, service_id):
    """Handle OM treatment booking (UC 11)."""
    from datetime import date as date_cls

    if 'om_id' not in request.session:
        return redirect('login')

    try:
        om = OperationsManager.objects.get(id=request.session['om_id'])
    except OperationsManager.DoesNotExist:
        request.session.flush()
        return redirect('login')

    try:
        service = Service.objects.select_related('customer', 'property').get(id=service_id)
    except Service.DoesNotExist:
        messages.error(request, 'Service record not found.')
        return redirect('om_service_status')

    if service.status not in {'For Booking', 'Estimated Bill Created'}:
        messages.error(request, 'Book Treatment is only available for services with For Booking status.')
        return redirect('om_service_status')

    treatment_service_choices = [
        choice for choice in Service.PREFERRED_SERVICE_CHOICES if choice[0] != 'Other'
    ]

    if request.method == 'POST':
        if request.POST.get('action') == 'cancel':
            return redirect('om_service_status')

        selected_treatment_services = [
            value.strip()
            for value in request.POST.getlist('treatment_service')
            if value.strip()
        ]
        booking_date = request.POST.get('date', '').strip()
        time_slot = request.POST.get('time_slot', '').strip()

        errors = {}
        if not selected_treatment_services:
            errors['treatment_service'] = 'Required fields must be filled in.'
        if not booking_date:
            errors['date'] = 'Required fields must be filled in.'
        if not time_slot:
            errors['time_slot'] = 'Required fields must be filled in.'

        if not errors:
            TreatmentBooking.objects.bulk_create([
                TreatmentBooking(
                    service=service,
                    treatment_service=treatment_service,
                    date=booking_date,
                    time_slot=time_slot,
                )
                for treatment_service in selected_treatment_services
            ])
            service.preferred_service = ', '.join(selected_treatment_services)
            service.status = 'For Treatment'
            service.confirmed_date = booking_date
            service.treatment_confirmed_date = booking_date
            service.save(update_fields=['preferred_service', 'status', 'confirmed_date', 'treatment_confirmed_date'])

            return render(request, 'om_book_treatment.html', {
                'om': om,
                'service': service,
                'success': True,
                'selected_treatments': selected_treatment_services,
                'treatment_service_choices': treatment_service_choices,
                'time_slot_choices': Service.TIME_SLOT_CHOICES,
                'today': date_cls.today().isoformat(),
            })

        return render(request, 'om_book_treatment.html', {
            'om': om,
            'service': service,
            'errors': errors,
            'form_data': request.POST,
            'selected_treatments': selected_treatment_services,
            'treatment_service_choices': treatment_service_choices,
            'time_slot_choices': Service.TIME_SLOT_CHOICES,
            'today': date_cls.today().isoformat(),
        })

    return render(request, 'om_book_treatment.html', {
        'om': om,
        'service': service,
        'form_data': {
            'treatment_service': [],
        },
        'selected_treatments': [],
        'treatment_service_choices': treatment_service_choices,
        'time_slot_choices': Service.TIME_SLOT_CHOICES,
        'today': date_cls.today().isoformat(),
    })
