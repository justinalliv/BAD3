# Design Protocol Audit

## Mobile Navigation Drawer

- Screen name: Base navigation
- Account type: Customer, Technician, Sales Representative, Operations Manager
- Route/page: `base.html`
- Current issue: Mobile account item used only role labels, so Profile was not explicit.
- Design Protocol rule violated: Mobile Profile navigation item rule.
- Desktop impact: None.
- Mobile impact: Profile is now explicit and role identity remains visible.
- Fix applied: Added `Profile` as the account-section title with role label beneath it.
- Business logic changed: No
- Routes changed: No
- APIs changed: No
- Database behavior changed: No
- Validation behavior changed: No
- Desktop baseline preserved: Yes
- Mobile optimized: Yes
- Final status: Pass

## Typography System

- Screen name: Shared typography
- Account type: Public, Customer, Technician, Sales Representative, Operations Manager
- Route/page: Global base template
- Current issue: Equivalent UI elements could inherit inconsistent screen-level font sizing and weights.
- Design Protocol rule violated: Universal typography consistency rule.
- Desktop impact: Shared typography tokens normalize equivalent UI elements.
- Mobile impact: Mobile breakpoint uses readable adjusted title/action/input scale.
- Fix applied: Added shared typography variables and common typography selectors for titles, labels, controls, tables, navigation, buttons, statuses, and modals.
- Business logic changed: No
- Routes changed: No
- APIs changed: No
- Database behavior changed: No
- Validation behavior changed: No
- Desktop baseline preserved: Yes
- Mobile optimized: Yes
- Final status: Pass

## Service Configuration Update Modals

- Screen name: Chemicals, Service Items, Field Options update flows
- Account type: Operations Manager
- Route/page: `om_chemicals`, `om_invoice_items`, `om_service_forms`
- Current issue: Update modals used “Edit”/“Save” labels and placeholder-only inputs in some flows.
- Design Protocol rule violated: Service Configuration Update screen design rule.
- Desktop impact: Modals now follow a contained update form-shell without changing table layout.
- Mobile impact: Update modal forms stack cleanly with full-width controls and buttons.
- Fix applied: Added shared service configuration update modal class, visible labels, Update titles, and Update action labels.
- Business logic changed: No
- Routes changed: No
- APIs changed: No
- Database behavior changed: No
- Validation behavior changed: No
- Desktop baseline preserved: Yes
- Mobile optimized: Yes
- Final status: Pass

## Mobile Profile Priority

- Screen name: Mobile navigation drawer
- Account type: Customer, Technician, Sales Representative, Operations Manager
- Route/page: `base.html`
- Current issue: Profile appeared after role navigation items.
- Design Protocol rule violated: Mobile Profile navigation priority rule.
- Desktop impact: None.
- Mobile impact: Profile is now the first drawer item for logged-in users.
- Fix applied: Moved logged-in Profile account section directly below the drawer header and kept Public without a Profile link.
- Business logic changed: No
- Routes changed: No
- APIs changed: No
- Database behavior changed: No
- Validation behavior changed: No
- Desktop baseline preserved: Yes
- Mobile optimized: Yes
- Final status: Pass

## Update Service Status Screens

- Screen name: Update Service Status
- Account type: Technician, Operations Manager
- Route/page: `technician_update_service_status`, `om_update_service_status`
- Current issue: Mobile layout wasted space and Technician update lacked top Back placement.
- Design Protocol rule violated: Update Service Status mobile UI spacing and Back button rules.
- Desktop impact: Existing centered form pattern remains intact with a clearer form shell.
- Mobile impact: Full-width mobile sheet, single-column controls, top Back, stacked buttons, and consistent modal copy.
- Fix applied: Added top Back for Technician, form shell for OM, mobile spacing overrides, full-width action areas, and Update terminology.
- Business logic changed: No
- Routes changed: No
- APIs changed: No
- Database behavior changed: No
- Validation behavior changed: No
- Desktop baseline preserved: Yes
- Mobile optimized: Yes
- Final status: Pass

## Sign-Up Authentication Background

- Screen name: Sign Up
- Account type: Public
- Route/page: `signup`
- Current issue: Full-card blue background coverage needed to match Login.
- Design Protocol rule violated: Sign-up page height and background consistency rule.
- Desktop impact: Login-matched full-page gradient remains behind the card.
- Mobile impact: Tall sign-up form scrolls naturally while the blue background continues behind the full card.
- Fix applied: Added full-height body/main gradient coverage and reset container margin inside the auth layout.
- Business logic changed: No
- Routes changed: No
- APIs changed: No
- Database behavior changed: No
- Validation behavior changed: No
- Desktop baseline preserved: Yes
- Mobile optimized: Yes
- Final status: Pass

## Mobile Table Access And Action Buttons

- Screen name: Data-dense tables and table action controls
- Account type: Public, Customer, Technician, Sales Representative, Operations Manager
- Route/page: Shared table wrappers in `base.html`
- Current issue: Some mobile portrait table wrappers could clip right-side columns/actions if local table styles used hidden overflow or fixed widths.
- Design Protocol rule violated: Mobile portrait horizontal table movement rule; Service Configuration mobile table access rule; Delete and Cancel button design rule.
- Desktop impact: None; changes are mobile breakpoint scoped for table scrolling and semantic action styling is aligned globally.
- Mobile impact: Wide tables now scroll horizontally inside their container with a subtle swipe cue, while page-level horizontal overflow is prevented.
- Fix applied: Added mobile-only horizontal overflow standards for table wrappers and standardized Delete red / Cancel secondary button styling.
- Business logic changed: No
- Routes changed: No
- APIs changed: No
- Database behavior changed: No
- Validation behavior changed: No
- Desktop baseline preserved: Yes
- Mobile optimized: Yes
- Final status: Pass
