from django.shortcuts import render, redirect
from django.db import transaction
from django.db.models import Case, When, IntegerField, Count, Max, Q
from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from decimal import Decimal, InvalidOperation
from datetime import datetime
import json
import re
from collections import defaultdict
from urllib.parse import quote_plus
from .models import (
    Customer,
    Property,
    Service,
    OperationsManager,
    SalesRepresentative,
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
    PaymentProof,
    RemittanceRecord,
    ServiceFormOption,
)
from .forms import CustomerRegistrationForm


def _noop_message(*args, **kwargs):
    return None


class _SilentMessages:
    success = staticmethod(_noop_message)
    error = staticmethod(_noop_message)
    info = staticmethod(_noop_message)
    warning = staticmethod(_noop_message)


messages = _SilentMessages()


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
    'Ongoing Inspection': [],
    'Estimated Bill Created': ['For Treatment Booking'],
    'For Treatment Booking': ['For Treatment'],
    'For Treatment': ['Ongoing Treatment'],
    'Ongoing Treatment': [],
    'Pending Payment': ['Ongoing Treatment', 'Payment Confirmed',],
    'Payment Confirmed': ['Completed'],
}


SERVICE_FORM_FIELD_CATALOG = {
    'Inspection': ['Type of Property', 'Preferred Service', 'Pest Problems'],
    'Treatment': ['Treatment Service'],
    'Service Report Submission': ['Service Done', 'Chemicals Used', 'Levels of Infestation'],
    'Payment Proof Submission': ['Bank Used for Payment', 'Payment Type'],
}


TREATMENT_SERVICE_PREDEFINED_OPTIONS = [
    'Termite Control',
    'Cockroach Control',
    'General Pest Control Treatment',
    'Mosquito Control',
    'Rodent Control',
    'Bed Bug Treatment',
]

TREATMENT_SERVICE_METADATA = {
    'Termite Control': {
        'description': 'Targeted treatment for active termite activity.',
        'rate': Decimal('3000.00'),
        'problem_text': 'Active termite presence or suspected colony activity.',
        'recommendation_text': 'Apply targeted termiticide treatment and monitor affected areas.',
        'target_pest': 'Termites',
        'application_method': 'Injection and perimeter application',
        'additional_information': 'Inspect wall voids and timber contact points.',
        'dilution_rate': '1:10',
    },
    'Cockroach Control': {
        'description': 'Focused control for cockroach infestations.',
        'rate': Decimal('2000.00'),
        'problem_text': 'Cockroach sightings in kitchens, drains, and storage areas.',
        'recommendation_text': 'Use residual spray and gel baiting for sustained control.',
        'target_pest': 'Cockroaches',
        'application_method': 'Residual spray and bait placement',
        'additional_information': 'Treat cracks, crevices, and harborage points.',
        'dilution_rate': '1:20',
    },
    'General Pest Control Treatment': {
        'description': 'General-purpose treatment for common pests.',
        'rate': Decimal('2500.00'),
        'problem_text': 'General pest activity across common entry and harboring areas.',
        'recommendation_text': 'Apply a broad-spectrum treatment with follow-up inspection.',
        'target_pest': 'General Pests',
        'application_method': 'Surface spray and barrier treatment',
        'additional_information': 'Covers common pest pressure in occupied areas.',
        'dilution_rate': '1:15',
    },
    'Mosquito Control': {
        'description': 'Mosquito population reduction treatment.',
        'rate': Decimal('1800.00'),
        'problem_text': 'Mosquito breeding or resting activity near the property.',
        'recommendation_text': 'Treat breeding sites and perimeter vegetation.',
        'target_pest': 'Mosquitoes',
        'application_method': 'Fogging and residual surface treatment',
        'additional_information': 'Inspect stagnant water and shaded outdoor zones.',
        'dilution_rate': '1:25',
    },
    'Rodent Control': {
        'description': 'Rodent monitoring and control treatment.',
        'rate': Decimal('2200.00'),
        'problem_text': 'Rodent droppings, gnaw marks, or live rodent activity.',
        'recommendation_text': 'Install bait stations and seal entry points.',
        'target_pest': 'Rodents',
        'application_method': 'Baiting and trapping',
        'additional_information': 'Review rooflines, utility penetrations, and storage spaces.',
        'dilution_rate': 'N/A',
    },
    'Bed Bug Treatment': {
        'description': 'Specialized treatment for bed bug infestations.',
        'rate': Decimal('2800.00'),
        'problem_text': 'Bed bug bites, spotting, or infestation in sleeping areas.',
        'recommendation_text': 'Treat mattresses, bed frames, and adjacent furnishings.',
        'target_pest': 'Bed Bugs',
        'application_method': 'Residual spray and targeted crack treatment',
        'additional_information': 'Encourage laundering and heat treatment where appropriate.',
        'dilution_rate': '1:20',
    },
}

FALLBACK_CHEMICAL_NAMES = ['Temprid', 'Maxforce', 'Racumin', 'Muriatic Acid', 'Solignum']
PAYMENT_BANK_DEFAULTS = [
    ('Online Bank Transfer', 'BDO', '0000-0000-0000'),
    ('Online Bank Transfer', 'BPI', '0000-1111-2222'),
    ('Over-the-counter Deposit', 'Landbank', '0000-2222-3333'),
    ('Over-the-counter Deposit', 'Metrobank', '0000-3333-4444'),
    ('E-Wallet Transfer', 'GCash', '0917-000-0000'),
    ('E-Wallet Transfer', 'Maya', '0998-000-0000'),
]


def _unique_preserve_order(values):
    seen = set()
    ordered = []
    for value in values:
        normalized = (value or '').strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(normalized)
    return ordered


def _build_service_form_default_options():
    chemical_names = list(
        Chemical.objects.filter(is_active=True).order_by('name').values_list('name', flat=True)
    )
    chemical_names = _unique_preserve_order(chemical_names) or FALLBACK_CHEMICAL_NAMES

    return {
        ('Inspection', 'Type of Property'): [label for _, label in Property.PROPERTY_TYPE_CHOICES],
        ('Inspection', 'Preferred Service'): TREATMENT_SERVICE_PREDEFINED_OPTIONS,
        ('Inspection', 'Pest Problems'): [label for _, label in Service.PEST_PROBLEM_CHOICES],
        ('Treatment', 'Treatment Service'): TREATMENT_SERVICE_PREDEFINED_OPTIONS,
        ('Service Report Submission', 'Service Done'): TREATMENT_SERVICE_PREDEFINED_OPTIONS,
        ('Service Report Submission', 'Chemicals Used'): chemical_names,
        ('Service Report Submission', 'Levels of Infestation'): [label for _, label in ServiceReportArea.INFESTATION_CHOICES],
        ('Payment Proof Submission', 'Bank Used for Payment'): [name for _, name, _ in PAYMENT_BANK_DEFAULTS],
        ('Payment Proof Submission', 'Payment Type'): ['Online Bank Transfer', 'Over-the-counter Deposit', 'E-Wallet Transfer'],
    }


def _ensure_service_form_default_options():
    default_options = _build_service_form_default_options()
    for (form_section, field_name), option_values in default_options.items():
        for option_value in option_values:
            existing = ServiceFormOption.objects.filter(
                form_section=form_section,
                field_name=field_name,
                option_value__iexact=option_value,
            ).order_by('-is_active', 'id').first()

            if existing:
                update_fields = []
                if existing.option_value != option_value:
                    existing.option_value = option_value
                    update_fields.append('option_value')
                if not existing.is_active:
                    existing.is_active = True
                    update_fields.append('is_active')
                if existing.scoped_option_id is None:
                    last_scoped_id = ServiceFormOption.objects.filter(
                        form_section=form_section,
                        field_name=field_name,
                    ).aggregate(max_id=Max('scoped_option_id')).get('max_id') or 0
                    existing.scoped_option_id = last_scoped_id + 1
                    update_fields.append('scoped_option_id')
                if update_fields:
                    update_fields.append('updated_at')
                    existing.save(update_fields=update_fields)
                continue

            last_scoped_id = ServiceFormOption.objects.filter(
                form_section=form_section,
                field_name=field_name,
            ).aggregate(max_id=Max('scoped_option_id')).get('max_id') or 0

            ServiceFormOption.objects.create(
                form_section=form_section,
                field_name=field_name,
                scoped_option_id=last_scoped_id + 1,
                option_value=option_value,
                is_active=True,
            )

    # Ensure treatment services always have description/rate metadata for table display.
    for service_name, metadata in TREATMENT_SERVICE_METADATA.items():
        option = ServiceFormOption.objects.filter(
            form_section='Treatment',
            field_name='Treatment Service',
            option_value__iexact=service_name,
        ).order_by('-is_active', 'id').first()
        if not option:
            continue

        update_fields = []
        if not option.option_description:
            option.option_description = metadata['description']
            update_fields.append('option_description')
        if option.option_rate is None:
            option.option_rate = metadata['rate']
            update_fields.append('option_rate')
        if not option.problem_text:
            option.problem_text = metadata['problem_text']
            update_fields.append('problem_text')
        if not option.recommendation_text:
            option.recommendation_text = metadata['recommendation_text']
            update_fields.append('recommendation_text')
        if not option.target_pest:
            option.target_pest = metadata['target_pest']
            update_fields.append('target_pest')
        if not option.application_method:
            option.application_method = metadata['application_method']
            update_fields.append('application_method')
        if not option.additional_information:
            option.additional_information = metadata['additional_information']
            update_fields.append('additional_information')
        if not option.dilution_rate:
            option.dilution_rate = metadata['dilution_rate']
            update_fields.append('dilution_rate')
        if update_fields:
            update_fields.append('updated_at')
            option.save(update_fields=update_fields)

    for payment_type, bank_name, account_number in PAYMENT_BANK_DEFAULTS:
        option = ServiceFormOption.objects.filter(
            form_section='Payment Proof Submission',
            field_name='Bank Used for Payment',
            option_value__iexact=bank_name,
        ).order_by('-is_active', 'id').first()
        if not option:
            continue
        update_fields = []
        if not option.option_description:
            option.option_description = payment_type
            update_fields.append('option_description')
        if not option.account_number:
            option.account_number = account_number
            update_fields.append('account_number')
        if update_fields:
            update_fields.append('updated_at')
            option.save(update_fields=update_fields)


def _get_active_service_form_option_values(form_section, field_name, fallback_values=None, excluded_values=None):
    if (form_section, field_name) in {
        ('Inspection', 'Preferred Service'),
        ('Service Report Submission', 'Service Done'),
    }:
        form_section = 'Treatment'
        field_name = 'Treatment Service'

    values = list(
        ServiceFormOption.objects.filter(
            form_section=form_section,
            field_name=field_name,
            is_active=True,
        ).order_by('option_value').values_list('option_value', flat=True)
    )

    if not values and fallback_values:
        values = list(fallback_values)

    values = _unique_preserve_order(values)
    if excluded_values:
        excluded = {value.strip().lower() for value in excluded_values if value}
        values = [value for value in values if value.strip().lower() not in excluded]

    return values


def _get_service_form_choices(form_section, field_name, fallback_values=None, excluded_values=None):
    values = _get_active_service_form_option_values(
        form_section,
        field_name,
        fallback_values=fallback_values,
        excluded_values=excluded_values,
    )
    return [(value, value) for value in values]


def _get_service_form_option_map(form_section, field_name):
    options = ServiceFormOption.objects.filter(
        form_section=form_section,
        field_name=field_name,
        is_active=True,
    ).order_by('option_value')
    return {option.option_value: option for option in options}


def _resolve_back_url(request, default_name, *, fallback_query_param='back'):
    back_url = request.GET.get(fallback_query_param, '').strip()
    if back_url.startswith('/'):
        return back_url
    if back_url.startswith('http://') or back_url.startswith('https://'):
        return reverse(default_name)
    return reverse(default_name)


def _service_payment_proof(service):
    try:
        return service.payment_proof
    except PaymentProof.DoesNotExist:
        return None


def _is_service_payment_locked(service):
    proof = _service_payment_proof(service)
    return bool(proof and proof.status == PaymentProof.STATUS_VALIDATED)


def _service_display_treatments(service):
    bill = getattr(service, 'estimated_bill', None)
    if bill:
        names = [item.service_type for item in bill.items.all() if item.service_type]
        if names:
            return ', '.join(names)

    invoice = service.invoices.order_by('-created_at').first() if hasattr(service, 'invoices') else None
    if invoice:
        names = [item.item_type for item in invoice.items.all() if item.item_type]
        if names:
            return ', '.join(names)

    bookings = getattr(service, 'treatment_bookings', None)
    if bookings:
        names = [booking.treatment_service for booking in bookings.all() if booking.treatment_service]
        if names:
            return ', '.join(_unique_preserve_order(names))

    return service.preferred_service or '-'


def _get_treatment_option_by_name(option_name):
    if not option_name:
        return None
    return ServiceFormOption.objects.filter(
        form_section='Treatment',
        field_name='Treatment Service',
        option_value__iexact=option_name.strip(),
        is_active=True,
    ).order_by('-updated_at', '-id').first()


def _get_bank_option_by_name(bank_name, payment_type=''):
    if not bank_name:
        return None
    options = ServiceFormOption.objects.filter(
        form_section='Payment Proof Submission',
        field_name='Bank Used for Payment',
        option_value__iexact=bank_name.strip(),
        is_active=True,
    )
    if payment_type:
        options = options.filter(option_description__iexact=payment_type.strip())
    return options.order_by('-updated_at', '-id').first()


def _get_treatment_service_names():
    names = _get_active_service_form_option_values(
        'Treatment',
        'Treatment Service',
        fallback_values=TREATMENT_SERVICE_PREDEFINED_OPTIONS,
        excluded_values={'Other'},
    )
    return set(name.strip().lower() for name in names if name)

def home(request):
    """Public home page."""
    if request.session.get('om_id'):
        return redirect('om_home')
    if request.session.get('technician_id'):
        return redirect('technician_home')
    if request.session.get('sales_representative_id'):
        return redirect('sales_representative_home')
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
            request.session['om_display_id'] = str(om.id)
            return redirect('om_home')

        technician = Technician.objects.filter(email__iexact=email, is_active=True).only('id', 'technician_id', 'password', 'first_name', 'last_name').first()
        if technician and technician.password == password:
            request.session.flush()
            request.session['technician_id'] = technician.id
            request.session['technician_name'] = f"{technician.first_name} {technician.last_name}"
            request.session['technician_display_id'] = technician.technician_id or str(technician.id)
            return redirect('technician_home')

        sales_representative = SalesRepresentative.objects.filter(email__iexact=email, is_active=True).only('id', 'password', 'first_name', 'last_name').first()
        if sales_representative and sales_representative.password == password:
            request.session.flush()
            request.session['sales_representative_id'] = sales_representative.id
            request.session['sales_representative_name'] = f"{sales_representative.first_name} {sales_representative.last_name}"
            request.session['sales_representative_display_id'] = str(sales_representative.id)
            return redirect('sales_representative_home')

        customer = Customer.objects.filter(email=email, is_active=True).only('id', 'password', 'first_name', 'last_name').first()
        if customer and customer.password == password:
            request.session.flush()
            request.session['customer_id'] = customer.id
            request.session['customer_name'] = f"{customer.first_name} {customer.last_name}"
            request.session['customer_display_id'] = str(customer.id)
            return redirect('home')

        if Technician.objects.filter(email__iexact=email, is_active=False).exists() or SalesRepresentative.objects.filter(email__iexact=email, is_active=False).exists() or Customer.objects.filter(email__iexact=email, is_active=False).exists():
            return render(request, 'login.html', {
                'error_message': 'This account has been archived. Please contact the Operations Manager.',
                'form_data': {'email': email},
            }, status=403)

        return render(request, 'login.html', {
            'error_message': 'Invalid email or password.',
            'form_data': {'email': email},
        }, status=401)
    
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
            
            return redirect('login')
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
    
    # Keep existing ongoing-services context for compatibility.
    services = Service.objects.filter(
        customer=customer
    ).exclude(
        status__in=['Completed', 'Cancelled']
    ).select_related('property', 'estimated_bill', 'service_report', 'payment_proof').annotate(
        invoice_count=Count('invoices', distinct=True)
    ).order_by('-created_at')

    for service in services:
        proof = getattr(service, 'payment_proof', None)
        service.has_invoice = (service.invoice_count or 0) > 0
        service.payment_proof_status = proof.status if proof else ''
        service.can_submit_payment_proof = service.has_invoice and ((not proof) or proof.status == PaymentProof.STATUS_REJECTED)

    history_statuses = ['Payment Confirmed', 'Completed', 'Cancelled']
    completed_services = Service.objects.filter(
        customer=customer,
        status__in=history_statuses,
    ).select_related(
        'property',
        'service_report',
    ).annotate(
        invoice_count=Count('invoices', distinct=True)
    ).order_by('-created_at')

    for service in completed_services:
        service.has_invoice = (service.invoice_count or 0) > 0
    
    return render(request, 'profile.html', {
        'customer': customer,
        'services': services,
        'completed_services': completed_services,
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
            return redirect('profile')

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

    return redirect('service_status')


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

    _ensure_service_form_default_options()

    def _combined_invoice_total(inv):
        if not inv:
            return Decimal('0.00')

        estimated_bill = getattr(inv.service, 'estimated_bill', None)
        treatment_total = Decimal('0.00')
        if estimated_bill:
            treatment_total = sum((item.line_total for item in estimated_bill.items.all()), Decimal('0.00'))

        service_item_total = sum((item.line_total for item in inv.items.all()), Decimal('0.00'))
        return treatment_total + service_item_total

    def _proof_form_data(proof):
        if not proof:
            return {}

        return {
            'payment_type': proof.payment_type,
            'bank_used': proof.bank_used,
            'account_number': proof.account_number,
            'reference_number': proof.reference_number,
                'amount_paid': proof.amount_paid,
        }

    def _proof_context(service, invoice, errors=None, form_data=None, existing_proof=None):
        proof = existing_proof or (_service_payment_proof(service) if service else None)
        is_locked = bool(proof and proof.status == PaymentProof.STATUS_VALIDATED)
        proof_file_name = ''
        if proof and getattr(proof, 'proof_file', None):
            proof_file_name = proof.proof_file.name.split('/')[-1]

        return {
            'service': service,
            'invoice': invoice,
            'errors': errors or {},
            'form_data': form_data if form_data is not None else _proof_form_data(proof),
            'bank_options': list(ServiceFormOption.objects.filter(
                form_section='Payment Proof Submission',
                field_name='Bank Used for Payment',
                is_active=True,
            ).order_by('option_description', 'option_value')),
            'payment_type_options': list(ServiceFormOption.objects.filter(
                form_section='Payment Proof Submission',
                field_name='Payment Type',
                is_active=True,
            ).order_by('option_value')),
            'back_url': _resolve_back_url(request, 'service_status'),
            'display_total_amount': _combined_invoice_total(invoice),
            'existing_proof': proof,
            'proof_file_name': proof_file_name,
            'is_edit_mode': proof is not None,
            'is_locked': is_locked,
        }
    
    if request.method == 'POST':
        payment_type = request.POST.get('payment_type', '').strip()
        bank_used = request.POST.get('bank_used', '').strip()
        account_number = request.POST.get('account_number', '').strip()
        reference_number = request.POST.get('reference_number', '').strip()
        amount_paid = request.POST.get('amount_paid', '').strip()
        proof_file = request.FILES.get('proof_file')
        service_id = request.POST.get('service_id', '').strip()

        service = None
        invoice = None
        existing_proof = None

        if service_id:
            service = Service.objects.filter(id=service_id, customer_id=request.session['customer_id']).select_related('property').first()
            if service:
                invoice = service.invoices.order_by('-created_at').first()
                existing_proof = PaymentProof.objects.filter(service=service).first()

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
        if not proof_file and not existing_proof:
            errors['file'] = 'Proof of payment is required'

        payment_type_option = None
        if payment_type:
            payment_type_option = ServiceFormOption.objects.filter(
                form_section='Payment Proof Submission',
                field_name='Payment Type',
                option_value__iexact=payment_type,
                is_active=True,
            ).order_by('-updated_at', '-id').first()
            if not payment_type_option:
                errors['payment_type'] = 'Selected payment type is not available.'

        selected_bank_option = None
        if bank_used and payment_type and payment_type_option:
            selected_bank_option = _get_bank_option_by_name(bank_used, payment_type)
            if not selected_bank_option:
                errors['bank_used'] = 'Selected bank is not available for the chosen payment type.'
            elif not (selected_bank_option.account_number or '').strip():
                errors['account_number'] = 'Selected bank has no configured account number.'

        if selected_bank_option:
            account_number = (selected_bank_option.account_number or '').strip()
        
        # Validate file format and size
        if proof_file:
            allowed_extensions = ['jpg', 'jpeg', 'png', 'pdf']
            max_size = 10 * 1024 * 1024  # 10 MB
            
            file_ext = proof_file.name.split('.')[-1].lower()
            if file_ext not in allowed_extensions:
                errors['file'] = 'File format not allowed. Only JPG, PNG, or PDF are accepted.'
            
            if proof_file.size > max_size:
                errors['file'] = 'File size exceeds 10 MB limit.'
        
        if errors:
            form_data = request.POST.copy()
            form_data['account_number'] = account_number
            return render(request, 'submit_payment_proof.html', _proof_context(
                service,
                invoice,
                errors=errors,
                form_data=form_data,
                existing_proof=existing_proof,
            ))

        if not service:
            errors['service_id'] = 'A valid pending payment service is required.'
            form_data = request.POST.copy()
            form_data['account_number'] = account_number
            return render(request, 'submit_payment_proof.html', _proof_context(
                service,
                invoice,
                errors=errors,
                form_data=form_data,
                existing_proof=existing_proof,
            ))

        if not invoice:
            errors['service_id'] = 'Invoice is not yet available for this service.'
            form_data = request.POST.copy()
            form_data['account_number'] = account_number
            return render(request, 'submit_payment_proof.html', _proof_context(
                service,
                invoice,
                errors=errors,
                form_data=form_data,
                existing_proof=existing_proof,
            ))

        if existing_proof and existing_proof.status == PaymentProof.STATUS_VALIDATED:
            errors['service_id'] = 'Payment proof is already validated and is now read-only.'
            form_data = request.POST.copy()
            form_data['account_number'] = account_number
            return render(request, 'submit_payment_proof.html', _proof_context(
                service,
                invoice,
                errors=errors,
                form_data=form_data,
                existing_proof=existing_proof,
            ))

        if existing_proof and existing_proof.status in {
            PaymentProof.STATUS_FOR_VALIDATION,
        }:
            # Allow editing while preserving existing content.
            pass

        if existing_proof:
            existing_proof.invoice = invoice
            existing_proof.payment_type = payment_type
            existing_proof.bank_used = bank_used
            existing_proof.account_number = account_number
            existing_proof.reference_number = reference_number
            existing_proof.amount_paid = amount_paid
            if proof_file:
                existing_proof.proof_file = proof_file
            existing_proof.status = PaymentProof.STATUS_FOR_VALIDATION
            existing_proof.validated_at = None
            existing_proof.validated_by = None
            existing_proof.rejection_reason = ''
            existing_proof.save(update_fields=[
                'invoice',
                'payment_type',
                'bank_used',
                'account_number',
                'reference_number',
                'amount_paid',
                'proof_file' if proof_file else 'amount_paid',
                'status',
                'validated_at',
                'validated_by',
                'rejection_reason',
            ])
            return redirect('service_status')

        PaymentProof.objects.create(
            service=service,
            invoice=invoice,
            customer_id=request.session['customer_id'],
            payment_type=payment_type,
            bank_used=bank_used,
            account_number=account_number,
            reference_number=reference_number,
            amount_paid=amount_paid,
            proof_file=proof_file,
        )

        return redirect('service_status')

    service_id = request.GET.get('service_id', '').strip()
    service = None
    invoice = None
    if service_id:
        service = Service.objects.filter(id=service_id, customer_id=request.session['customer_id']).select_related('property').first()
        if service:
            invoice = service.invoices.order_by('-created_at').first()

    if not service:
        service = Service.objects.filter(customer_id=request.session['customer_id'], status='Pending Payment').select_related('property').order_by('-created_at').first()
        if service:
            invoice = service.invoices.order_by('-created_at').first()

    existing_proof = PaymentProof.objects.filter(service=service).first() if service else None
    return render(request, 'submit_payment_proof.html', _proof_context(
        service,
        invoice,
        form_data=_proof_form_data(existing_proof),
        existing_proof=existing_proof,
    ))


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
    search = request.GET.get('q', '').strip()
    properties = Property.objects.filter(customer=customer)
    if search:
        properties = properties.filter(
            Q(property_name__icontains=search)
            | Q(street_number__icontains=search)
            | Q(street__icontains=search)
            | Q(city__icontains=search)
            | Q(province__icontains=search)
            | Q(property_type__icontains=search)
        )
    
    return render(request, 'property_list.html', {
        'customer': customer,
        'properties': properties,
        'search': search,
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
                zip_code=zip_code,
                property_type=property_type,
                floor_area=float(floor_area)
            )
            return redirect('property_list')
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
            property_obj.zip_code = zip_code
            property_obj.property_type = property_type
            property_obj.floor_area = float(floor_area)
            property_obj.save()
            return redirect('property_list')
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
        return render(request, 'book_inspection.html', {
            'customer': customer,
            'properties': properties,
            'errors': {'property_id': 'You need to register a property before booking an inspection.'},
            'form_data': {},
            'service_choices': service_choices if 'service_choices' in locals() else [],
            'pest_choices': pest_choices if 'pest_choices' in locals() else [],
            'time_slot_choices': Service.TIME_SLOT_CHOICES,
            'today': date.today().isoformat(),
        })

    _ensure_service_form_default_options()
    service_choices = _get_service_form_choices(
        'Inspection',
        'Preferred Service',
        fallback_values=[label for _, label in Service.PREFERRED_SERVICE_CHOICES],
    )
    pest_choices = _get_service_form_choices(
        'Inspection',
        'Pest Problems',
        fallback_values=[label for _, label in Service.PEST_PROBLEM_CHOICES],
    )
    
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
                'service_choices': service_choices,
                'pest_choices': pest_choices,
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
                'service_choices': service_choices,
                'pest_choices': pest_choices,
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
            return redirect('service_status')
        except Exception as e:
            errors['general'] = f'An error occurred while booking the inspection: {str(e)}'
            return render(request, 'book_inspection.html', {
                'customer': customer,
                'properties': properties,
                'errors': errors,
                'form_data': request.POST,
                'service_choices': service_choices,
                'pest_choices': pest_choices,
                'time_slot_choices': Service.TIME_SLOT_CHOICES,
                'today': date.today().isoformat(),
            })
    
    # GET request - display the form
    return render(request, 'book_inspection.html', {
        'customer': customer,
        'properties': properties,
        'service_choices': service_choices,
        'pest_choices': pest_choices,
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
    ).select_related('property', 'estimated_bill', 'service_report', 'payment_proof').annotate(
        invoice_count=Count('invoices', distinct=True)
    ).order_by('-created_at')

    for service in services:
        proof = getattr(service, 'payment_proof', None)
        service.has_invoice = (service.invoice_count or 0) > 0
        service.payment_proof_status = proof.status if proof else ''
        service.can_submit_payment_proof = service.has_invoice and ((not proof) or proof.status == PaymentProof.STATUS_REJECTED)
    
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


def customer_view_booking(request, service_id):
    if 'customer_id' not in request.session:
        return redirect('login')

    try:
        customer = Customer.objects.get(id=request.session['customer_id'])
    except Customer.DoesNotExist:
        request.session.flush()
        return redirect('login')

    service = Service.objects.select_related('customer', 'property').filter(
        id=service_id,
        customer=customer,
    ).first()

    if not service:
        messages.error(request, 'Service record not found.')
        return redirect('service_status')

    return render(request, 'view_booking.html', {
        'customer': customer,
        'service': service,
        'identified_as': 'Customer',
        'back_url': _resolve_back_url(request, 'service_status'),
    })


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
        return redirect('service_status')

    treatment_rows = []
    for item in estimated_bill.items.all():
        treatment_details = _get_treatment_billing_details(item.service_type)
        treatment_rows.append({
            'service_type': treatment_details['service_type'],
            'quantity': item.quantity,
            'unit_price': item.unit_price,
            'line_total': item.line_total,
            'problem_text': item.problem_text or treatment_details['problem_text'],
            'recommendation_text': item.recommendation_text or treatment_details['recommendation_text'],
        })

    return render(request, 'om_estimated_bill_view.html', {
        'estimated_bill': estimated_bill,
        'role': 'customer',
        'back_url': _resolve_back_url(request, 'service_status'),
        'treatment_rows': treatment_rows,
        'service_type_display': _service_display_treatments(estimated_bill.service),
    })


def customer_confirm_estimated_bill(request, estimated_bill_id):
    if 'customer_id' not in request.session:
        return redirect('login')

    if request.method != 'POST':
        return redirect('service_status')

    try:
        customer = Customer.objects.get(id=request.session['customer_id'])
    except Customer.DoesNotExist:
        request.session.flush()
        return redirect('login')

    estimated_bill = EstimatedBill.objects.select_related('service').filter(
        id=estimated_bill_id,
        service__customer=customer,
    ).first()

    if not estimated_bill:
        return redirect('service_status')

    service = estimated_bill.service
    if service.status == 'Estimated Bill Created':
        service.status = 'For Treatment Booking'
        service.save(update_fields=['status'])

    return redirect('service_status')


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
        'back_url': _resolve_back_url(request, 'service_status'),
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
            return redirect('om_profile')

        return render(request, 'om_change_password.html', {
            'om': om,
            'errors': errors,
        })

    return render(request, 'om_change_password.html', {'om': om})


def sales_representative_profile(request):
    if 'sales_representative_id' not in request.session:
        return redirect('login')

    sales_representative = SalesRepresentative.objects.filter(
        id=request.session['sales_representative_id']
    ).first()
    if not sales_representative:
        request.session.flush()
        return redirect('login')

    return render(request, 'sales_representative_profile.html', {
        'sales_representative': sales_representative,
    })


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


def _get_service_history_queryset(search='', status_filter=''):
    history_statuses = ['Payment Confirmed', 'Completed', 'Cancelled']
    services = Service.objects.select_related(
        'customer',
        'property',
        'service_report',
        'payment_proof',
    ).prefetch_related('invoices').filter(
        status__in=history_statuses,
    ).order_by('-created_at')

    if status_filter in history_statuses:
        services = services.filter(status=status_filter)

    if search:
        services = services.filter(
            Q(id__icontains=search)
            | Q(customer__first_name__icontains=search)
            | Q(customer__last_name__icontains=search)
            | Q(property__property_name__icontains=search)
            | Q(property__street__icontains=search)
            | Q(preferred_service__icontains=search)
        )

    for service in services:
        service.latest_invoice = service.invoices.order_by('-created_at').first()

    return services, history_statuses


def om_service_history(request):
    if 'om_id' not in request.session:
        return redirect('login')

    try:
        om = OperationsManager.objects.get(id=request.session['om_id'])
    except OperationsManager.DoesNotExist:
        request.session.flush()
        return redirect('login')

    search = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '').strip()
    services, history_statuses = _get_service_history_queryset(search, status_filter)

    return render(request, 'service_history_shared.html', {
        'om': om,
        'history_role': 'om',
        'services': services,
        'search': search,
        'status_filter': status_filter,
        'status_choices': history_statuses,
    })


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

    search = request.GET.get('q', '').strip()

    estimated_bills = EstimatedBill.objects.select_related(
        'service__customer', 'service__property'
    ).prefetch_related('items').exclude(
        service__status__in=['Payment Confirmed', 'Completed', 'Cancelled']
    ).order_by('-created_at')

    if search:
        estimated_bills = estimated_bills.filter(
            Q(service__id__icontains=search)
            | Q(id__icontains=search)
            | Q(service__customer__first_name__icontains=search)
            | Q(service__customer__last_name__icontains=search)
            | Q(service__property__street__icontains=search)
            | Q(service__property__city__icontains=search)
            | Q(items__service_type__icontains=search)
        ).distinct()

    return render(request, 'om_estimated_bills.html', {
        'om': om,
        'estimated_bills': estimated_bills,
        'search': search,
    })


def om_view_estimated_bill(request, estimated_bill_id):
    if 'om_id' not in request.session:
        return redirect('login')

    estimated_bill = EstimatedBill.objects.select_related(
        'service__customer', 'service__property', 'operations_manager'
    ).prefetch_related('items').filter(id=estimated_bill_id).first()

    if not estimated_bill:
        return redirect('om_estimated_bills')

    treatment_rows = []
    for item in estimated_bill.items.all():
        treatment_details = _get_treatment_billing_details(item.service_type)
        treatment_rows.append({
            'service_type': treatment_details['service_type'],
            'quantity': item.quantity,
            'unit_price': item.unit_price,
            'line_total': item.line_total,
            'problem_text': item.problem_text or treatment_details['problem_text'],
            'recommendation_text': item.recommendation_text or treatment_details['recommendation_text'],
        })

    return render(request, 'om_estimated_bill_view.html', {
        'estimated_bill': estimated_bill,
        'role': 'om',
        'back_url': _resolve_back_url(request, 'om_estimated_bills'),
        'treatment_rows': treatment_rows,
        'service_type_display': _service_display_treatments(estimated_bill.service),
    })


def om_edit_estimated_bill(request, estimated_bill_id):
    if 'om_id' not in request.session:
        return redirect('login')

    estimated_bill = EstimatedBill.objects.select_related(
        'service__customer', 'service__property'
    ).prefetch_related('items').filter(id=estimated_bill_id).first()

    treatment_options = list(ServiceFormOption.objects.filter(
        form_section='Treatment',
        field_name='Treatment Service',
        is_active=True,
    ).order_by('option_value').values('option_value', 'option_description', 'option_rate', 'problem_text', 'recommendation_text'))

    if not estimated_bill:
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
                    {
                        'value': option['option_value'],
                        'label': option['option_value'],
                        'description': option['option_description'],
                        'rate': str(option['option_rate'] or ''),
                        'problem_text': option['problem_text'] or '',
                        'recommendation_text': option['recommendation_text'] or '',
                    }
                    for option in treatment_options
                ]),
            })

        with transaction.atomic():
            estimated_bill.items.all().delete()
            EstimatedBillItem.objects.bulk_create([
                EstimatedBillItem(
                    estimated_bill=estimated_bill,
                    service_type=_get_treatment_billing_details(item['service_type'])['service_type'],
                    quantity=item['quantity'],
                    unit_price=_get_treatment_billing_details(item['service_type'])['unit_price'],
                    problem_text=item.get('problem_text', ''),
                    recommendation_text=item.get('recommendation_text', ''),
                )
                for item in items
            ])

        return redirect('om_estimated_bills')

    return render(request, 'om_edit_estimated_bill.html', {
        'estimated_bill': estimated_bill,
        'errors': {},
        'items_json': json.dumps([
            {
                'service_type': item.service_type,
                'quantity': item.quantity,
                'problem_text': item.problem_text,
                'recommendation_text': item.recommendation_text,
            }
            for item in estimated_bill.items.all()
        ]),
        'service_type_choices_json': json.dumps([
            {
                'value': option['option_value'],
                'label': option['option_value'],
                'description': option['option_description'],
                'rate': str(option['option_rate'] or ''),
                'problem_text': option['problem_text'] or '',
                'recommendation_text': option['recommendation_text'] or '',
            }
            for option in treatment_options
        ]),
    })


def om_delete_estimated_bill(request, estimated_bill_id):
    if 'om_id' not in request.session:
        return redirect('login')

    if request.method != 'POST':
        return redirect('om_estimated_bills')

    estimated_bill = EstimatedBill.objects.select_related('service').filter(id=estimated_bill_id).first()
    if not estimated_bill:
        return redirect('om_estimated_bills')

    service = estimated_bill.service
    estimated_bill.delete()
    service.status = 'Ongoing Inspection'
    service.save(update_fields=['status'])

    return redirect('om_estimated_bills')


def om_invoices(request):
    if 'om_id' not in request.session:
        return redirect('login')

    try:
        om = OperationsManager.objects.get(id=request.session['om_id'])
    except OperationsManager.DoesNotExist:
        request.session.flush()
        return redirect('login')

    search = request.GET.get('q', '').strip()

    invoices = Invoice.objects.select_related(
        'service__customer', 'service__property', 'service__payment_proof'
    ).prefetch_related('items').exclude(
        service__status__in=['Payment Confirmed', 'Completed', 'Cancelled']
    ).order_by('-created_at')

    if search:
        invoices = invoices.filter(
            Q(service__id__icontains=search)
            | Q(id__icontains=search)
            | Q(service__customer__first_name__icontains=search)
            | Q(service__customer__last_name__icontains=search)
            | Q(service__property__street__icontains=search)
            | Q(service__property__city__icontains=search)
            | Q(items__item_type__icontains=search)
        ).distinct()

    invoices = list(invoices)
    for invoice in invoices:
        invoice.payment_locked = _is_service_payment_locked(invoice.service)

    return render(request, 'om_invoices.html', {
        'om': om,
        'invoices': invoices,
        'search': search,
    })


def om_view_invoice(request, invoice_id):
    if 'om_id' not in request.session:
        return redirect('login')

    invoice = Invoice.objects.select_related(
        'service__customer', 'service__property', 'operations_manager', 'service__estimated_bill'
    ).prefetch_related('items__service_item', 'service__estimated_bill__items').filter(id=invoice_id).first()

    if not invoice:
        return redirect('om_invoices')

    treatment_rows = []
    estimated_bill = getattr(invoice.service, 'estimated_bill', None)
    if estimated_bill:
        for item in estimated_bill.items.all():
            treatment_details = _get_treatment_billing_details(item.service_type)
            treatment_rows.append({
                'service_type': treatment_details['service_type'] or item.service_type,
                'quantity': item.quantity,
                'unit_price': item.unit_price,
                'line_total': item.line_total,
                'target_pest': treatment_details['target_pest'],
                'application_method': treatment_details['application_method'],
                'additional_information': treatment_details['additional_information'],
                'dilution_rate': treatment_details['dilution_rate'],
            })

    service_item_rows = []
    for item in invoice.items.all():
        treatment_details = _get_treatment_billing_details(item.item_type)
        service_item_rows.append({
            'item_type': item.service_item.name if item.service_item else item.item_type,
            'quantity': item.quantity,
            'unit_price': item.unit_price,
            'line_total': item.line_total,
            'target_pest': treatment_details['target_pest'],
            'application_method': treatment_details['application_method'],
            'additional_information': treatment_details['additional_information'],
            'dilution_rate': treatment_details['dilution_rate'],
        })

    treatment_total = sum((row['line_total'] for row in treatment_rows), Decimal('0.00'))
    service_item_total = sum((row['line_total'] for row in service_item_rows), Decimal('0.00'))

    return render(request, 'om_invoice_view.html', {
        'invoice': invoice,
        'back_url': _resolve_back_url(request, 'om_invoices'),
        'treatment_rows': treatment_rows,
        'service_item_rows': service_item_rows,
        'display_total_amount': treatment_total + service_item_total,
        'service_type_display': invoice.service.treatment_summary,
    })


def customer_view_invoice(request, service_id):
    if 'customer_id' not in request.session:
        return redirect('login')

    try:
        customer = Customer.objects.get(id=request.session['customer_id'])
    except Customer.DoesNotExist:
        request.session.flush()
        return redirect('login')

    invoice = Invoice.objects.select_related(
        'service__customer', 'service__property', 'operations_manager', 'service__estimated_bill'
    ).prefetch_related('items__service_item', 'service__estimated_bill__items').filter(
        service_id=service_id,
        service__customer=customer,
    ).first()

    if not invoice:
        return redirect('pending_payment')

    treatment_rows = []
    estimated_bill = getattr(invoice.service, 'estimated_bill', None)
    if estimated_bill:
        for item in estimated_bill.items.all():
            treatment_details = _get_treatment_billing_details(item.service_type)
            treatment_rows.append({
                'service_type': treatment_details['service_type'] or item.service_type,
                'quantity': item.quantity,
                'unit_price': item.unit_price,
                'line_total': item.line_total,
                'target_pest': treatment_details['target_pest'],
                'application_method': treatment_details['application_method'],
                'additional_information': treatment_details['additional_information'],
                'dilution_rate': treatment_details['dilution_rate'],
            })

    service_item_rows = []
    for item in invoice.items.all():
        treatment_details = _get_treatment_billing_details(item.item_type)
        service_item_rows.append({
            'item_type': item.service_item.name if item.service_item else item.item_type,
            'quantity': item.quantity,
            'unit_price': item.unit_price,
            'line_total': item.line_total,
            'target_pest': treatment_details['target_pest'],
            'application_method': treatment_details['application_method'],
            'additional_information': treatment_details['additional_information'],
            'dilution_rate': treatment_details['dilution_rate'],
        })

    treatment_total = sum((row['line_total'] for row in treatment_rows), Decimal('0.00'))
    service_item_total = sum((row['line_total'] for row in service_item_rows), Decimal('0.00'))
    payment_proof = getattr(invoice.service, 'payment_proof', None)
    payment_proof_exists = payment_proof is not None

    return render(request, 'om_invoice_view.html', {
        'invoice': invoice,
        'role': 'customer',
        'back_url': _resolve_back_url(request, 'service_status'),
        'treatment_rows': treatment_rows,
        'service_item_rows': service_item_rows,
        'display_total_amount': treatment_total + service_item_total,
        'service_type_display': invoice.service.treatment_summary,
        'allow_customer_payment': not (payment_proof and payment_proof.status == PaymentProof.STATUS_VALIDATED),
        'customer_payment_action_label': 'Edit Proof of Payment' if payment_proof_exists else 'Submit Proof of Payment',
    })


def om_edit_invoice(request, invoice_id):
    if 'om_id' not in request.session:
        return redirect('login')

    invoice = Invoice.objects.select_related(
        'service__customer', 'service__property'
    ).prefetch_related('items', 'service__estimated_bill__items').filter(id=invoice_id).first()

    if not invoice:
        messages.error(request, 'Invoice not found.')
        return redirect('om_invoices')

    if _is_service_payment_locked(invoice.service):
        messages.error(request, 'Invoice is locked because payment has already been confirmed in remittance records.')
        return redirect('om_view_invoice', invoice_id=invoice.id)

    existing_item_ids = list(
        invoice.items.exclude(service_item_id__isnull=True).values_list('service_item_id', flat=True)
    )
    treatment_names = _get_treatment_service_names()
    service_item_options = [
        option
        for option in InvoiceItemOption.objects.filter(Q(is_active=True) | Q(id__in=existing_item_ids)).order_by('name')
        if option.id in existing_item_ids or option.name.strip().lower() not in treatment_names
    ]
    allowed_item_map = {option.id: option.name for option in service_item_options}
    allowed_item_price_map = {option.id: option.default_unit_price for option in service_item_options}
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
        items, has_invalid = _clean_invoice_items(
            raw_items,
            allowed_item_map=allowed_item_map,
            allowed_item_price_map=allowed_item_price_map,
        )
        errors = {}

        if not service_item_choices:
            errors['general'] = 'Please create at least one Service Item in Service Configuration first.'

        if not items or has_invalid:
            errors['general'] = 'Required fields must be filled in.'

        if errors:
            return render(request, 'om_edit_invoice.html', {
                'invoice': invoice,
                'errors': errors,
                'items_json': json.dumps(raw_items if raw_items else [{'service_item_id': '', 'quantity': ''}]),
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

    if _is_service_payment_locked(invoice.service):
        messages.error(request, 'Invoice is locked because payment has already been confirmed in remittance records.')
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
        problem_text = (item.get('problem_text') or '').strip()
        recommendation_text = (item.get('recommendation_text') or '').strip()

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
            'problem_text': problem_text,
            'recommendation_text': recommendation_text,
        })

    merged_items = []
    merged_map = {}
    for item in cleaned_items:
        normalized_name = item['service_type'].strip().lower()
        if normalized_name in merged_map:
            merged_index = merged_map[normalized_name]
            merged_items[merged_index]['quantity'] += item['quantity']
            if item['problem_text']:
                merged_items[merged_index]['problem_text'] = item['problem_text']
            if item['recommendation_text']:
                merged_items[merged_index]['recommendation_text'] = item['recommendation_text']
        else:
            merged_map[normalized_name] = len(merged_items)
            merged_items.append(item)

    return merged_items, has_invalid


def _get_treatment_billing_details(service_type):
    option = _get_treatment_option_by_name(service_type)
    if option:
        return {
            'service_type': option.option_value,
            'unit_price': option.option_rate or Decimal('0.00'),
            'problem_text': option.problem_text,
            'recommendation_text': option.recommendation_text,
            'target_pest': option.target_pest,
            'application_method': option.application_method,
            'additional_information': option.additional_information,
            'dilution_rate': option.dilution_rate,
        }

    metadata = TREATMENT_SERVICE_METADATA.get(service_type, {})
    return {
        'service_type': service_type,
        'unit_price': metadata.get('rate', Decimal('0.00')),
        'problem_text': metadata.get('problem_text', ''),
        'recommendation_text': metadata.get('recommendation_text', ''),
        'target_pest': metadata.get('target_pest', ''),
        'application_method': metadata.get('application_method', ''),
        'additional_information': metadata.get('additional_information', ''),
        'dilution_rate': metadata.get('dilution_rate', ''),
    }


def _parse_invoice_items(raw_payload):
    if not raw_payload:
        return []
    try:
        parsed = json.loads(raw_payload)
        return parsed if isinstance(parsed, list) else []
    except (TypeError, ValueError):
        return []


def _clean_invoice_items(raw_items, allowed_item_map=None, allowed_item_price_map=None):
    cleaned_items = []
    has_invalid = False
    allowed_map = allowed_item_map or {}
    allowed_price_map = allowed_item_price_map or {}

    for item in raw_items:
        if not isinstance(item, dict):
            continue

        service_item_id_raw = str(item.get('service_item_id') or '').strip()
        quantity_raw = str(item.get('quantity') or '').strip()

        if not (service_item_id_raw or quantity_raw):
            continue

        if not service_item_id_raw or not quantity_raw:
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

        unit_price = allowed_price_map.get(service_item_id)
        if unit_price is None:
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

        if unit_price <= 0:
            has_invalid = True
            continue

        cleaned_items.append({
            'service_item_id': service_item_id,
            'item_type': allowed_map.get(service_item_id, ''),
            'quantity': quantity,
            'unit_price': unit_price,
        })

    return cleaned_items, has_invalid


def _get_invoice_eligible_services_queryset():
    return Service.objects.filter(
        status__in=['Ongoing Treatment', 'Pending Payment'],
        estimated_bill__isnull=False,
        invoices__isnull=True,
    ).select_related('customer', 'property', 'estimated_bill').prefetch_related(
        'estimated_bill__items',
        'invoices__items',
    ).order_by('-treatment_confirmed_date', '-confirmed_date', '-date', '-created_at')


def _filter_invoice_eligible_services(services):
    return list(services)


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
    for selectable_service in selectable_services:
        selectable_service.service_type_display = _service_display_treatments(selectable_service)

    treatment_names = _get_treatment_service_names()
    service_item_options = [
        option
        for option in InvoiceItemOption.objects.filter(is_active=True).order_by('name')
        if option.name.strip().lower() not in treatment_names
    ]
    allowed_item_map = {option.id: option.name for option in service_item_options}
    allowed_item_price_map = {option.id: option.default_unit_price for option in service_item_options}
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
        cleaned_items, has_invalid = _clean_invoice_items(
            raw_items,
            allowed_item_map=allowed_item_map,
            allowed_item_price_map=allowed_item_price_map,
        )

        selected_service = next(
            (service for service in selectable_services if str(service.id) == selected_service_id),
            None,
        )
        errors = {}

        if not selected_service:
            errors['general'] = 'Required fields must be filled in.'

        if selected_service and selected_service.invoices.exists():
            errors['general'] = 'An invoice already exists for this service.'

        if has_invalid:
            errors['general'] = 'Required fields must be filled in.'

        if errors:
            return render(request, 'om_create_invoice.html', {
                'om': om,
                'services': selectable_services,
                'selected_service_id': selected_service_id,
                'errors': errors,
                'items_json': json.dumps(raw_items if raw_items else [{'service_item_id': '', 'quantity': ''}]),
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

        return redirect('om_invoices')

    return render(request, 'om_create_invoice.html', {
        'om': om,
        'services': selectable_services,
        'selected_service_id': '',
        'errors': {},
        'items_json': json.dumps([{'service_item_id': '', 'quantity': ''}]),
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

    treatment_options = list(ServiceFormOption.objects.filter(
        form_section='Treatment',
        field_name='Treatment Service',
        is_active=True,
    ).order_by('option_value').values('option_value', 'option_description', 'option_rate', 'problem_text', 'recommendation_text'))

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
                'service_type_choices_json': json.dumps([
                    {
                        'value': option['option_value'],
                        'label': option['option_value'],
                        'description': option['option_description'],
                        'rate': str(option['option_rate'] or ''),
                        'problem_text': option['problem_text'] or '',
                        'recommendation_text': option['recommendation_text'] or '',
                    }
                    for option in treatment_options
                ]),
            })

        if EstimatedBill.objects.filter(service=selected_service).exists():
            return redirect('om_estimated_bills')

        with transaction.atomic():
            estimated_bill = EstimatedBill.objects.create(
                service=selected_service,
                operations_manager=om,
            )

            EstimatedBillItem.objects.bulk_create([
                EstimatedBillItem(
                    estimated_bill=estimated_bill,
                    service_type=_get_treatment_billing_details(item['service_type'])['service_type'],
                    quantity=item['quantity'],
                    unit_price=_get_treatment_billing_details(item['service_type'])['unit_price'],
                    problem_text=item.get('problem_text', ''),
                    recommendation_text=item.get('recommendation_text', ''),
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

        return redirect('om_estimated_bills')

    return render(request, 'om_create_estimated_bill.html', {
        'om': om,
        'services': ongoing_inspection_services,
        'selected_service_id': '',
        'errors': {},
        'items_json': json.dumps(default_items),
        'service_type_choices_json': json.dumps([
            {
                'value': option['option_value'],
                'label': option['option_value'],
                'description': option['option_description'],
                'rate': str(option['option_rate'] or ''),
                'problem_text': option['problem_text'] or '',
                'recommendation_text': option['recommendation_text'] or '',
            }
            for option in treatment_options
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

    search = request.GET.get('q', '').strip()

    reports = ServiceReport.objects.select_related(
        'service__customer', 'service__property'
    ).exclude(
        service__status__in=['Payment Confirmed', 'Completed', 'Cancelled']
    ).order_by('-created_at')

    if search:
        reports = reports.filter(
            Q(service__id__icontains=search)
            | Q(service__customer__first_name__icontains=search)
            | Q(service__customer__last_name__icontains=search)
            | Q(service__property__street__icontains=search)
            | Q(service__property__city__icontains=search)
            | Q(service__preferred_service__icontains=search)
        )

    return render(request, 'service_reports_shared.html', {
        'om': om,
        'report_role': 'om',
        'reports': reports,
        'search': search,
    })


def om_remittance_records(request):
    if 'om_id' not in request.session:
        return redirect('login')

    try:
        om = OperationsManager.objects.get(id=request.session['om_id'])
    except OperationsManager.DoesNotExist:
        request.session.flush()
        return redirect('login')

    search = request.GET.get('q', '').strip()
    records = RemittanceRecord.objects.select_related(
        'service__customer',
        'service__property',
        'invoice',
        'payment_proof',
        'confirmed_by',
    ).order_by('-created_at')

    if search:
        records = records.filter(
            Q(service__customer__first_name__icontains=search)
            | Q(service__customer__last_name__icontains=search)
            | Q(service__property__property_name__icontains=search)
            | Q(service__property__street__icontains=search)
            | Q(service__id__icontains=search)
            | Q(invoice__id__icontains=search)
        )

    return render(request, 'om_remittance_records.html', {
        'om': om,
        'records': records,
        'search': search,
        'back_url': reverse('om_billing'),
    })


def remittance_record_details(request, record_id):
    is_om = 'om_id' in request.session
    is_sales = 'sales_representative_id' in request.session

    if not (is_om or is_sales):
        return redirect('login')

    record = RemittanceRecord.objects.select_related(
        'service__customer',
        'service__property',
        'invoice',
        'payment_proof',
        'confirmed_by',
    ).filter(id=record_id).first()

    if not record:
        if is_om:
            return redirect('om_remittance_records')
        return redirect('sales_representative_remittance_records')

    payment_proof = record.payment_proof
    property_obj = record.service.property
    customer = record.service.customer
    bank_used = payment_proof.bank_used or ''
    bank_initials = ''.join(part[0] for part in bank_used.split() if part).upper()

    details = {
        'customer_name': f"{customer.first_name} {customer.last_name}",
        'address': f"{property_obj.street_number} {property_obj.street}, {property_obj.city}",
        'or_number': f"OR-{record.id:06d}",
        'bank_initials_used': f"{bank_initials} / {bank_used}" if bank_initials else bank_used,
        'payment_type': payment_proof.payment_type,
        'check_or_reference_number': payment_proof.reference_number,
        'payment_date': payment_proof.validated_at or payment_proof.uploaded_at,
        'account_number': payment_proof.account_number,
        'amount': payment_proof.amount_paid,
        'treatment_date': record.service.treatment_confirmed_date,
        'invoice_id': record.invoice.id if record.invoice else None,
    }

    back_url_name = 'om_remittance_records' if is_om else 'sales_representative_remittance_records'

    return render(request, 'remittance_record_details.html', {
        'record': record,
        'details': details,
        'back_url': reverse(back_url_name),
    })


def sales_representative_home(request):
    if 'sales_representative_id' not in request.session:
        return redirect('login')

    sales_representative = SalesRepresentative.objects.filter(
        id=request.session['sales_representative_id']
    ).first()
    if not sales_representative:
        request.session.flush()
        return redirect('login')

    queue_count = PaymentProof.objects.filter(status=PaymentProof.STATUS_FOR_VALIDATION).count()
    validated_count = PaymentProof.objects.filter(status=PaymentProof.STATUS_VALIDATED).count()
    rejected_count = PaymentProof.objects.filter(status=PaymentProof.STATUS_REJECTED).count()

    recent_proofs = PaymentProof.objects.select_related(
        'service__customer',
        'service__property',
        'invoice',
    ).order_by('-uploaded_at')[:8]

    return render(request, 'sales_representative_home.html', {
        'sales_representative': sales_representative,
        'queue_count': queue_count,
        'validated_count': validated_count,
        'rejected_count': rejected_count,
        'recent_proofs': recent_proofs,
    })


def sales_representative_payment_proofs(request):
    if 'sales_representative_id' not in request.session:
        return redirect('login')

    sales_representative = SalesRepresentative.objects.filter(
        id=request.session['sales_representative_id']
    ).first()
    if not sales_representative:
        request.session.flush()
        return redirect('login')

    search = request.GET.get('q', '').strip()
    proofs = PaymentProof.objects.select_related(
        'service__customer',
        'service__property',
        'invoice',
        'validated_by',
    ).filter(status=PaymentProof.STATUS_FOR_VALIDATION).order_by('-uploaded_at')

    if search:
        proofs = proofs.filter(
            Q(service__id__icontains=search)
            | Q(customer__first_name__icontains=search)
            | Q(customer__last_name__icontains=search)
            | Q(service__property__street__icontains=search)
        )

    return render(request, 'sales_representative_payment_proofs.html', {
        'sales_representative': sales_representative,
        'proofs': proofs,
        'search': search,
    })


def sales_representative_service_history(request):
    if 'sales_representative_id' not in request.session:
        return redirect('login')

    sales_representative = SalesRepresentative.objects.filter(
        id=request.session['sales_representative_id']
    ).first()
    if not sales_representative:
        request.session.flush()
        return redirect('login')

    search = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '').strip()
    services, history_statuses = _get_service_history_queryset(search, status_filter)

    return render(request, 'service_history_shared.html', {
        'sales_representative': sales_representative,
        'history_role': 'sales',
        'services': services,
        'search': search,
        'status_filter': status_filter,
        'status_choices': history_statuses,
    })


def sales_representative_service_status(request):
    if 'sales_representative_id' not in request.session:
        return redirect('login')

    sales_representative = SalesRepresentative.objects.filter(
        id=request.session['sales_representative_id']
    ).first()
    if not sales_representative:
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
    ).select_related('customer', 'property', 'service_report').prefetch_related(
        'invoices'
    ).annotate(
        workflow_order=Case(
            *status_order_cases,
            default=len(OM_STATUS_WORKFLOW),
            output_field=IntegerField(),
        )
    ).order_by(order_by, 'workflow_order')

    services = list(services_qs)
    for service in services:
        service.latest_invoice = service.invoices.order_by('-created_at').first()

    return render(request, 'service_status_shared.html', {
        'sales_representative': sales_representative,
        'status_role': 'sales',
        'services': services,
        'created_order': created_order,
    })


def sales_representative_remittance_records(request):
    if 'sales_representative_id' not in request.session:
        return redirect('login')

    sales_representative = SalesRepresentative.objects.filter(
        id=request.session['sales_representative_id']
    ).first()
    if not sales_representative:
        request.session.flush()
        return redirect('login')

    search = request.GET.get('q', '').strip()

    records = RemittanceRecord.objects.select_related(
        'service__customer',
        'service__property',
        'invoice',
        'payment_proof',
        'confirmed_by',
    ).order_by('-created_at')

    if search:
        records = records.filter(
            Q(service__customer__first_name__icontains=search)
            | Q(service__customer__last_name__icontains=search)
            | Q(service__property__street__icontains=search)
            | Q(service__id__icontains=search)
            | Q(invoice__id__icontains=search)
        )

    return render(request, 'om_remittance_records.html', {
        'records': records,
        'search': search,
        'back_url': reverse('sales_representative_payment_proofs'),
    })


def sales_representative_view_invoice(request, invoice_id):
    if 'sales_representative_id' not in request.session:
        return redirect('login')

    invoice = Invoice.objects.select_related(
        'service__customer', 'service__property', 'operations_manager'
    ).prefetch_related('items').filter(id=invoice_id).first()

    if not invoice:
        return redirect('sales_representative_payment_proofs')

    treatment_rows = []
    for item in invoice.items.all():
        treatment_details = _get_treatment_billing_details(item.item_type)
        treatment_rows.append({
            'item_type': treatment_details['service_type'] or item.item_type,
            'quantity': item.quantity,
            'unit_price': item.unit_price,
            'line_total': item.line_total,
            'target_pest': treatment_details['target_pest'],
            'application_method': treatment_details['application_method'],
            'additional_information': treatment_details['additional_information'],
            'dilution_rate': treatment_details['dilution_rate'],
        })

    return render(request, 'om_invoice_view.html', {
        'invoice': invoice,
        'role': 'sales_representative',
        'back_url': _resolve_back_url(request, 'sales_representative_payment_proofs'),
        'treatment_rows': treatment_rows,
        'service_type_display': invoice.service.treatment_summary,
    })


def sales_representative_review_payment_proof(request, payment_proof_id):
    if 'sales_representative_id' not in request.session:
        return redirect('login')

    sales_representative = SalesRepresentative.objects.filter(
        id=request.session['sales_representative_id']
    ).first()
    if not sales_representative:
        request.session.flush()
        return redirect('login')

    proof = PaymentProof.objects.select_related(
        'service__customer',
        'service__property',
        'invoice',
        'validated_by',
    ).filter(id=payment_proof_id).first()
    if not proof:
        return redirect('sales_representative_payment_proofs')

    errors = {}
    if request.method == 'POST':
        if proof.status != PaymentProof.STATUS_FOR_VALIDATION:
            errors['action'] = 'Validation status is final and can no longer be changed.'
            return render(request, 'sales_representative_review_payment_proof.html', {
                'sales_representative': sales_representative,
                'proof': proof,
                'errors': errors,
            })

        action = request.POST.get('action', '').strip()
        rejection_reason = request.POST.get('rejection_reason', '').strip()

        if action == 'validate':
            with transaction.atomic():
                proof.status = PaymentProof.STATUS_VALIDATED
                proof.validated_at = timezone.now()
                proof.validated_by = sales_representative
                proof.rejection_reason = ''
                proof.save(update_fields=['status', 'validated_at', 'validated_by', 'rejection_reason'])

                service = proof.service
                service.status = 'Payment Confirmed'
                service.save(update_fields=['status'])

                RemittanceRecord.objects.get_or_create(
                    payment_proof=proof,
                    defaults={
                        'service': proof.service,
                        'invoice': proof.invoice,
                        'confirmed_by': sales_representative,
                    },
                )

            return redirect('sales_representative_payment_proofs')

        if action == 'reject':
            if not rejection_reason:
                errors['rejection_reason'] = 'Rejection reason is required.'
            else:
                with transaction.atomic():
                    proof.status = PaymentProof.STATUS_REJECTED
                    proof.validated_at = timezone.now()
                    proof.validated_by = sales_representative
                    proof.rejection_reason = rejection_reason
                    proof.save(update_fields=['status', 'validated_at', 'validated_by', 'rejection_reason'])

                    service = proof.service
                    service.status = 'Pending Payment'
                    service.save(update_fields=['status'])

                return redirect('sales_representative_payment_proofs')

    return render(request, 'sales_representative_review_payment_proof.html', {
        'sales_representative': sales_representative,
        'proof': proof,
        'errors': errors,
    })


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

    _ensure_service_form_default_options()

    selected_section = request.GET.get('section', '').strip()
    if selected_section and selected_section not in SERVICE_FORM_FIELD_CATALOG:
        selected_section = ''

    section_filter_sections = {'Inspection', 'Service Report Submission', 'Payment Proof Submission'}
    section_filter = request.GET.get('field_filter', '').strip()
    legacy_inspection_filter = request.GET.get('inspection_filter', '').strip()
    if not section_filter and selected_section == 'Inspection' and legacy_inspection_filter:
        section_filter = legacy_inspection_filter

    section_filter_options = SERVICE_FORM_FIELD_CATALOG.get(selected_section, []) if selected_section in section_filter_sections else []
    if selected_section not in section_filter_sections:
        section_filter = ''
    elif section_filter and section_filter not in section_filter_options:
        section_filter = ''
    elif not section_filter and section_filter_options:
        section_filter = section_filter_options[0]

    def _build_forms_redirect_url():
        query = []
        if selected_section:
            query.append(f"section={selected_section}")
        if selected_section in section_filter_sections and section_filter:
            query.append(f"field_filter={quote_plus(section_filter)}")
        if query:
            return f"{request.path}?{'&'.join(query)}"
        return reverse('om_service_forms')

    def redirect_forms():
        return redirect(_build_forms_redirect_url())

    managed_by_treatment_fields = {
        ('Inspection', 'Preferred Service'),
        ('Service Report Submission', 'Service Done'),
    }

    payment_type_values = list(ServiceFormOption.objects.filter(
        form_section='Payment Proof Submission',
        field_name='Payment Type',
        is_active=True,
    ).order_by('option_value').values_list('option_value', flat=True))

    if request.method == 'POST':
        action = request.POST.get('action', '').strip()
        option_id = request.POST.get('option_id', '').strip()
        form_section = request.POST.get('form_section', '').strip()
        field_name = request.POST.get('field_name', '').strip()
        option_value = request.POST.get('option_value', '').strip()
        option_description = request.POST.get('option_description', '').strip()
        option_problem_text = request.POST.get('problem_text', '').strip()
        option_recommendation_text = request.POST.get('recommendation_text', '').strip()
        option_target_pest = request.POST.get('target_pest', '').strip()
        option_application_method = request.POST.get('application_method', '').strip()
        option_additional_information = request.POST.get('additional_information', '').strip()
        option_dilution_rate = request.POST.get('dilution_rate', '').strip()
        option_account_number = request.POST.get('account_number', '').strip()
        option_rate_raw = request.POST.get('option_rate', '').strip()
        is_active = request.POST.get('is_active') == 'on'

        is_treatment_service = form_section == 'Treatment' and field_name == 'Treatment Service'
        is_service_report_chemicals_field = (
            form_section == 'Service Report Submission' and
            field_name == 'Chemicals Used'
        )
        is_payment_bank_field = (
            form_section == 'Payment Proof Submission' and
            field_name == 'Bank Used for Payment'
        )
        option_rate = None
        valid_field_names = SERVICE_FORM_FIELD_CATALOG.get(form_section, [])

        if action in {'create', 'update'}:
            if not form_section or field_name not in valid_field_names or not option_value:
                messages.error(request, 'Required fields must be filled in.')
                return redirect_forms()

            if (form_section, field_name) in managed_by_treatment_fields:
                messages.error(request, f'{field_name} options are managed in Treatment.')
                return redirect_forms()

            if is_treatment_service and option_value.strip().lower() == 'other':
                messages.error(request, '"Other" is not allowed for Treatment Service right now.')
                return redirect_forms()

            if is_treatment_service:
                if not option_description or not option_rate_raw:
                    messages.error(request, 'Required fields must be filled in.')
                    return redirect_forms()
                try:
                    option_rate = Decimal(option_rate_raw)
                    if option_rate <= 0:
                        raise InvalidOperation
                except (InvalidOperation, TypeError, ValueError):
                    messages.error(request, 'Treatment Rate must be a valid positive amount.')
                    return redirect_forms()
            elif is_payment_bank_field:
                if not option_account_number:
                    messages.error(request, 'Account Number is required.')
                    return redirect_forms()
                if not option_description:
                    messages.error(request, 'Payment Type is required for bank options.')
                    return redirect_forms()
                if option_description not in payment_type_values:
                    messages.error(request, 'Selected Payment Type is not available.')
                    return redirect_forms()

        if action == 'create':
            if is_service_report_chemicals_field:
                messages.error(request, 'Chemicals Used options are managed under Chemicals.')
                return redirect_forms()

            existing = ServiceFormOption.objects.filter(
                form_section=form_section,
                field_name=field_name,
                option_value__iexact=option_value,
            ).first()

            if existing and existing.is_active:
                messages.error(request, 'Entered option already exists.')
                return redirect_forms()

            if existing and not existing.is_active:
                existing.option_value = option_value
                existing.is_active = True
                existing.option_description = option_description if (is_treatment_service or is_payment_bank_field) else ''
                existing.option_rate = option_rate if is_treatment_service else None
                existing.problem_text = option_problem_text if is_treatment_service else ''
                existing.recommendation_text = option_recommendation_text if is_treatment_service else ''
                existing.target_pest = option_target_pest if is_treatment_service else ''
                existing.application_method = option_application_method if is_treatment_service else ''
                existing.additional_information = option_additional_information if is_treatment_service else ''
                existing.dilution_rate = option_dilution_rate if is_treatment_service else ''
                existing.account_number = option_account_number if is_payment_bank_field else ''
                if existing.scoped_option_id is None:
                    last_scoped_id = ServiceFormOption.objects.filter(
                        form_section=form_section,
                        field_name=field_name,
                    ).aggregate(max_id=Max('scoped_option_id')).get('max_id') or 0
                    existing.scoped_option_id = last_scoped_id + 1
                existing.save(update_fields=['option_value', 'is_active', 'option_description', 'option_rate', 'problem_text', 'recommendation_text', 'target_pest', 'application_method', 'additional_information', 'dilution_rate', 'account_number', 'scoped_option_id', 'updated_at'])
                return redirect_forms()

            last_scoped_id = ServiceFormOption.objects.filter(
                form_section=form_section,
                field_name=field_name,
            ).aggregate(max_id=Max('scoped_option_id')).get('max_id') or 0

            ServiceFormOption.objects.create(
                form_section=form_section,
                field_name=field_name,
                scoped_option_id=last_scoped_id + 1,
                option_value=option_value,
                option_description=option_description if (is_treatment_service or is_payment_bank_field) else '',
                option_rate=option_rate if is_treatment_service else None,
                problem_text=option_problem_text if is_treatment_service else '',
                recommendation_text=option_recommendation_text if is_treatment_service else '',
                target_pest=option_target_pest if is_treatment_service else '',
                application_method=option_application_method if is_treatment_service else '',
                additional_information=option_additional_information if is_treatment_service else '',
                dilution_rate=option_dilution_rate if is_treatment_service else '',
                account_number=option_account_number if is_payment_bank_field else '',
                is_active=True,
            )
            return redirect_forms()

        if action == 'update':
            if not option_id.isdigit():
                messages.error(request, 'Invalid field option.')
                return redirect_forms()

            option = ServiceFormOption.objects.filter(id=int(option_id)).first()
            if not option:
                messages.error(request, 'Field option not found.')
                return redirect_forms()

            if option.form_section == 'Service Report Submission' and option.field_name == 'Chemicals Used':
                # Lock value changes for Chemicals Used; manage names in Chemicals page.
                form_section = option.form_section
                option_value = option.option_value

            duplicate = ServiceFormOption.objects.filter(
                form_section=form_section,
                field_name=field_name,
                option_value__iexact=option_value,
                is_active=True,
            ).exclude(id=option.id).exists()

            if duplicate:
                messages.error(request, 'Entered option already exists.')
                return redirect_forms()

            option.form_section = form_section
            option.field_name = field_name
            option.option_value = option_value
            option.option_description = option_description if (is_treatment_service or is_payment_bank_field) else ''
            option.option_rate = option_rate if is_treatment_service else None
            option.problem_text = option_problem_text if is_treatment_service else ''
            option.recommendation_text = option_recommendation_text if is_treatment_service else ''
            option.target_pest = option_target_pest if is_treatment_service else ''
            option.application_method = option_application_method if is_treatment_service else ''
            option.additional_information = option_additional_information if is_treatment_service else ''
            option.dilution_rate = option_dilution_rate if is_treatment_service else ''
            option.account_number = option_account_number if is_payment_bank_field else ''
            option.is_active = is_active
            update_fields = ['form_section', 'field_name', 'option_value', 'option_description', 'option_rate', 'problem_text', 'recommendation_text', 'target_pest', 'application_method', 'additional_information', 'dilution_rate', 'account_number', 'is_active', 'updated_at']
            option.save(update_fields=update_fields)
            return redirect_forms()

        if action == 'delete':
            if not option_id.isdigit():
                messages.error(request, 'Invalid field option.')
                return redirect_forms()

            option = ServiceFormOption.objects.filter(id=int(option_id)).first()
            if not option:
                messages.error(request, 'Field option not found.')
                return redirect_forms()

            if (option.form_section, option.field_name) in managed_by_treatment_fields:
                messages.error(request, f'{option.field_name} options are managed in Treatment.')
                return redirect_forms()

            if not option.is_active:
                messages.info(request, 'Field option is already inactive.')
                return redirect_forms()

            option.is_active = False
            option.save(update_fields=['is_active', 'updated_at'])
            messages.success(request, 'Field option deleted successfully.')
            return redirect_forms()

        if action == 'hard_delete':
            if not option_id.isdigit():
                messages.error(request, 'Invalid field option.')
                return redirect_forms()

            option = ServiceFormOption.objects.filter(id=int(option_id)).first()
            if not option:
                messages.error(request, 'Field option not found.')
                return redirect_forms()

            if (option.form_section, option.field_name) in managed_by_treatment_fields:
                messages.error(request, f'{option.field_name} options are managed in Treatment.')
                return redirect_forms()

            option.delete()
            messages.success(request, 'Field option permanently deleted.')
            return redirect_forms()

        messages.error(request, 'Unsupported action.')
        return redirect_forms()

    options_qs = ServiceFormOption.objects.all()
    options_qs = options_qs.exclude(
        form_section='Treatment',
        field_name='Treatment Service',
        option_value__iexact='Other',
    )
    if selected_section == 'Treatment':
        options_qs = options_qs.filter(form_section='Treatment')
    elif selected_section in section_filter_sections:
        options_qs = options_qs.filter(form_section=selected_section)
        if section_filter:
            options_qs = options_qs.filter(field_name=section_filter)
    else:
        options_qs = options_qs.filter(is_active=True)
        if selected_section:
            options_qs = options_qs.filter(form_section=selected_section)

    active_options = options_qs.order_by('form_section', 'field_name', 'scoped_option_id', 'option_value')

    grouped_options = defaultdict(lambda: defaultdict(list))
    option_rows = []
    for option in active_options:
        grouped_options[option.form_section][option.field_name].append(option)
        option_rows.append({
            'id': option.id,
            'scoped_option_id': option.scoped_option_id,
            'form_section': option.form_section,
            'field_name': option.field_name,
            'option_value': option.option_value,
            'option_description': option.option_description,
            'problem_text': option.problem_text,
            'recommendation_text': option.recommendation_text,
            'target_pest': option.target_pest,
            'application_method': option.application_method,
            'additional_information': option.additional_information,
            'dilution_rate': option.dilution_rate,
            'account_number': option.account_number,
            'option_rate': option.option_rate,
            'is_active': option.is_active,
        })

    if selected_section == 'Treatment':
        for index, row in enumerate(option_rows, start=1):
            row['treatment_display_id'] = index

    return render(request, 'om_service_forms.html', {
        'om': om,
        'field_catalog': SERVICE_FORM_FIELD_CATALOG,
        'field_catalog_json': json.dumps(SERVICE_FORM_FIELD_CATALOG),
        'grouped_options': dict(grouped_options),
        'option_rows': option_rows,
        'selected_section': selected_section,
        'section_filter': section_filter,
        'section_filter_options': section_filter_options,
        'payment_type_options': payment_type_values,
        'is_managed_by_treatment': (selected_section, section_filter) in managed_by_treatment_fields,
    })


def om_service_items(request):
    if 'om_id' not in request.session:
        return redirect('login')

    try:
        om = OperationsManager.objects.get(id=request.session['om_id'])
    except OperationsManager.DoesNotExist:
        request.session.flush()
        return redirect('login')

    treatment_names = _get_treatment_service_names()

    if request.method == 'POST':
        action = request.POST.get('action', '').strip()
        item_id = request.POST.get('item_id', '').strip()

        if action in {'create', 'update'}:
            name = request.POST.get('name', '').strip()
            default_unit_price_raw = request.POST.get('default_unit_price', '').strip()
            is_active = request.POST.get('is_active') == 'on'

            if not name:
                messages.error(request, 'Service item name is required.')
                return redirect('om_service_items')

            if name.strip().lower() in treatment_names:
                messages.error(request, 'This is a Treatment Service option. Manage it under Service Forms > Treatment.')
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
                    existing_item.default_unit_price = default_unit_price
                    existing_item.is_active = True
                    existing_item.save(update_fields=['name', 'default_unit_price', 'is_active'])
                    messages.success(request, 'Service item restored successfully.')
                    return redirect('om_service_items')
                InvoiceItemOption.objects.create(
                    name=name,
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
            service_item.default_unit_price = default_unit_price
            service_item.is_active = is_active
            service_item.save(update_fields=['name', 'default_unit_price', 'is_active'])
            messages.success(request, 'Service item updated successfully.')
            return redirect('om_service_items')

        if action == 'hard_delete':
            if not item_id.isdigit():
                messages.error(request, 'Invalid service item.')
                return redirect('om_service_items')

            service_item = InvoiceItemOption.objects.filter(id=int(item_id)).first()
            if not service_item:
                messages.error(request, 'Service item not found.')
                return redirect('om_service_items')

            service_item.delete()
            messages.success(request, 'Service item permanently deleted.')
            return redirect('om_service_items')

        messages.error(request, 'Unsupported action.')
        return redirect('om_service_items')

    service_items = [
        item
        for item in InvoiceItemOption.objects.order_by('name')
        if item.name.strip().lower() not in treatment_names
    ]

    service_item_rows = []
    for item in service_items:
        service_item_rows.append({
            'id': item.id,
            'name': item.name,
            'default_unit_price': item.default_unit_price,
            'is_active': item.is_active,
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

        if action == 'hard_delete':
            if not chemical_id.isdigit():
                messages.error(request, 'Invalid chemical.')
                return redirect('om_chemicals')

            chemical = Chemical.objects.filter(id=int(chemical_id)).first()
            if not chemical:
                messages.error(request, 'Chemical not found.')
                return redirect('om_chemicals')

            chemical.delete()
            messages.success(request, 'Chemical permanently deleted.')
            return redirect('om_chemicals')

        messages.error(request, 'Unsupported action.')
        return redirect('om_chemicals')

    chemical_rows = []
    for chemical in Chemical.objects.order_by('name'):
        chemical_rows.append({
            'id': chemical.id,
            'name': chemical.name,
            'standard_unit_measure': chemical.standard_unit_measure,
            'is_active': chemical.is_active,
        })

    return render(request, 'om_chemicals.html', {
        'om': om,
        'chemicals': chemical_rows,
    })


def om_invoice_items(request):
    return redirect('om_service_items')


def om_manage_accounts(request):
    """Category entry screen for account management."""
    if 'om_id' not in request.session:
        return redirect('login')

    try:
        om = OperationsManager.objects.get(id=request.session['om_id'])
    except OperationsManager.DoesNotExist:
        request.session.flush()
        return redirect('login')

    return render(request, 'om_manage_accounts_category.html', {'om': om})


def om_manage_technician_accounts(request):
    """Technician account management screen."""
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
                return render(request, 'om_manage_staff_accounts.html', {
                    'om': om,
                    'accounts': Technician.objects.all().order_by('technician_id'),
                    'errors': errors,
                    'form_data': request.POST,
                    'account_type': 'technician',
                    'page_heading': 'Technician Accounts',
                    'role_label': 'Technician',
                    'role_slug': 'technician',
                    'id_header': 'Technician ID',
                    'list_title': 'Technician Accounts',
                    'create_hint': 'Technician ID and email are auto-generated as tech[ID]@companyemail.com',
                    'create_action': 'create_technician',
                    'deactivate_action': 'delete_technician',
                    'reactivate_action': 'reactivate_technician',
                    'hard_delete_action': 'hard_delete_technician',
                    'pk_field_name': 'technician_pk',
                    'edit_url_name': 'om_edit_technician_account',
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
            return redirect('om_manage_technician_accounts')

        if action == 'delete_technician':
            technician_pk = request.POST.get('technician_pk', '').strip()
            technician = Technician.objects.filter(id=technician_pk).first()
            if technician:
                technician.is_active = False
                technician.save(update_fields=['is_active'])
            return redirect('om_manage_technician_accounts')

        if action == 'reactivate_technician':
            technician_pk = request.POST.get('technician_pk', '').strip()
            technician = Technician.objects.filter(id=technician_pk).first()
            if technician:
                technician.is_active = True
                technician.save(update_fields=['is_active'])
            return redirect('om_manage_technician_accounts')

        if action == 'hard_delete_technician':
            technician_pk = request.POST.get('technician_pk', '').strip()
            technician = Technician.objects.filter(id=technician_pk).first()
            if technician:
                technician.delete()
            return redirect('om_manage_technician_accounts')

    return render(request, 'om_manage_staff_accounts.html', {
        'om': om,
        'accounts': Technician.objects.all().order_by('technician_id'),
        'errors': {},
        'form_data': {},
        'account_type': 'technician',
        'page_heading': 'Technician Accounts',
        'role_label': 'Technician',
        'role_slug': 'technician',
        'id_header': 'Technician ID',
        'list_title': 'Technician Accounts',
        'create_hint': 'Technician ID and email are auto-generated as tech[ID]@companyemail.com',
        'create_action': 'create_technician',
        'deactivate_action': 'delete_technician',
        'reactivate_action': 'reactivate_technician',
        'hard_delete_action': 'hard_delete_technician',
        'pk_field_name': 'technician_pk',
        'edit_url_name': 'om_edit_technician_account',
    })


def om_manage_sales_accounts(request):
    """Sales representative account management screen."""
    if 'om_id' not in request.session:
        return redirect('login')

    try:
        om = OperationsManager.objects.get(id=request.session['om_id'])
    except OperationsManager.DoesNotExist:
        request.session.flush()
        return redirect('login')

    if request.method == 'POST':
        action = request.POST.get('action', '').strip()

        if action == 'create_sales_representative':
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
                return render(request, 'om_manage_staff_accounts.html', {
                    'om': om,
                    'accounts': SalesRepresentative.objects.all().order_by('created_at'),
                    'errors': errors,
                    'form_data': request.POST,
                    'account_type': 'sales',
                    'page_heading': 'Sales Representative Accounts',
                    'role_label': 'Sales Representative',
                    'role_slug': 'sales representative',
                    'id_header': 'Sales ID',
                    'list_title': 'Sales Representative Accounts',
                    'create_hint': 'Sales Representative ID and email are auto-generated as sales[ID]@companyemail.com',
                    'create_action': 'create_sales_representative',
                    'deactivate_action': 'delete_sales_representative',
                    'reactivate_action': 'reactivate_sales_representative',
                    'hard_delete_action': 'hard_delete_sales_representative',
                    'pk_field_name': 'sales_representative_pk',
                    'edit_url_name': 'om_edit_sales_representative_account',
                })

            pending_email = f"pending-sales-{timezone.now().strftime('%Y%m%d%H%M%S%f')}@companyemail.com"
            sales_representative = SalesRepresentative.objects.create(
                first_name=first_name,
                last_name=last_name,
                password=password,
                email=pending_email,
            )
            generated_email = f'sales{sales_representative.id}@companyemail.com'
            sales_representative.email = generated_email
            sales_representative.save(update_fields=['email'])
            return redirect('om_manage_sales_accounts')

        if action == 'delete_sales_representative':
            sales_representative_pk = request.POST.get('sales_representative_pk', '').strip()
            sr = SalesRepresentative.objects.filter(id=sales_representative_pk).first()
            if sr:
                sr.is_active = False
                sr.save(update_fields=['is_active'])
            return redirect('om_manage_sales_accounts')

        if action == 'reactivate_sales_representative':
            sales_representative_pk = request.POST.get('sales_representative_pk', '').strip()
            sr = SalesRepresentative.objects.filter(id=sales_representative_pk).first()
            if sr:
                sr.is_active = True
                sr.save(update_fields=['is_active'])
            return redirect('om_manage_sales_accounts')

        if action == 'hard_delete_sales_representative':
            sales_representative_pk = request.POST.get('sales_representative_pk', '').strip()
            sr = SalesRepresentative.objects.filter(id=sales_representative_pk).first()
            if sr:
                sr.delete()
            return redirect('om_manage_sales_accounts')

    return render(request, 'om_manage_staff_accounts.html', {
        'om': om,
        'accounts': SalesRepresentative.objects.all().order_by('created_at'),
        'errors': {},
        'form_data': {},
        'account_type': 'sales',
        'page_heading': 'Sales Representative Accounts',
        'role_label': 'Sales Representative',
        'role_slug': 'sales representative',
        'id_header': 'Sales ID',
        'list_title': 'Sales Representative Accounts',
        'create_hint': 'Sales Representative ID and email are auto-generated as sales[ID]@companyemail.com',
        'create_action': 'create_sales_representative',
        'deactivate_action': 'delete_sales_representative',
        'reactivate_action': 'reactivate_sales_representative',
        'hard_delete_action': 'hard_delete_sales_representative',
        'pk_field_name': 'sales_representative_pk',
        'edit_url_name': 'om_edit_sales_representative_account',
    })


def om_manage_customer_accounts(request):
    """Customer account management screen."""
    if 'om_id' not in request.session:
        return redirect('login')

    try:
        om = OperationsManager.objects.get(id=request.session['om_id'])
    except OperationsManager.DoesNotExist:
        request.session.flush()
        return redirect('login')

    if request.method == 'POST':
        action = request.POST.get('action', '').strip()

        if action == 'archive_customer':
            customer_pk = request.POST.get('customer_pk', '').strip()
            customer = Customer.objects.filter(id=customer_pk).first()
            if customer and customer.is_active:
                customer.is_active = False
                customer.save(update_fields=['is_active'])
            return redirect('om_manage_customer_accounts')

        if action == 'reactivate_customer':
            customer_pk = request.POST.get('customer_pk', '').strip()
            customer = Customer.objects.filter(id=customer_pk).first()
            if customer and not customer.is_active:
                customer.is_active = True
                customer.save(update_fields=['is_active'])
            return redirect('om_manage_customer_accounts')

        if action == 'hard_delete_customer':
            customer_pk = request.POST.get('customer_pk', '').strip()
            customer = Customer.objects.filter(id=customer_pk).first()
            if customer and not customer.is_active:
                customer.delete()
            return redirect('om_manage_customer_accounts')

    customers = Customer.objects.annotate(
        property_count=Count('properties', distinct=True),
        service_count=Count('services', distinct=True),
    ).order_by('-created_at')

    return render(request, 'om_manage_customer_accounts.html', {
        'om': om,
        'customers': customers,
        'errors': {},
    })


def om_edit_sales_representative_account(request, sales_representative_pk):
    if 'om_id' not in request.session:
        return redirect('login')

    try:
        om = OperationsManager.objects.get(id=request.session['om_id'])
    except OperationsManager.DoesNotExist:
        request.session.flush()
        return redirect('login')

    sales_representative = SalesRepresentative.objects.filter(id=sales_representative_pk).first()
    if not sales_representative:
        return redirect('om_manage_sales_accounts')

    if request.method == 'POST':
        if request.POST.get('action') == 'cancel':
            return redirect('om_manage_sales_accounts')

        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        new_password = request.POST.get('password', '').strip()

        errors = {}
        if not first_name:
            errors['first_name'] = 'First name is required.'
        if not last_name:
            errors['last_name'] = 'Last name is required.'

        if errors:
            return render(request, 'om_edit_sales_representative_account.html', {
                'om': om,
                'sales_representative': sales_representative,
                'errors': errors,
                'form_data': request.POST,
            })

        sales_representative.first_name = first_name
        sales_representative.last_name = last_name
        update_fields = ['first_name', 'last_name']

        if new_password:
            sales_representative.password = new_password
            update_fields.append('password')

        sales_representative.save(update_fields=update_fields)
        return redirect('om_manage_sales_accounts')

    return render(request, 'om_edit_sales_representative_account.html', {
        'om': om,
        'sales_representative': sales_representative,
        'form_data': {
            'first_name': sales_representative.first_name,
            'last_name': sales_representative.last_name,
        },
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
        return redirect('om_manage_technician_accounts')

    if request.method == 'POST':
        if request.POST.get('action') == 'cancel':
            return redirect('om_manage_technician_accounts')

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
        return redirect('om_manage_technician_accounts')

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

    return render(request, 'service_status_shared.html', {
        'technician': technician,
        'status_role': 'technician',
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
        'back_url': _resolve_back_url(request, 'technician_service_status'),
    })


def technician_view_estimated_bill(request, estimated_bill_id):
    if 'technician_id' not in request.session:
        return redirect('login')

    try:
        Technician.objects.get(id=request.session['technician_id'])
    except Technician.DoesNotExist:
        request.session.flush()
        return redirect('login')

    estimated_bill = EstimatedBill.objects.select_related(
        'service__customer', 'service__property', 'operations_manager'
    ).prefetch_related('items').exclude(
        service__status='Completed'
    ).order_by('-created_at')

    if not estimated_bill:
        return redirect('technician_service_status')

    treatment_rows = []
    for item in estimated_bill.items.all():
        treatment_details = _get_treatment_billing_details(item.service_type)
        treatment_rows.append({
            'service_type': treatment_details['service_type'],
            'quantity': item.quantity,
            'unit_price': item.unit_price,
            'line_total': item.line_total,
            'problem_text': item.problem_text or treatment_details['problem_text'],
            'recommendation_text': item.recommendation_text or treatment_details['recommendation_text'],
        })

    return render(request, 'om_estimated_bill_view.html', {
        'estimated_bill': estimated_bill,
        'role': 'technician',
        'back_url': _resolve_back_url(request, 'technician_service_status'),
        'treatment_rows': treatment_rows,
        'service_type_display': _service_display_treatments(estimated_bill.service),
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
    _ensure_service_form_default_options()
    treatment_service_choices = _get_service_form_choices(
        'Treatment',
        'Treatment Service',
        fallback_values=TREATMENT_SERVICE_PREDEFINED_OPTIONS,
        excluded_values={'Other'},
    )
    service_choices = _get_service_form_choices(
        'Inspection',
        'Preferred Service',
        fallback_values=[label for _, label in Service.PREFERRED_SERVICE_CHOICES],
    )
    pest_choices = _get_service_form_choices(
        'Inspection',
        'Pest Problems',
        fallback_values=[label for _, label in Service.PEST_PROBLEM_CHOICES],
    )

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
            elif treatment_service not in {value for value, _ in treatment_service_choices}:
                errors['treatment_service'] = 'Invalid treatment service selected.'
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
            if preferred_service and preferred_service not in {value for value, _ in service_choices}:
                errors['preferred_service'] = 'Invalid preferred service selected.'
            if pest_problem and pest_problem not in {value for value, _ in pest_choices}:
                errors['pest_problem'] = 'Invalid pest problem selected.'

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
                'service_choices': service_choices,
                'pest_choices': pest_choices,
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
        'service_choices': service_choices,
        'pest_choices': pest_choices,
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

    try:
        technician = Technician.objects.get(id=request.session['technician_id'])
    except Technician.DoesNotExist:
        request.session.flush()
        return redirect('login')

    search = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '').strip()
    services, history_statuses = _get_service_history_queryset(search, status_filter)

    return render(request, 'service_history_shared.html', {
        'technician': technician,
        'history_role': 'technician',
        'services': services,
        'search': search,
        'status_filter': status_filter,
        'status_choices': history_statuses,
    })


def technician_service_reports(request):
    if 'technician_id' not in request.session:
        return redirect('login')

    try:
        technician = Technician.objects.get(id=request.session['technician_id'])
    except Technician.DoesNotExist:
        request.session.flush()
        return redirect('login')

    search = request.GET.get('q', '').strip()

    reports = ServiceReport.objects.select_related(
        'service__customer', 'service__property'
    ).exclude(
        service__status__in=['Payment Confirmed', 'Completed', 'Cancelled']
    ).order_by('-created_at')

    if search:
        reports = reports.filter(
            Q(service__id__icontains=search)
            | Q(service__customer__first_name__icontains=search)
            | Q(service__customer__last_name__icontains=search)
            | Q(service__property__street__icontains=search)
            | Q(service__property__city__icontains=search)
            | Q(service__preferred_service__icontains=search)
        )

    return render(request, 'service_reports_shared.html', {
        'technician': technician,
        'report_role': 'technician',
        'reports': reports,
        'search': search,
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


def _clean_area_rows(raw_rows, infestation_values=None):
    cleaned_rows = []
    has_invalid = False
    valid_infestation_values = set(infestation_values or {'Low', 'Medium', 'High'})

    for row in raw_rows:
        if not isinstance(row, dict):
            continue

        area_name = (row.get('area_name') or '').strip()
        infestation_level = (row.get('infestation_level') or '').strip()
        spray = bool(row.get('spray'))
        mist = bool(row.get('mist'))
        rat_bait = bool(row.get('rat_bait'))
        powder = bool(row.get('powder'))
        date_raw = (row.get('date') or '').strip()
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

        if not area_name or infestation_level not in valid_infestation_values:
            has_invalid = True
            continue

        area_date = None
        if date_raw:
            try:
                area_date = datetime.strptime(date_raw, '%Y-%m-%d').date()
            except ValueError:
                has_invalid = True
                continue

        cleaned_rows.append({
            'area_name': area_name,
            'infestation_level': infestation_level,
            'spray': spray,
            'mist': mist,
            'rat_bait': rat_bait,
            'powder': powder,
            'date': area_date,
            'remarks': remarks,
            'recommendation': recommendation,
        })

    return cleaned_rows, has_invalid


def technician_create_service_report(request):
    if 'technician_id' not in request.session and 'om_id' not in request.session:
        return redirect('login')

    technician = None
    identified_as = 'Technician'
    if request.session.get('technician_id'):
        try:
            technician = Technician.objects.get(id=request.session['technician_id'])
        except Technician.DoesNotExist:
            request.session.flush()
            return redirect('login')
    else:
        try:
            OperationsManager.objects.get(id=request.session['om_id'])
            identified_as = 'Operations Manager'
        except OperationsManager.DoesNotExist:
            request.session.flush()
            return redirect('login')

    draft = request.session.get('tech_service_report_draft', {})
    selected_service_id = draft.get('service_id')
    _ensure_service_form_default_options()
    infestation_choices = _get_active_service_form_option_values(
        'Service Report Submission',
        'Levels of Infestation',
        fallback_values=[label for _, label in ServiceReportArea.INFESTATION_CHOICES],
    )
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

    default_chemicals = draft.get('chemicals') if isinstance(draft.get('chemicals'), list) else []
    default_areas = draft.get('treated_areas') or [
        {
            'area_name': '',
            'infestation_level': infestation_choices[0] if infestation_choices else 'Low',
            'spray': False,
            'mist': False,
            'rat_bait': False,
            'powder': False,
            'date': '',
            'remarks': '',
            'recommendation': '',
        }
    ]

    selectable_services_qs = Service.objects.filter(
        status='Ongoing Treatment',
        service_report__isnull=True,
    ).select_related('customer', 'property', 'estimated_bill').prefetch_related(
        'estimated_bill__items'
    ).order_by('-confirmed_date', '-date', '-created_at')

    selectable_services = list(selectable_services_qs)
    for selectable_service in selectable_services:
        bill = getattr(selectable_service, 'estimated_bill', None)
        bill_item_names = []
        if bill:
            bill_item_names = [
                item.service_type
                for item in bill.items.all()
                if item.service_type
            ]
        selectable_service.service_type_display = ', '.join(_unique_preserve_order(bill_item_names)) if bill_item_names else (selectable_service.preferred_service or '-')

    def render_step_one(errors=None):
        return render(request, 'technician_create_service_report.html', {
            'technician': technician,
            'identified_as': identified_as,
            'step': 'select',
            'services': selectable_services,
            'errors': errors or {},
            'selected_service_id': str(selected_service_id or ''),
        })

    def render_step_two(service, errors=None, chemicals=None, treated_areas=None):
        default_treatment_date = ''
        if service.confirmed_date or service.date:
            default_treatment_date = (service.confirmed_date or service.date).strftime('%Y-%m-%d')

        return render(request, 'technician_create_service_report.html', {
            'technician': technician,
            'identified_as': identified_as,
            'step': 'details',
            'service': service,
            'errors': errors or {},
            'chemicals_json': json.dumps(chemicals if chemicals is not None else default_chemicals),
            'treated_areas_json': json.dumps(treated_areas if treated_areas is not None else default_areas),
            'chemical_choices_json': json.dumps(chemical_choices),
            'infestation_choices_json': json.dumps(infestation_choices),
            'default_treatment_date': default_treatment_date,
        })

    if request.method == 'POST':
        action = request.POST.get('action', '').strip()
        step = request.POST.get('step', 'select').strip()

        if action == 'confirm_cancel':
            request.session.pop('tech_service_report_draft', None)
            if request.session.get('om_id'):
                return redirect('om_service_reports')
            return redirect('technician_service_reports')

        if step == 'select':
            if action == 'continue':
                chosen_service_id = request.POST.get('selected_service_id', '').strip()
                selected_service = selectable_services_qs.filter(id=chosen_service_id).first()

                if not selected_service:
                    return render_step_one({'selected_service': 'Please select an Ongoing Treatment service record.'})

                if str(selected_service_id or '') != str(selected_service.id):
                    default_chemicals = []
                    default_areas = [{
                        'area_name': '',
                        'infestation_level': infestation_choices[0] if infestation_choices else 'Low',
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
                selected_service = selectable_services_qs.filter(id=selected_service_id).first()

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
                treated_areas, area_has_invalid = _clean_area_rows(raw_areas, infestation_values=infestation_choices)

                if chemical_has_invalid:
                    errors['chemicals'] = 'Please complete each filled chemical row with valid values.'

                if not treated_areas:
                    errors['treated_areas'] = 'At least one area must be filled in.'
                elif area_has_invalid:
                    errors['treated_areas'] = 'Please complete each filled treated area row with valid values.'

                if errors:
                    return render_step_two(selected_service, errors=errors, chemicals=raw_chemicals, treated_areas=raw_areas)

                if ServiceReport.objects.filter(service=selected_service).exists():
                    request.session.pop('tech_service_report_draft', None)
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
                            date=row.get('date'),
                            remarks=row['remarks'],
                            recommendation=row['recommendation'],
                        )
                        for row in treated_areas
                    ])

                    # Keep Ongoing Treatment until invoice creation to preserve billing workflow congruence.
                    selected_service.status = 'Ongoing Treatment'
                    selected_service.save(update_fields=['status'])

                request.session.pop('tech_service_report_draft', None)
                return redirect(_service_report_redirect_name(request))

            return render_step_two(selected_service, chemicals=raw_chemicals, treated_areas=raw_areas)

    if selected_service_id:
        selected_service = selectable_services_qs.filter(id=selected_service_id).first()
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
        'back_url': _resolve_back_url(request, 'technician_service_reports'),
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

    _ensure_service_form_default_options()
    infestation_choices = _get_active_service_form_option_values(
        'Service Report Submission',
        'Levels of Infestation',
        fallback_values=[label for _, label in ServiceReportArea.INFESTATION_CHOICES],
    )

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
        treated_areas, area_has_invalid = _clean_area_rows(raw_areas, infestation_values=infestation_choices)

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
                'infestation_choices_json': json.dumps(infestation_choices),
                'back_url': _resolve_back_url(request, _service_report_redirect_name(request)),
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
                    date=row.get('date'),
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
                'date': area.date.isoformat() if area.date else '',
                'remarks': area.remarks,
                'recommendation': area.recommendation,
            }
            for area in report.treated_areas.all()
        ]),
        'back_url': _resolve_back_url(request, _service_report_redirect_name(request)),
        'chemical_choices_json': json.dumps(chemical_choices),
        'infestation_choices_json': json.dumps(infestation_choices),
        'default_treatment_date': (report.service.confirmed_date or report.service.date).strftime('%Y-%m-%d') if (report.service.confirmed_date or report.service.date) else '',
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
        'back_url': _resolve_back_url(request, 'om_service_reports'),
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

    return render(request, 'service_status_shared.html', {
        'om': om,
        'status_role': 'om',
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
    _ensure_service_form_default_options()
    treatment_service_choices = _get_service_form_choices(
        'Treatment',
        'Treatment Service',
        fallback_values=TREATMENT_SERVICE_PREDEFINED_OPTIONS,
        excluded_values={'Other'},
    )
    service_choices = _get_service_form_choices(
        'Inspection',
        'Preferred Service',
        fallback_values=[label for _, label in Service.PREFERRED_SERVICE_CHOICES],
    )
    pest_choices = _get_service_form_choices(
        'Inspection',
        'Pest Problems',
        fallback_values=[label for _, label in Service.PEST_PROBLEM_CHOICES],
    )

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
            elif treatment_service not in {value for value, _ in treatment_service_choices}:
                errors['treatment_service'] = 'Invalid treatment service selected.'
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
            if preferred_service and preferred_service not in {value for value, _ in service_choices}:
                errors['preferred_service'] = 'Invalid preferred service selected.'
            if pest_problem and pest_problem not in {value for value, _ in pest_choices}:
                errors['pest_problem'] = 'Invalid pest problem selected.'

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
                'service_choices': service_choices,
                'pest_choices': pest_choices,
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
        'service_choices': service_choices,
        'pest_choices': pest_choices,
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
        'back_url': _resolve_back_url(request, 'om_service_status'),
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

    _ensure_service_form_default_options()
    treatment_service_choices = _get_service_form_choices(
        'Treatment',
        'Treatment Service',
        fallback_values=TREATMENT_SERVICE_PREDEFINED_OPTIONS,
        excluded_values={'Other'},
    )
    allowed_treatment_values = {value for value, _ in treatment_service_choices}

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
        elif any(value not in allowed_treatment_values for value in selected_treatment_services):
            errors['treatment_service'] = 'Invalid treatment service selected.'
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

            return redirect('om_service_status')

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
