# Logic Test Matrix

Generated from `sangapp/urls.py`, `sangapp/views.py`, `sangapp/models.py`, and `sangapp/forms.py` before applying logic fixes.

## Public / Not Logged In

- Allowed routes: `home`, `login`, `signup`, `logout`
- Blocked routes: all `profile`, `properties`, `book-inspection`, `service-status`, `om/*`, `technician/*`, and `sales-representative/*` routes
- Available actions: view public home, login, sign up, logout/clear session
- API endpoints used: none; this project exposes Django form routes rather than separate API endpoints
- Database tables touched: `customers` on sign-up; account tables on login reads
- Validation rules involved: required login fields, invalid credentials, inactive account checks, customer sign-up fields, duplicate email and phone checks
- Expected status transitions: none

## Customer

- Allowed routes: `home`, `profile`, `profile/edit`, `profile/change-password`, `properties`, `properties/register`, own property edit/delete, `book-inspection`, `service-status`, own booking/bill/invoice/report/payment routes
- Blocked routes: all `om/*`, `technician/*`, and `sales-representative/*` routes
- Available actions: update profile, change password, register/update/delete own properties, book inspection, delete own pending bookings, view own booking, view own estimated bill, confirm own estimated bill, view own invoice/report, submit or update payment proof when allowed
- API endpoints used: none; form routes write directly through Django views
- Database tables touched: `customers`, `properties`, `services`, `estimated_bills`, `invoices`, `payment_proofs`
- Validation rules involved: required property fields, positive floor area, duplicate property name per customer, required booking fields, valid own property, required “Other” text, required payment fields, file type and file size checks
- Expected status transitions: booking starts `For Confirmation`; estimated bill confirmation moves service to `For Treatment Booking`; payment proof submission starts `For Validation`

## Technician

- Allowed routes: `technician/home`, `technician/profile`, `technician/service-status`, technician booking view/edit/delete, technician estimated bill view, technician service history, technician service report list/create/view/edit/delete
- Blocked routes: customer account routes, `om/*` management routes, and `sales-representative/*` routes
- Available actions: view assigned/general technician queues, update allowed service statuses, update/delete booking data through technician routes, create/edit/delete service reports
- API endpoints used: none; form routes write directly through Django views
- Database tables touched: `technicians`, `services`, `properties`, `treatment_bookings`, `service_reports`, `service_report_chemicals`, `service_report_areas`, `estimated_bills`
- Validation rules involved: allowed status transitions, required booking/report fields, valid treatment service, valid chemical rows, valid treated area rows
- Expected status transitions: `For Inspection` → `Ongoing Inspection`; `For Treatment` → `Ongoing Treatment`

## Sales Representative

- Allowed routes: `sales-representative/home`, `sales-representative/profile`, `sales-representative/service-history`, `sales-representative/service-status`, `sales-representative/payment-proofs`, payment proof review, remittance records, remittance details, invoice view
- Blocked routes: customer account routes, `om/*` management routes, and `technician/*` routes
- Available actions: view payment queue, validate/reject payment proofs, view invoices, view remittance records
- API endpoints used: none; form routes write directly through Django views
- Database tables touched: `sales_representatives`, `payment_proofs`, `services`, `invoices`, `remittance_records`
- Validation rules involved: payment proof must be `For Validation` before review action, rejection reason required when rejecting, invalid/nonexistent proof redirects safely
- Expected status transitions: payment proof `For Validation` → `Validated` with service `Payment Confirmed`; payment proof `For Validation` → `Rejected` with service `Pending Payment`

## Operations Manager

- Allowed routes: `om/home`, `om/profile`, `om/profile/change-password`, service history/status, billing, estimated bills, invoices, service reports, remittance records, service configurations, account management
- Blocked routes: customer account routes, technician-only profile/status routes, and sales-only profile/payment queue routes
- Available actions: update service statuses, view/update/delete bookings, book treatment, create/edit/delete estimated bills and invoices, create/edit/delete service reports, manage service form options, manage chemicals/service items/invoice items, archive/reactivate customer/staff accounts
- API endpoints used: none; form routes write directly through Django views
- Database tables touched: all account tables plus `services`, `properties`, `treatment_bookings`, `estimated_bills`, `estimated_bill_items`, `invoices`, `invoice_items`, `payment_proofs`, `remittance_records`, `service_reports`, `service_report_*`, `service_form_options`, `chemicals`, `invoice_item_options`
- Validation rules involved: allowed status transitions, required confirmation dates/times, valid time slots, billing item parsing, duplicate service forms/configuration items, account activation/archive rules
- Expected status transitions: `For Confirmation` → `For Inspection`; `For Inspection` → `Ongoing Inspection`; `Estimated Bill Created` → `For Treatment Booking`; `For Treatment Booking` → `For Treatment`; `For Treatment` → `Ongoing Treatment`; `Pending Payment` → `Ongoing Treatment` or `Payment Confirmed`; `Payment Confirmed` → `Completed`
