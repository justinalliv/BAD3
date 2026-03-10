from django.db import models


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
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email})"

    class Meta:
        db_table = 'customers'


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
    country = models.CharField(max_length=100)
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


class ServiceReportChemical(models.Model):
    report = models.ForeignKey(ServiceReport, on_delete=models.CASCADE, related_name='chemicals')
    chemical_name = models.CharField(max_length=255)
    unit_measure = models.CharField(max_length=50)
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


class InvoiceItem(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='items')
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
