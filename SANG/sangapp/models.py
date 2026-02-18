from django.db import models
from django.contrib.auth.hashers import make_password

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
        ('For Inspection', 'For Inspection'),
        ('Pending Payment', 'Pending Payment'),
        ('Scheduled', 'Scheduled'),
        ('In Progress', 'In Progress'),
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
    time_slot = models.CharField(max_length=50)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='For Inspection')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Service #{self.id} - {self.customer.first_name} {self.customer.last_name} ({self.status})"

    class Meta:
        db_table = 'services'
        ordering = ['-created_at']
