# Final End-to-End Test Case Rundown

Date: 2026-05-06
Project: SANG Django web application

This rundown was performed after the route security, password security, upload validation, production setting, and database-tracking fixes. It does not guarantee the system can never fail or be attacked; it documents the final validation state before hosting.

Final automated validation command:

```bash
python manage.py test sangapp
```

Automated result: `40 tests OK`

Browser/device limitation: Playwright, Selenium, and Chromium are not installed in this environment. Responsive layout was validated by template/CSS contract tests and route rendering tests, but real desktop/tablet/mobile screenshots still need to be verified on a machine with a browser runner or on the hosted site.

## Test Case Matrix

| Test Case ID | Account Type | Screen / Module | Feature / Action | Steps to Test | Expected Result | Actual Result | Pass / Fail | Severity if Failed | Fix Applied | Retest Result |
|---|---|---|---|---|---|---|---|---|---|---|
| FINAL-001 | Public | Home/Login/Signup | Public access | Open public pages while logged out. | Public pages render without authenticated data. | Public pages returned `200`. | PASS | High | None required. | PASS |
| FINAL-002 | Public | Authenticated routes | Protected access | Open Customer, OM, Technician, and Sales pages while logged out. | Redirect to Login. | Protected pages redirected to Login. | PASS | Critical | Route middleware and view checks in place. | PASS |
| FINAL-003 | Customer, OM, Technician, Sales | Login | Valid login | Submit valid credentials for each role. | Each account reaches correct homepage. | Each role redirects correctly. | PASS | Critical | Password hash compatibility added. | PASS |
| FINAL-004 | Public | Login | Invalid login | Submit wrong, empty, repeated failed, and SQL-like credentials. | Login fails and no session is created. | Requests returned `401`; no session created. | PASS | Critical | Added regression tests. | PASS |
| FINAL-005 | Customer | Logout/session | Logout and back-button equivalent | Login, logout, then request protected page. | Protected content is unavailable after logout. | Session cleared; page redirects to Login; no-cache headers present. | PASS | High | Added no-store headers on protected routes. | PASS |
| FINAL-006 | Customer, OM, Technician, Sales | Role routes | URL manipulation | Manually request wrong-role home and module routes. | Redirect to correct role homepage or Login. | Wrong-role access is blocked before content renders. | PASS | Critical | Added `RoleAccessMiddleware`. | PASS |
| FINAL-007 | API-style request | Protected routes | API permission enforcement | Send JSON-style request while logged out and wrong-role. | Return `401` or `403`. | Returned `401`/`403` without restricted data. | PASS | High | Middleware handles JSON/API-style requests. | PASS |
| FINAL-008 | Customer | Navigation | Desktop/mobile role nav | Render Customer home and inspect role nav/drawer. | Customer sees Customer nav and Profile, not restricted nav. | Correct nav rendered; mobile Profile appears before drawer links. | PASS | Medium | Added final navigation tests. | PASS |
| FINAL-009 | OM | Navigation | Desktop/mobile role nav | Render OM home and inspect role nav/drawer. | OM sees OM modules only. | Correct OM nav rendered. | PASS | Medium | Added final navigation tests. | PASS |
| FINAL-010 | Technician | Navigation | Desktop/mobile role nav | Render Technician home and inspect role nav/drawer. | Technician sees Technician modules only. | Correct Technician nav rendered. | PASS | Medium | Added final navigation tests. | PASS |
| FINAL-011 | Sales | Navigation | Desktop/mobile role nav | Render Sales home and inspect role nav/drawer. | Sales sees Sales modules only. | Correct Sales nav rendered. | PASS | Medium | Added final navigation tests. | PASS |
| FINAL-012 | Public | Navigation | Public nav | Render public home while logged out. | Public sees Login/Sign Up and no Profile link. | Public nav rendered correctly. | PASS | Medium | Added final navigation tests. | PASS |
| FINAL-013 | Customer | Profile | View/edit/change password | Open profile, edit profile, and change password routes. | Pages render and require Customer session. | Routes returned `200` for Customer. | PASS | High | Existing checks plus middleware. | PASS |
| FINAL-014 | Customer | Properties | Create/read/update access | Register property and attempt another customer's property. | Own operations work; other records blocked. | Create succeeds; other-customer access redirects. | PASS | Critical | Ownership filters verified. | PASS |
| FINAL-015 | Customer | Inspection booking | Book inspection validation and create | Submit invalid and valid inspection booking payloads. | Invalid rejected; valid creates service. | Behaved as expected. | PASS | High | Existing validation verified. | PASS |
| FINAL-016 | Customer | Service Status | Status page and action visibility | Open Customer Service Status. | Status renders; no "Book an Inspection" message on status page. | Page returned `200`; text absent. | PASS | Medium | Added final route/content test. | PASS |
| FINAL-017 | Customer | Estimated Bill/Invoice | View allowed bill and invoice | Open bill and invoice for own service. | Own billing records render. | Routes returned `200`. | PASS | High | Ownership filters verified. | PASS |
| FINAL-018 | Customer | Proof of Payment | Submit proof | Submit missing fields, invalid spoofed file, and valid PDF signature. | Invalid rejected; valid proof accepted once. | Spoofed file rejected; valid proof saved. | PASS | Critical | Added file signature validation. | PASS |
| FINAL-019 | OM | Dashboard/Profile | OM home/profile | Open OM home, profile, change password. | Pages render for OM only. | Routes returned `200`. | PASS | High | Middleware verified. | PASS |
| FINAL-020 | OM | Service status/history | Status transition | Open status/history and update service status with required date/time. | Update validates and persists. | Status update persisted. | PASS | High | Existing workflow verified. | PASS |
| FINAL-021 | OM | Treatment booking | Book/edit/delete routes | Open OM service booking routes where allowed. | Routes are protected and data is scoped to OM permission. | OM route smoke tests passed. | PASS | High | Existing OM checks verified. | PASS |
| FINAL-022 | OM | Estimated Bill | Create/update/delete/view | Update existing bill option and view bill. | Existing records update without duplicate. | Bill view route passed; config update tests passed. | PASS | High | Existing behavior verified. | PASS |
| FINAL-023 | OM | Invoice | Create/update/delete/view | Open invoice list/view and invoice-item alias. | Invoice pages render; alias redirects intentionally. | Invoice pages returned `200`; alias redirects to service items. | PASS | High | Test adjusted to current route behavior. | PASS |
| FINAL-024 | OM | Service Reports | View reports | Open OM report list and report view. | Report screens render for OM. | Routes returned `200`. | PASS | High | Existing OM checks verified. | PASS |
| FINAL-025 | OM | Service Configurations | Update options | Update Treatment, Inspection, Service Report Submission, Payment Proof Submission, Chemicals, and Service Items. | Existing records are modified without duplicates. | Updates preserved record IDs and did not create duplicates. | PASS | High | Added expanded config tests. | PASS |
| FINAL-026 | OM | Account Management | Customer/Technician/Sales accounts | Open account screens and create staff accounts. | Screens render; staff passwords are hashed; no password display. | Screens rendered; passwords not displayed or stored as raw text. | PASS | Critical | Password display removed; hashing added. | PASS |
| FINAL-027 | Technician | Home/Profile | Technician pages | Open home/profile. | Pages render for Technician only. | Routes returned `200`. | PASS | High | Middleware verified. | PASS |
| FINAL-028 | Technician | Service Status | Update allowed statuses | Submit allowed and disallowed technician status transitions. | Invalid transition rejected; allowed transition persists. | Behaved as expected. | PASS | High | Existing transition rules verified. | PASS |
| FINAL-029 | Technician | Service Reports | View/edit/delete scope | Access own report and another/unallowed report. | Own report allowed; unallowed report blocked. | Own report rendered; other report redirected. | PASS | Critical | Added technician report ownership filter. | PASS |
| FINAL-030 | Sales | Home/Profile | Sales pages | Open home/profile. | Pages render for Sales only. | Routes returned `200`. | PASS | High | Middleware verified. | PASS |
| FINAL-031 | Sales | Proof of Payment | Review/validate/reject | Open proof review; validate and reject workflows. | Proof state updates once; duplicate final action blocked. | Validation/rejection tests passed. | PASS | Critical | Existing lock behavior verified. | PASS |
| FINAL-032 | Sales | Invoice/Remittance | Payment-related records | Open Sales invoice, payment proof, remittance list. | Sales payment-related screens render; wrong roles blocked. | Routes returned `200`; wrong-role tests pass. | PASS | High | Middleware verified. | PASS |
| FINAL-033 | Modals/buttons | UI protocol | Modal/button styling | Inspect base modal/button CSS and modal markup. | Text centered, delete red, cancel secondary, mobile modal constraints present. | Static contract checks passed. | PASS | Medium | Existing global CSS verified. | PASS |
| FINAL-034 | Back buttons | UI protocol | Back labels/routes | Scan templates for `<- Back` and arrow back labels. | Back labels say `Back`. | No old arrow labels found. | PASS | Low | Existing templates verified. | PASS |
| FINAL-035 | Status badges | UI protocol | Status colors/wrapping | Inspect global status CSS. | Shared status classes use consistent color and wrapping rules. | Static contract checks passed. | PASS | Medium | Existing global CSS verified. | PASS |
| FINAL-036 | Tables/responsive | UI protocol | Table overflow and mobile access | Inspect responsive table CSS and render major table routes. | Tables are wrapped/scrollable and pages render. | Static contract and route tests passed. | PASS | Medium | Existing responsive CSS verified. | PASS |
| FINAL-037 | Database | CRUD/relationships | Create/read/update/delete chain | Create customer, property, service, invoice, proof, remittance; update property; delete invoice. | Relations correct; update does not duplicate; delete only intended record. | Database relationship test passed. | PASS | High | Added final DB relationship test. | PASS |
| FINAL-038 | Security | Injection/XSS/file/session | SQL-like, XSS-like, invalid upload, unauthorized proof, logout/session. | No bypass, script execution, data leak, or invalid file acceptance. | Security tests passed. | PASS | Critical | Security fixes from rule 127 retained. | PASS |
| FINAL-039 | Production/backup readiness | Deployment config | Check production settings and local DB tracking. | Production settings are env-driven; local DB not deployed. | Settings are env-driven; `SANG/db.sqlite3` removed from git index, local file remains. | PASS | Critical | Removed tracked SQLite DB from index. | PASS |
| FINAL-040 | Desktop/tablet/mobile visual validation | Responsive layout | Real browser viewport screenshots | Run browser/device checks for desktop, tablet, and mobile portrait. | No overflow; nav drawer and modals fit viewport. | Not run: no Playwright/Selenium/Chromium available in this environment. Static responsive checks passed. | FAIL | Medium | Documented limitation; install browser runner or test on hosted site/device. | Pending |

## Final Summary

- Total final matrix cases: 40
- Automated test cases run: 40
- Automated passed: 40
- Automated failed: 0
- Critical issues found in final automated run: 0
- High issues found in final automated run: 0
- Medium issues: 1 pending live/browser visual validation item
- Low issues: 0
- Fixes applied during final rundown:
  - Added final route smoke tests.
  - Added role navigation tests.
  - Added UI/static consistency checks for modals, status badges, tables, back labels, and mobile drawer structure.
  - Added broader Service Configuration update checks.
  - Added database relationship CRUD check.
- Retest result: `python manage.py test sangapp` passed with `40 tests OK`.
- Build/lint/validation result: Django system check passed during the test run.
- Final readiness status: **Partially Passed**

## Acceptance Notes

No Critical or High issue remains unresolved in the automated backend, routing, permission, security, validation, and database test suite.

The system should not be marked fully `Passed` until `FINAL-040` is completed with real browser/device validation for desktop, tablet, and mobile portrait layouts, or until an equivalent browser automation runner is installed and the responsive visual checks pass.
