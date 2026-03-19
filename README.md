# BAD3 Use Case Backlog

This document lists the current use cases (UCs) in the system and groups them by backlog status.

## UC Master List

| UC ID | Use Case | Description | Current Status |
|---|---|---|---|
| UC-01 | Customer Sign Up | Register a new customer account with validation for duplicate email and phone. | Done |
| UC-02 | Unified Login | Log in as Customer, Operations Manager, or Technician from one login page. | Done |
| UC-03 | Logout | End active session and return user to home page. | Done |
| UC-04 | Customer Profile Management | View profile and update customer information (name, phone). | Done |
| UC-05 | Customer Change Password | Change customer password with current password and confirmation validation. | Done |
| UC-06 | Register Property | Add a customer property with full address and floor-area validation. | Done |
| UC-07 | Edit Property | Modify an existing registered property record. | Done |
| UC-08 | Delete Property | Remove a registered property owned by the logged-in customer. | Done |
| UC-09 | Book Inspection | Create a new service booking for inspection with preferred service, issue, date, and time. | Done |
| UC-10 | Customer Service Status View | View all ongoing customer services (excluding completed/cancelled). | Done |
| UC-11 | Customer Delete Booking | Delete customer booking if still in editable/deletable status. | Done |
| UC-12 | Customer View/Confirm Estimated Bill | View estimated bill details and confirm bill to move workflow forward. | Done |
| UC-13 | Customer View Service Report | View finalized service report details for own service. | Done |
| UC-14 | OM Dashboard & Profile | Access OM home/profile pages and account context. | Done |
| UC-15 | OM Change Password | Change OM password with required-field and match checks. | Done |
| UC-16 | OM Service Status Monitoring | View and sort ongoing service records in workflow order. | Done |
| UC-17 | OM Update Service Status | Transition service statuses based on allowed workflow rules and required dates/times. | Testing |
| UC-18 | OM View/Edit/Delete Booking | View booking details, edit booking fields, and delete valid bookings. | Testing |
| UC-19 | OM Book Treatment | Create treatment bookings and move service into treatment flow. | Testing |
| UC-20 | OM Estimated Bill Management | Create, view, edit, and delete estimated bills with itemized rows and totals. | Testing |
| UC-21 | OM Invoice Management | Create, view, edit, delete invoices and update service to pending payment. | Testing |
| UC-22 | OM Download Invoice PDF | Generate and download invoice PDF document. | Testing |
| UC-23 | OM Manage Technician Accounts | Create, edit, change password, and delete technician accounts. | Done |
| UC-24 | OM View Service Reports | Browse and view service reports created for treatment services. | Done |
| UC-25 | Technician Dashboard & Profile | Access technician home/profile pages and account context. | Done |
| UC-26 | Technician Service Status Monitoring | View and sort ongoing service records assigned to technician role view. | Done |
| UC-27 | Technician Update/Edit/Delete Booking | Update allowed status, edit booking details, and delete valid bookings. | Testing |
| UC-28 | Technician Service Report Management | Create, view, edit, and delete service reports with chemicals and treated areas. | Testing |
| UC-29 | Pending Payment Page | Display customer pending payment page. | In Progress |
| UC-30 | Payment Instructions Page | Display payment channel/instruction screen for customer. | In Progress |
| UC-31 | Submit Payment Proof | Validate payment proof form and uploaded file type/size. | In Progress |
| UC-32 | OM Service History Module | OM service history page is currently placeholder-only. | Product Backlog |
| UC-33 | OM Remittance Records Module | OM remittance records page is currently placeholder-only. | Product Backlog |
| UC-34 | OM Manage Service Forms Module | OM manage service forms page is currently placeholder-only. | Product Backlog |
| UC-35 | Technician Service History Module | Technician service history page is currently placeholder-only. | Product Backlog |
| UC-36 | Payment Proof Persistence & Approval | Save payment proofs, review/approve by OM, and update service to payment-confirmed/completed. | Sprint Backlog |

## Product Backlog UCs

| UC ID | Description |
|---|---|
| UC-32 | Implement full OM service history module with persistent data and filters. |
| UC-33 | Implement remittance records workflow and data persistence. |
| UC-34 | Implement service forms management module for OM. |
| UC-35 | Implement technician service history module. |

## Sprint Backlog UCs

| UC ID | Description |
|---|---|
| UC-36 | Implement end-to-end payment proof persistence, OM review, and payment status transitions. |

## In Progress UCs

| UC ID | Description |
|---|---|
| UC-29 | Pending payment screen exists but is currently display-only (no invoice/balance integration). |
| UC-30 | Payment instructions page is available but currently static. |
| UC-31 | Payment proof submission validates inputs/files but does not save records yet. |

## Testing UCs

| UC ID | Description |
|---|---|
| UC-17 | Validate complete status transition paths and date/time requirements in real workflow scenarios. |
| UC-18 | Validate OM booking edit/delete constraints across all allowed statuses. |
| UC-19 | Validate treatment booking flow and status updates for multi-service selections. |
| UC-20 | Validate estimated bill creation/edit/delete edge cases and service-status rollback behavior. |
| UC-21 | Validate invoice lifecycle (create/edit/delete) and impact on payment status. |
| UC-22 | Validate invoice PDF output format/content in different data conditions. |
| UC-27 | Validate technician booking update/edit/delete restrictions by service state. |
| UC-28 | Validate service report lifecycle and data integrity for chemical and treated-area rows. |

## Done UCs

| UC ID | Description |
|---|---|
| UC-01 to UC-16 | Core account, customer profile/property, booking, and OM monitoring features are implemented. |
| UC-23 to UC-26 | Technician account management (OM side) and technician dashboard/status viewing features are implemented. |
