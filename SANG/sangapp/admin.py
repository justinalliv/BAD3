from django.contrib import admin
from .models import Customer, Property, Service

# Register your models here.

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('id', 'first_name', 'last_name', 'email', 'phone_number', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('first_name', 'last_name', 'email', 'phone_number')
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ('id', 'property_name', 'customer', 'city', 'province', 'property_type', 'floor_area', 'created_at')
    list_filter = ('created_at', 'property_type')
    search_fields = ('property_name', 'city', 'province', 'customer__first_name', 'customer__last_name')
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer', 'property', 'preferred_service', 'pest_problem', 'date', 'time_slot', 'status', 'created_at')
    list_filter = ('created_at', 'status', 'date')
    search_fields = ('customer__first_name', 'customer__last_name', 'property__property_name', 'preferred_service', 'pest_problem')
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)

