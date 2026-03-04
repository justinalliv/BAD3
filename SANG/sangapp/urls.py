
from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('signup/', views.signup, name='signup'),
    path('login/', views.login, name='login'),
    path('logout/', views.logout, name='logout'),
    path('profile/', views.profile, name='profile'),
    path('profile/edit/', views.edit_profile, name='edit_profile'),
    path('profile/change-password/', views.change_password, name='change_password'),
    path('pending-payment/', views.pending_payment, name='pending_payment'),
    path('payment-instructions/', views.payment_instructions, name='payment_instructions'),
    path('submit-payment-proof/', views.submit_payment_proof, name='submit_payment_proof'),
    path('properties/', views.property_list, name='property_list'),
    path('properties/register/', views.register_property, name='register_property'),
    path('properties/<int:property_id>/edit/', views.edit_property, name='edit_property'),
    path('properties/<int:property_id>/delete/', views.delete_property, name='delete_property'),
    path('book-inspection/', views.book_inspection, name='book_inspection'),
    path('service-status/', views.service_status, name='service_status'),
    path('om/home/', views.om_home, name='om_home'),
    path('om/profile/', views.om_profile, name='om_profile'),
    path('om/profile/change-password/', views.om_change_password, name='om_change_password'),
    path('om/service-history/', views.om_service_history, name='om_service_history'),
    path('om/billing/', views.om_billing, name='om_billing'),
    path('om/service-status/', views.om_service_status, name='om_service_status'),
    path('om/service-status/<int:service_id>/book-treatment/', views.om_book_treatment, name='om_book_treatment'),
    path('om/service-reports/', views.om_service_reports, name='om_service_reports'),
    path('om/remittance-records/', views.om_remittance_records, name='om_remittance_records'),
    path('om/manage-service-forms/', views.om_manage_service_forms, name='om_manage_service_forms'),
    path('om/manage-accounts/', views.om_manage_accounts, name='om_manage_accounts'),
]
