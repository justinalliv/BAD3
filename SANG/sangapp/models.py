from django.db import models
import builtins


class OperationsManager(models.Model):
    first_name = models.CharField(max_length=100, default='Operations')
    last_name = models.CharField(max_length=100, default='Manager')
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email})"

    class Meta:
        db_table = 'operations_managers'


class Technician(models.Model):
    technician_id = models.CharField(max_length=20, unique=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.technician_id} - {self.first_name} {self.last_name}"

    class Meta:
        db_table = 'technicians'

class Customer(models.Model):
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=11, unique=True)
    password = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email})"

    class Meta:
        db_table = 'customers'


class SalesRepresentative(models.Model):
    first_name = models.CharField(max_length=100, default='Sales')
    last_name = models.CharField(max_length=100, default='Representative')
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email})"

    class Meta:
        db_table = 'sales_representatives'


class Property(models.Model):
    PROPERTY_TYPE_CHOICES = [
        ('Residential', 'Residential'),
        ('Commercial', 'Commercial'),
        ('Industrial', 'Industrial'),
        ('Agricultural', 'Agricultural'),
        ('Mixed Use', 'Mixed Use'),
    ]

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='properties')
    property_name = models.CharField(max_length=255)
    street_number = models.CharField(max_length=100)
    street = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    province = models.CharField(max_length=100)
    zip_code = models.CharField(max_length=20)
    property_type = models.CharField(max_length=50, choices=PROPERTY_TYPE_CHOICES)
    floor_area = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.property_name} ({self.city}, {self.province})"

    class Meta:
        db_table = 'properties'
        unique_together = ('customer', 'property_name')


class Service(models.Model):
    STATUS_CHOICES = [
        ('For Confirmation', 'For Confirmation'),
        ('For Inspection', 'For Inspection'),
        ('Ongoing Inspection', 'Ongoing Inspection'),
        ('Estimated Bill Created', 'Estimated Bill Created'),
        ('For Booking', 'For Booking'),
        ('For Treatment', 'For Treatment'),
        ('Ongoing Treatment', 'Ongoing Treatment'),
        ('Pending Payment', 'Pending Payment'),
        ('Payment Confirmed', 'Payment Confirmed'),
        ('Completed', 'Completed'),
        ('Cancelled', 'Cancelled'),
    ]

    PREFERRED_SERVICE_CHOICES = [
        ('General Pest Control Treatment', 'General Pest Control Treatment'),
        ('Termite Control', 'Termite Control'),
        ('Rodent Control', 'Rodent Control'),
        ('Mosquito Control', 'Mosquito Control'),
        ('Bed Bug Treatment', 'Bed Bug Treatment'),
        ('Cockroach Control', 'Cockroach Control'),
        ('Other', 'Other'),
    ]

    PEST_PROBLEM_CHOICES = [
        ('Termites', 'Termites'),
        ('Rodents', 'Rodents'),
        ('Mosquitoes', 'Mosquitoes'),
        ('Bed Bugs', 'Bed Bugs'),
        ('Cockroaches', 'Cockroaches'),
        ('Ants', 'Ants'),
        ('Flies', 'Flies'),
        ('Spiders', 'Spiders'),
        ('Other', 'Other'),
    ]

    TIME_SLOT_CHOICES = [
        ('8:00 AM - 9:00 AM', '8:00 AM - 9:00 AM'),
        ('9:00 AM - 10:00 AM', '9:00 AM - 10:00 AM'),
        ('10:00 AM - 11:00 AM', '10:00 AM - 11:00 AM'),
        ('11:00 AM - 12:00 PM', '11:00 AM - 12:00 PM'),
        ('1:00 PM - 2:00 PM', '1:00 PM - 2:00 PM'),
        ('2:00 PM - 3:00 PM', '2:00 PM - 3:00 PM'),
        ('3:00 PM - 4:00 PM', '3:00 PM - 4:00 PM'),
        ('4:00 PM - 5:00 PM', '4:00 PM - 5:00 PM'),
    ]

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='services')
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='services')
    preferred_service = models.CharField(max_length=255)
    preferred_service_other = models.CharField(max_length=255, blank=True, null=True)
    pest_problem = models.CharField(max_length=255)
    pest_problem_other = models.CharField(max_length=255, blank=True, null=True)
    date = models.DateField()
    confirmed_date = models.DateField(blank=True, null=True)
    inspection_confirmed_date = models.DateField(blank=True, null=True)
    inspection_confirmed_time = models.CharField(max_length=50, blank=True, null=True)
    treatment_confirmed_date = models.DateField(blank=True, null=True)
    treatment_confirmed_time = models.CharField(max_length=50, blank=True, null=True)
    time_slot = models.CharField(max_length=50)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='For Confirmation')
    om_seen_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Service #{self.id} - {self.customer.first_name} {self.customer.last_name} ({self.status})"

    @builtins.property
    def treatment_summary(self):
        estimated_bill = getattr(self, 'estimated_bill', None)
        if estimated_bill:
            names = [item.service_type for item in estimated_bill.items.all() if item.service_type]
            if names:
                ordered = []
                seen = set()
                for name in names:
                    normalized = name.strip().lower()
                    if normalized in seen:
                        continue
                    seen.add(normalized)
                    ordered.append(name)
                return ', '.join(ordered)

        invoice = self.invoices.order_by('-created_at').first()
        if invoice:
            names = [item.item_type for item in invoice.items.all() if item.item_type]
            if names:
                ordered = []
                seen = set()
                for name in names:
                    normalized = name.strip().lower()
                    if normalized in seen:
                        continue
                    seen.add(normalized)
                    ordered.append(name)
                return ', '.join(ordered)

        latest_booking = self.treatment_bookings.order_by('-created_at').first()
        if latest_booking and latest_booking.treatment_service:
            return latest_booking.treatment_service

        return self.preferred_service or '-'

    class Meta:
        db_table = 'services'
        ordering = ['-created_at']


class TreatmentBooking(models.Model):
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='treatment_bookings')
    treatment_service = models.CharField(max_length=255)
    date = models.DateField()
    time_slot = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Treatment Booking #{self.id} for Service #{self.service_id}"

    class Meta:
        db_table = 'treatment_bookings'
        ordering = ['-created_at']


class ServiceReport(models.Model):
    service = models.OneToOneField(Service, on_delete=models.CASCADE, related_name='service_report')
    technician = models.ForeignKey(Technician, on_delete=models.SET_NULL, null=True, blank=True, related_name='service_reports')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Service Report #{self.id} for Service #{self.service_id}"

    class Meta:
        db_table = 'service_reports'
        ordering = ['-created_at']


class Chemical(models.Model):
    name = models.CharField(max_length=255, unique=True)
    standard_unit_measure = models.CharField(max_length=50)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'chemicals'
        ordering = ['name']


class ServiceReportChemical(models.Model):
    report = models.ForeignKey(ServiceReport, on_delete=models.CASCADE, related_name='chemicals')
    chemical = models.ForeignKey(Chemical, on_delete=models.SET_NULL, null=True, blank=True, related_name='usages')
    chemical_name = models.CharField(max_length=255, blank=True)
    unit_measure = models.CharField(max_length=50, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.chemical_name} ({self.amount} {self.unit_measure})"

    class Meta:
        db_table = 'service_report_chemicals'


class ServiceReportArea(models.Model):
    INFESTATION_CHOICES = [
        ('Low', 'Low'),
        ('Medium', 'Medium'),
        ('High', 'High'),
    ]

    report = models.ForeignKey(ServiceReport, on_delete=models.CASCADE, related_name='treated_areas')
    area_name = models.CharField(max_length=255)
    infestation_level = models.CharField(max_length=20, choices=INFESTATION_CHOICES)
    spray = models.BooleanField(default=False)
    mist = models.BooleanField(default=False)
    rat_bait = models.BooleanField(default=False)
    powder = models.BooleanField(default=False)
    date = models.DateField(blank=True, null=True)
    remarks = models.TextField(blank=True)
    recommendation = models.TextField(blank=True)

    def __str__(self):
        return f"{self.area_name} ({self.infestation_level})"

    class Meta:
        db_table = 'service_report_areas'


class EstimatedBill(models.Model):
    service = models.OneToOneField(Service, on_delete=models.CASCADE, related_name='estimated_bill')
    operations_manager = models.ForeignKey(OperationsManager, on_delete=models.SET_NULL, null=True, blank=True, related_name='estimated_bills')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Estimated Bill #{self.id} for Service #{self.service_id}"

    @property
    def total_amount(self):
        return sum((item.line_total for item in self.items.all()), 0)

    class Meta:
        db_table = 'estimated_bills'
        ordering = ['-created_at']


class EstimatedBillItem(models.Model):
    estimated_bill = models.ForeignKey(EstimatedBill, on_delete=models.CASCADE, related_name='items')
    service_type = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    problem_text = models.TextField(blank=True)
    recommendation_text = models.TextField(blank=True)

    def __str__(self):
        return f"{self.service_type} x{self.quantity}"

    @property
    def line_total(self):
        return self.quantity * self.unit_price

    class Meta:
        db_table = 'estimated_bill_items'


class Invoice(models.Model):
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='invoices')
    operations_manager = models.ForeignKey(OperationsManager, on_delete=models.SET_NULL, null=True, blank=True, related_name='invoices')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Invoice #{self.id} for Service #{self.service_id}"

    @property
    def total_amount(self):
        return sum((item.line_total for item in self.items.all()), 0)

    class Meta:
        db_table = 'invoices'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['service'], name='unique_invoice_per_service'),
        ]


class InvoiceItemOption(models.Model):
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    default_unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=1500)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'invoice_item_options'
        ordering = ['name']


class ServiceFormOption(models.Model):
    form_section = models.CharField(max_length=100)
    field_name = models.CharField(max_length=100)
    scoped_option_id = models.PositiveIntegerField(null=True, blank=True)
    option_value = models.CharField(max_length=255)
    option_description = models.TextField(blank=True)
    option_rate = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    problem_text = models.TextField(blank=True)
    recommendation_text = models.TextField(blank=True)
    target_pest = models.CharField(max_length=255, blank=True)
    application_method = models.CharField(max_length=255, blank=True)
    additional_information = models.TextField(blank=True)
    dilution_rate = models.CharField(max_length=255, blank=True)
    account_number = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.form_section} | {self.field_name} | {self.option_value}"

    class Meta:
        db_table = 'service_form_options'
        ordering = ['form_section', 'field_name', 'option_value']
        unique_together = ('form_section', 'field_name', 'option_value')


class InvoiceItem(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='items')
    service_item = models.ForeignKey(InvoiceItemOption, on_delete=models.SET_NULL, null=True, blank=True, related_name='invoice_lines')
    item_type = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return f"{self.item_type} x{self.quantity}"

    @property
    def line_total(self):
        return self.quantity * self.unit_price

    class Meta:
        db_table = 'invoice_items'


class PaymentProof(models.Model):
    STATUS_FOR_VALIDATION = 'For Validation'
    STATUS_VALIDATED = 'Validated'
    STATUS_REJECTED = 'Rejected'

    STATUS_CHOICES = [
        (STATUS_FOR_VALIDATION, STATUS_FOR_VALIDATION),
        (STATUS_VALIDATED, STATUS_VALIDATED),
        (STATUS_REJECTED, STATUS_REJECTED),
    ]

    service = models.OneToOneField(Service, on_delete=models.CASCADE, related_name='payment_proof')
    invoice = models.ForeignKey(Invoice, on_delete=models.SET_NULL, null=True, blank=True, related_name='payment_proofs')
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='payment_proofs')
    payment_type = models.CharField(max_length=100)
    bank_used = models.CharField(max_length=255)
    account_number = models.CharField(max_length=100, blank=True)
    reference_number = models.CharField(max_length=255)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2)
    proof_file = models.FileField(upload_to='payment_proofs/')
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default=STATUS_FOR_VALIDATION)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    validated_at = models.DateTimeField(blank=True, null=True)
    validated_by = models.ForeignKey(SalesRepresentative, on_delete=models.SET_NULL, null=True, blank=True, related_name='validated_payment_proofs')
    rejection_reason = models.TextField(blank=True)

    def __str__(self):
        return f"Payment Proof #{self.id} for Service #{self.service_id}"

    class Meta:
        db_table = 'payment_proofs'
        ordering = ['-uploaded_at']


class RemittanceRecord(models.Model):
    payment_proof = models.OneToOneField(PaymentProof, on_delete=models.CASCADE, related_name='remittance_record')
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='remittance_records')
    invoice = models.ForeignKey(Invoice, on_delete=models.SET_NULL, null=True, blank=True, related_name='remittance_records')
    confirmed_by = models.ForeignKey(SalesRepresentative, on_delete=models.SET_NULL, null=True, blank=True, related_name='remittance_records')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Remittance Record #{self.id} for Service #{self.service_id}"

    class Meta:
        db_table = 'remittance_records'
        ordering = ['-created_at']
