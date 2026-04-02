# SANG (Django Project)

This README can be used as a feature test reference for documentation and professor review.

## 1) Environment Setup

If you cloned this project and get MySQL driver errors, install dependencies first.

### macOS/Linux
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Windows (PowerShell)
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

Install requirements from the folder that contains `manage.py`:

```bash
pip install -r requirements.txt
```

## 2) Database Configuration

This project uses MySQL in `SANG/settings.py` (`django.db.backends.mysql`).

- Database: `sangapp_db`
- Host: `127.0.0.1`
- Port: `3306`
- User: `root`
- Password: empty by default

If your local credentials are different, update `DATABASES` in `SANG/settings.py`.

Run migrations and start server:

```bash
python manage.py migrate
python manage.py runserver
```

## 3) Feature Test Cases (Input/Output)

Use this section as an Input/Output guide for manual testing.

### 3.1 Customer Features

| Feature | Input (Sample) | Expected Output |
|---|---|---|
| Customer Sign Up | First Name=`Juan`, Last Name=`Dela Cruz`, Email=`juan@test.com`, Phone=`09123456789`, Password=`password123` | Account is created, customer is logged in, success state is shown in signup page. |
| Customer Login | Email=`juan@test.com`, Password=`password123` | Session is created and user is redirected to customer home page. |
| Edit Profile | Update First Name, Last Name, Phone=`09987654321` | Profile is updated and reflected in profile page/session name. |
| Change Password | Current=`password123`, New=`newpass123`, Confirm=`newpass123` | Password is updated, success message is shown. |
| Register Property | Property Name=`Main House`, full address fields, Property Type=`Residential`, Floor Area=`120` | Property is saved and appears in property list. |
| Edit Property | Change city/province/floor area | Updated property details are saved and displayed. |
| Delete Property | POST delete on selected property | Property is removed and success state is shown. |
| Book Inspection | Select property, Preferred Service, Pest Problem, Date, Time Slot | Service record is created with `For Confirmation` status. |
| View Service Status | Customer opens service status page | Ongoing services (not Completed/Cancelled) are listed. |
| Delete Booking | Delete service with status `For Confirmation`, `For Inspection`, or `For Treatment` | Service record is deleted and success message appears. |
| View Estimated Bill | Open estimated bill from service status | Estimated bill details are displayed (items and totals). |

### 3.2 Operations Manager (OM) Features

| Feature | Input (Sample) | Expected Output |
|---|---|---|
| OM Login | OM email/password | Session is created and OM is redirected to OM Home. |
| OM Change Password | Current password + valid new password | Password is updated and success state is shown. |
| View Service Status | Open OM service status page | Ongoing services are listed; unseen `For Confirmation` items are marked seen. |
| Update Service Status | Set status to `For Inspection` with date OR `For Treatment` with date | Service status and confirmed date fields are updated. |
| Edit Booking | Change property/service/problem/date/time | Booking fields are updated successfully. |
| Delete Booking | Delete allowed status (`For Confirmation`, `For Inspection`, `For Treatment`) | Service is deleted and success message appears. |
| Create Estimated Bill | Select eligible service + add bill items with quantity | Estimated bill and items are saved; service status changes to `Estimated Bill Created`; customer email notification is sent. |
| Edit Estimated Bill | Modify bill items | Old items are replaced with new items; success message appears. |
| Delete Estimated Bill | Delete selected estimated bill | Bill is deleted; service status reverts to `Ongoing Inspection`. |
| Download Estimated Bill PDF | Click download on estimated bill | PDF file is generated and downloaded. |
| Book Treatment | Select one or more treatment services + date/time | Treatment booking records are created; service status changes to `For Treatment`. |
| Create Invoice | Select eligible service + add invoice items | Invoice and items are saved; service status changes to `Pending Payment`; customer email notification is sent. |
| Edit Invoice | Modify invoice items | Invoice items are replaced and saved. |
| Delete Invoice | Delete selected invoice | Invoice is deleted; service status reverts to `Ongoing Treatment`. |
| Download Invoice PDF | Click download on invoice | Invoice PDF is generated and downloaded. |
| Manage Technician Accounts | Create/edit/delete technician, change password | Technician account records are created/updated/deleted accordingly. |
| View Service Reports | Open service reports list, open a report | Report list and full report details are viewable. |

### 3.3 Technician Features

| Feature | Input (Sample) | Expected Output |
|---|---|---|
| Technician Login | Technician email/password | Session is created and technician is redirected to Technician Home. |
| View Service Status | Open technician service status page | Ongoing services are listed with selected ordering. |
| Update Service Status | Select allowed status (`For Inspection`, `Ongoing Inspection`, `Estimated Bill Created`, `For Treatment`, `Ongoing Treatment`) | Service status is updated and saved. |
| Edit Booking | Update booking fields based on inspection/treatment flow | Booking details are updated successfully. |
| Delete Booking | Delete allowed status booking | Service record is deleted with success message. |
| Create Service Report | Step 1 select service; Step 2 submit chemicals + treated areas | Service report, chemical rows, and treated area rows are saved; success state shown. |
| View Service Report | Open report details | Report content is shown (customer, chemicals, areas). |
| Edit Service Report | Modify chemical and treated area rows | Existing report rows are replaced with edited rows. |
| Delete Service Report | Delete selected report | Report is removed and service status changes back to `Ongoing Treatment`. |
| Download Service Report PDF | Click download on report | Service report PDF is generated and downloaded. |

## 4) Validation and Negative Test Samples

| Scenario | Input | Expected Output |
|---|---|---|
| Duplicate Customer Email on Sign Up | Existing email address | Signup page shows duplicate-email error state. |
| Duplicate Customer Phone on Sign Up/Edit | Existing phone number | Validation error is shown; save is blocked. |
| Invalid Phone Format | Phone not matching `09` + 9 digits | Validation error is shown. |
| Missing Required Fields | Submit forms with blanks | Form returns error: required fields must be filled in. |
| Invalid Quantity/Amount in Bills/Reports | Quantity `0` or non-numeric amount | Validation fails; record is not saved. |
| Unauthorized Access | Open protected URL without session | User is redirected to login page. |

## 5) Current Limitations (For Documentation Transparency)

These pages/features currently exist but are not fully implemented with complete business logic/data persistence:

- OM `Service History` currently uses a placeholder page.
- Technician `Service History` currently uses a placeholder page.
- Sales Representative account passwords are currently stored in plain text (same pattern as other role accounts in this project).

## 6) Notes for Test Execution

- Use separate accounts for Customer, OM, and Technician.
- For billing and service-report tests, ensure prerequisite statuses are set correctly.
- For PDF tests, verify both download trigger and file content fields.
- For email tests, app is configured with `send_mail(..., fail_silently=True)`, so UI success does not always guarantee SMTP delivery in local setups.
