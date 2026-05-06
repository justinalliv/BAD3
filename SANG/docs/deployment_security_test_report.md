# Deployment Security Test Report

Date: 2026-05-06
Project: SANG Django web application

Security testing reduces deployment risk, but it does not guarantee the website can never be hacked. This report documents the pre-hosting security checks run against the current codebase and the fixes applied for identified issues.

Validation command:

```bash
python manage.py test sangapp
```

Result: `35 tests OK`

## Test Results

| Test Case ID | Security Area | Account Type Tested | Steps Performed | Expected Result | Actual Result | Pass/Fail | Severity if Failed | Fix Applied | Retest Result |
|---|---|---|---|---|---|---|---|---|---|
| SEC-AUTH-001 | Authentication security | Customer, OM, Technician, Sales | Submit valid credentials for each role. | Each user reaches only their own role homepage. | Each valid login redirects to the correct homepage. | PASS | Critical | Existing login flow retained; password hash support added. | PASS |
| SEC-AUTH-002 | Authentication security | Public | Submit invalid, empty, repeated failed, and SQL-like login credentials. | Login is rejected and no session is created. | Requests return `401`; no authenticated session is created. | PASS | Critical | Added regression coverage for failed login attempts and SQL-like input. | PASS |
| SEC-AUTH-003 | Session security | Customer | Logout, use browser-back equivalent, access protected page after logout, and use invalid session ID. | Protected pages require active valid session. | Logout flushes session; protected routes redirect to Login; invalid session is cleared. | PASS | High | Added no-cache headers for protected routes and session account validation. | PASS |
| SEC-RBAC-001 | Role-based access control | Customer | Manually request OM, Technician, and Sales routes. | Customer is blocked and redirected to Customer homepage. | Access is blocked before restricted content renders. | PASS | Critical | Added `RoleAccessMiddleware`. | PASS |
| SEC-RBAC-002 | Role-based access control | Technician | Manually request Customer, OM, and Sales routes. | Technician is blocked and redirected to Technician homepage. | Access is blocked before restricted content renders. | PASS | Critical | Added `RoleAccessMiddleware`. | PASS |
| SEC-RBAC-003 | Role-based access control | Sales | Manually request Customer, Technician, and OM routes. | Sales user is blocked and redirected to Sales homepage. | Access is blocked before restricted content renders. | PASS | Critical | Added `RoleAccessMiddleware`. | PASS |
| SEC-RBAC-004 | Role-based access control | OM | Manually request Customer, Technician, and Sales-only routes. | OM is blocked from routes outside intended OM permissions. | Access is blocked before restricted content renders. | PASS | Critical | Added `RoleAccessMiddleware`. | PASS |
| SEC-RBAC-005 | Public route protection | Public | Request authenticated Customer, OM, Technician, and Sales pages. | User is redirected to Login. | Protected routes redirect to Login. | PASS | Critical | Middleware and existing view checks enforce authentication. | PASS |
| SEC-URL-001 | URL manipulation protection | All roles | Type restricted URLs such as `/om/home/`, `/technician/home/`, `/sales-representative/home/`, and customer routes. | Wrong-role access is blocked. | Wrong-role requests redirect to the correct role homepage. | PASS | Critical | Added backend route guard middleware. | PASS |
| SEC-URL-002 | Object ID manipulation | Customer, Technician | Change property, service, invoice, payment proof, booking, and report IDs in URLs. | User cannot view or change unauthorized records. | Requests redirect or return not found without exposing restricted data. | PASS | Critical | Preserved customer ownership filters; added technician service/report query filters. | PASS |
| SEC-API-001 | API permission enforcement | Public and wrong-role users | Send JSON-style requests to protected routes while logged out and with wrong role. | Logged-out request returns `401`; wrong-role request returns `403`. | JSON requests return `401` or `403` with no restricted data. | PASS | High | Middleware now distinguishes HTML redirects from API-style responses. | PASS |
| SEC-OBJ-001 | Object-level access | Customer | Try to view another customer’s property, booking, invoice, and payment proof file. | Access is denied. | Other-customer records are not shown; unauthorized proof file redirects. | PASS | Critical | Existing customer ownership checks verified and covered. | PASS |
| SEC-OBJ-002 | Object-level access | Technician | Try to access completed services and reports not owned by the technician. | Access is denied. | Requests redirect to Technician service/report pages. | PASS | Critical | Added technician service/report scoped query helpers. | PASS |
| SEC-OBJ-003 | Object-level access | Sales | Access payment validation and remittance views through Sales-only routes. | Sales access is limited to existing payment/remittance scope. | Non-Sales users are blocked; Sales payment validation flow remains functional. | PASS | High | Middleware enforces Sales-only route access. | PASS |
| SEC-INPUT-001 | Input validation | Customer | Submit missing required fields, invalid values, invalid phone/email/date/amount, special characters, and SQL-like values. | Invalid input is rejected or safely handled. | Validation rejects bad required values; SQL-like search does not crash or expose data. | PASS | Medium | Added SQL-like search and malformed ID regression tests. | PASS |
| SEC-XSS-001 | Cross-site scripting protection | Customer | Store `<script>alert("xss")</script>` in a rendered property field and view the list page. | Script is escaped and does not execute. | Raw script does not appear; escaped HTML is rendered. | PASS | Critical | Django template escaping verified by regression test. | PASS |
| SEC-SQL-001 | SQL injection protection | Public, Customer | Use SQL-like input in login, search, ID path, and form fields. | No login bypass, crash, data leak, or incorrect data modification. | Login remains rejected; search and malformed ID are safely handled. | PASS | Critical | ORM-backed queries verified by tests. | PASS |
| SEC-FILE-001 | File upload security | Customer | Upload valid PDF proof and invalid spoofed PDF/script content. | Only valid JPG, PNG, or PDF content is accepted. | Spoofed file is rejected; valid PDF signature is accepted. | PASS | Critical | Added file signature validation in addition to extension checks. | PASS |
| SEC-FILE-002 | Uploaded file access | Customer, OM, Sales | Open uploaded proof file as authorized roles and as another customer. | Authorized roles can view; unauthorized users cannot. | Authorized roles receive file; another customer is redirected. | PASS | Critical | Existing file access view verified by tests. | PASS |
| SEC-PASS-001 | Password security | Customer, OM, Technician, Sales | Create accounts, sign up, change passwords, and inspect edit pages. | Passwords are not stored or displayed in plain text. | New/changed passwords are hashed; legacy passwords upgrade on login; OM edit pages no longer display current passwords. | PASS | Critical | Added Django password hashing helpers and removed password display fields. | PASS |
| SEC-CSRF-001 | CSRF protection | Customer | Submit state-changing POST without CSRF token. | Request is rejected. | Request returns `403`; no record is created. | PASS | High | Django CSRF middleware verified with enforced-CSRF test client. | PASS |
| SEC-ERR-001 | Error handling | Public, Customer | Trigger invalid route, invalid record ID, unauthorized access, invalid upload, and invalid API-style request. | No stack traces, secrets, server paths, or database errors are exposed. | Requests return redirect, `404`, `401`, `403`, or safe validation error. | PASS | Medium | Added tests for malformed ID and API-style blocked requests. | PASS |
| SEC-DATA-001 | Sensitive data exposure | OM, all roles | Inspect rendered account edit pages and security-sensitive responses. | Passwords, secret keys, DB credentials, and other users’ private data are not exposed. | Password values are not rendered; unauthorized data routes are blocked. | PASS | Critical | Removed password display fields; route and object checks verified. | PASS |
| SEC-CONFIG-001 | Production configuration security | Deployment config | Check `DEBUG`, `SECRET_KEY`, allowed hosts, HTTPS, secure cookie settings, and trusted origins. | Production settings are environment-driven and safe when `DJANGO_DEBUG=False`. | Settings now require `DJANGO_SECRET_KEY` when debug is off and enable secure cookies/SSL settings by default in production mode. | PASS | Critical | Replaced hardcoded production secret/debug assumptions with environment-driven settings. | PASS |
| SEC-BACKUP-001 | Backup access security | Deployment files | Check for local database/backup artifacts tracked by git. | Local DB/backup files are not deployed or publicly accessible. | `SANG/db.sqlite3` was tracked; removed from git index while keeping local file. | PASS | Critical | `.gitignore` already ignores `*.sqlite3`; removed tracked SQLite DB from index. | PASS |
| SEC-HTTPS-001 | HTTPS readiness | Deployment config | Review HTTPS settings for login, signup, upload, payment validation, and account pages. | Production uses HTTPS and avoids mixed sensitive HTTP transactions. | App settings enable SSL redirect and secure cookies when `DJANGO_DEBUG=False`; live certificate verification must be repeated on the hosting provider. | PASS | High | Added environment-driven HTTPS readiness settings. | PASS |

## Final Hosting Validation

- Critical and High issues found during this pass were fixed and retested.
- No unauthorized role can access restricted pages by direct URL manipulation in automated tests.
- API-style protected requests return `401` or `403` without restricted data.
- Customer and technician object-level ID manipulation is blocked by backend checks.
- Payment proof uploads are restricted by extension, size, ownership, and file signature validation.
- SQL-like and XSS-like inputs are safely handled in tested paths.
- Production settings are ready to be driven by deployment environment variables.
- `SANG/db.sqlite3` must remain untracked and must not be uploaded to public hosting storage.
- HTTPS must still be verified on the live hosting provider after the domain and TLS certificate are configured.

Do not deploy if any future Critical or High security test fails.
