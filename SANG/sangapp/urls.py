
from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('signup/', views.signup, name='signup'),
    path('login/', views.login, name='login'),
    path('customer-home/', views.customer_home, name='customer_home'),
    path('profile/', views.profile, name='profile'),
    path('profile/edit/', views.edit_profile, name='edit_profile'),
    path('pending-payment/', views.pending_payment, name='pending_payment'),
    path('payment-instructions/', views.payment_instructions, name='payment_instructions'),
    path('submit-payment-proof/', views.submit_payment_proof, name='submit_payment_proof'),
    path('properties/', views.property_list, name='property_list'),
    path('properties/register/', views.register_property, name='register_property'),
]
