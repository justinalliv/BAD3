from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings
from django.test import Client, TestCase
from django.test.utils import override_settings
from django.urls import reverse

from sangapp.models import (
    Chemical,
    Customer,
    EstimatedBill,
    EstimatedBillItem,
    Invoice,
    InvoiceItem,
    InvoiceItemOption,
    OperationsManager,
    PaymentProof,
    Property,
    RemittanceRecord,
    SalesRepresentative,
    Service,
    ServiceFormOption,
    ServiceReport,
    Technician,
)


class LogicProtocolTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        cls._test_media_root = tempfile.mkdtemp()
        cls._media_override = override_settings(MEDIA_ROOT=cls._test_media_root)
        cls._media_override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._media_override.disable()
        shutil.rmtree(cls._test_media_root, ignore_errors=True)

    @classmethod
    def setUpTestData(cls):
        cls.om = OperationsManager.objects.create(
            first_name='Olivia',
            last_name='Manager',
            email='om@example.com',
            password='secret',
        )
        cls.technician = Technician.objects.create(
            technician_id='TECH-001',
            first_name='Terry',
            last_name='Tech',
            email='tech@example.com',
            password='secret',
        )
        cls.sales = SalesRepresentative.objects.create(
            first_name='Sam',
            last_name='Sales',
            email='sales@example.com',
            password='secret',
        )
        cls.customer = Customer.objects.create(
            first_name='Casey',
            last_name='Customer',
            email='customer@example.com',
            phone_number='09123456789',
            password='secret',
        )
        cls.other_customer = Customer.objects.create(
            first_name='Other',
            last_name='Customer',
            email='other@example.com',
            phone_number='09987654321',
            password='secret',
        )
        cls.property = Property.objects.create(
            customer=cls.customer,
            property_name='Main Home',
            street_number='123',
            street='Pest Street',
            city='Quezon City',
            province='Metro Manila',
            zip_code='1100',
            property_type='Residential',
            floor_area=Decimal('120.00'),
        )
        cls.other_property = Property.objects.create(
            customer=cls.other_customer,
            property_name='Other Home',
            street_number='321',
            street='Other Street',
            city='Makati',
            province='Metro Manila',
            zip_code='1200',
            property_type='Residential',
            floor_area=Decimal('90.00'),
        )
        cls.service = cls._create_service(cls.customer, cls.property, 'For Confirmation')
        cls.for_inspection_service = cls._create_service(cls.customer, cls.property, 'For Inspection')
        cls.for_treatment_service = cls._create_service(cls.customer, cls.property, 'For Treatment')
        cls.pending_payment_service = cls._create_service(cls.customer, cls.property, 'Pending Payment')
        cls.other_service = cls._create_service(cls.other_customer, cls.other_property, 'For Confirmation')
        cls.estimated_bill = EstimatedBill.objects.create(service=cls.service, operations_manager=cls.om)
        EstimatedBillItem.objects.create(
            estimated_bill=cls.estimated_bill,
            service_type='Termite Control',
            quantity=1,
            unit_price=Decimal('3000.00'),
        )
        cls.invoice = Invoice.objects.create(service=cls.pending_payment_service, operations_manager=cls.om)
        InvoiceItem.objects.create(
            invoice=cls.invoice,
            item_type='Termite Control',
            quantity=1,
            unit_price=Decimal('3000.00'),
        )
        cls.payment_type, _ = ServiceFormOption.objects.get_or_create(
            form_section='Payment Proof Submission',
            field_name='Payment Type',
            option_value='Bank Transfer',
        )
        cls.bank, _ = ServiceFormOption.objects.get_or_create(
            form_section='Payment Proof Submission',
            field_name='Bank Used for Payment',
            option_value='BPI',
            defaults={
                'option_description': 'Bank Transfer',
                'account_number': '1234567890',
            },
        )
        if not cls.bank.account_number:
            cls.bank.option_description = 'Bank Transfer'
            cls.bank.account_number = '1234567890'
            cls.bank.save(update_fields=['option_description', 'account_number'])
        cls.payment_proof = PaymentProof.objects.create(
            service=cls.pending_payment_service,
            invoice=cls.invoice,
            customer=cls.customer,
            payment_type='Bank Transfer',
            bank_used='BPI',
            account_number='1234567890',
            reference_number='REF-001',
            amount_paid=Decimal('3000.00'),
            proof_file=SimpleUploadedFile('proof.pdf', b'proof', content_type='application/pdf'),
        )
        cls.report = ServiceReport.objects.create(
            service=cls.for_treatment_service,
            technician=cls.technician,
        )
        cls.other_report = ServiceReport.objects.create(
            service=cls.other_service,
            technician=None,
        )

    @classmethod
    def _create_service(cls, customer, property_obj, status):
        return Service.objects.create(
            customer=customer,
            property=property_obj,
            preferred_service='Termite Control',
            pest_problem='Termites',
            date=date.today() + timedelta(days=3),
            time_slot='8:00 AM - 9:00 AM',
            status=status,
        )

    def login_as_customer(self, customer=None):
        customer = customer or self.customer
        session = self.client.session
        session['customer_id'] = customer.id
        session['customer_name'] = f'{customer.first_name} {customer.last_name}'
        session['customer_display_id'] = str(customer.id)
        session.save()

    def login_as_technician(self):
        session = self.client.session
        session['technician_id'] = self.technician.id
        session['technician_name'] = f'{self.technician.first_name} {self.technician.last_name}'
        session['technician_display_id'] = self.technician.technician_id
        session.save()

    def login_as_sales(self):
        session = self.client.session
        session['sales_representative_id'] = self.sales.id
        session['sales_representative_name'] = f'{self.sales.first_name} {self.sales.last_name}'
        session['sales_representative_display_id'] = str(self.sales.id)
        session.save()

    def login_as_om(self):
        session = self.client.session
        session['om_id'] = self.om.id
        session['om_name'] = f'{self.om.first_name} {self.om.last_name}'
        session['om_display_id'] = str(self.om.id)
        session.save()


class AuthenticationAndAuthorizationTests(LogicProtocolTestCase):
    def test_public_private_routes_redirect_to_login(self):
        private_routes = [
            reverse('profile'),
            reverse('property_list'),
            reverse('book_inspection'),
            reverse('service_status'),
            reverse('om_home'),
            reverse('technician_home'),
            reverse('sales_representative_home'),
        ]

        for url in private_routes:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.url, reverse('login'))

    def test_each_role_is_blocked_from_other_role_home_routes(self):
        role_sessions = [
            (self.login_as_customer, reverse('home'), [reverse('om_home'), reverse('technician_home'), reverse('sales_representative_home')]),
            (self.login_as_technician, reverse('technician_home'), [reverse('profile'), reverse('om_home'), reverse('sales_representative_home')]),
            (self.login_as_sales, reverse('sales_representative_home'), [reverse('profile'), reverse('om_home'), reverse('technician_home')]),
            (self.login_as_om, reverse('om_home'), [reverse('profile'), reverse('technician_home'), reverse('sales_representative_home')]),
        ]

        for login_helper, expected_redirect, blocked_urls in role_sessions:
            self.client.cookies.clear()
            login_helper()
            for url in blocked_urls:
                with self.subTest(login_helper=login_helper.__name__, url=url):
                    response = self.client.get(url)
                    self.assertEqual(response.status_code, 302)
                    self.assertEqual(response.url, expected_redirect)

    def test_direct_restricted_urls_are_blocked_for_every_role(self):
        attempts = [
            (self.login_as_customer, reverse('home'), [
                reverse('om_service_status'),
                reverse('technician_service_status'),
                reverse('sales_representative_payment_proofs'),
            ]),
            (self.login_as_technician, reverse('technician_home'), [
                reverse('property_list'),
                reverse('om_service_status'),
                reverse('sales_representative_payment_proofs'),
            ]),
            (self.login_as_sales, reverse('sales_representative_home'), [
                reverse('property_list'),
                reverse('technician_service_status'),
                reverse('om_service_status'),
            ]),
            (self.login_as_om, reverse('om_home'), [
                reverse('property_list'),
                reverse('technician_service_status'),
                reverse('sales_representative_payment_proofs'),
            ]),
        ]

        for login_helper, expected_redirect, urls in attempts:
            self.client.cookies.clear()
            login_helper()
            for url in urls:
                with self.subTest(role=login_helper.__name__, url=url):
                    response = self.client.get(url)
                    self.assertEqual(response.status_code, 302)
                    self.assertEqual(response.url, expected_redirect)

    def test_json_restricted_requests_return_401_or_403(self):
        unauthenticated_response = self.client.get(
            reverse('om_home'),
            HTTP_ACCEPT='application/json',
        )
        self.assertEqual(unauthenticated_response.status_code, 401)

        self.login_as_customer()
        forbidden_response = self.client.get(
            reverse('technician_home'),
            HTTP_ACCEPT='application/json',
        )
        self.assertEqual(forbidden_response.status_code, 403)

    def test_protected_pages_are_not_cached_after_logout(self):
        self.login_as_customer()

        response = self.client.get(reverse('profile'))

        self.assertEqual(response.status_code, 200)
        self.assertIn('no-store', response.headers['Cache-Control'])

        self.client.get(reverse('logout'))
        after_logout_response = self.client.get(reverse('profile'))
        self.assertRedirects(after_logout_response, reverse('login'))

    def test_invalid_session_redirects_to_login(self):
        session = self.client.session
        session['customer_id'] = 999999
        session.save()

        response = self.client.get(reverse('profile'))

        self.assertRedirects(response, reverse('login'))
        self.assertNotIn('customer_id', self.client.session)

    def test_valid_login_redirects_to_correct_role_home(self):
        credentials = [
            ('om@example.com', 'secret', reverse('om_home'), 'om_id'),
            ('tech@example.com', 'secret', reverse('technician_home'), 'technician_id'),
            ('sales@example.com', 'secret', reverse('sales_representative_home'), 'sales_representative_id'),
            ('customer@example.com', 'secret', reverse('home'), 'customer_id'),
        ]

        for email, password, expected_url, session_key in credentials:
            with self.subTest(email=email):
                self.client.cookies.clear()
                response = self.client.post(reverse('login'), {'email': email, 'password': password})
            self.assertRedirects(response, expected_url)
            self.assertIn(session_key, self.client.session)

    def test_payment_proof_file_access_for_authorized_roles_only(self):
        proof_url = reverse('payment_proof_file', args=[self.payment_proof.id])

        for login_helper in (self.login_as_sales, self.login_as_om, self.login_as_customer):
            with self.subTest(role=login_helper.__name__):
                self.client.cookies.clear()
                login_helper()
                response = self.client.get(proof_url)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(b''.join(response.streaming_content), b'proof')

        self.client.cookies.clear()
        self.login_as_customer(self.other_customer)
        response = self.client.get(proof_url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('login'))

    def test_invalid_login_rejects_without_session(self):
        response = self.client.post(reverse('login'), {'email': 'customer@example.com', 'password': 'wrong'})

        self.assertEqual(response.status_code, 401)
        self.assertContains(response, 'Invalid email or password.', status_code=401)
        self.assertNotIn('customer_id', self.client.session)

    def test_empty_and_repeated_failed_login_attempts_do_not_create_session(self):
        payloads = [
            {'email': '', 'password': ''},
            {'email': 'customer@example.com', 'password': 'wrong'},
            {'email': 'customer@example.com', 'password': 'wrong-again'},
        ]

        for payload in payloads:
            with self.subTest(payload=payload):
                response = self.client.post(reverse('login'), payload)
                self.assertEqual(response.status_code, 401)
                self.assertNotIn('customer_id', self.client.session)

    def test_sql_injection_like_login_input_does_not_bypass_authentication(self):
        response = self.client.post(reverse('login'), {
            'email': "' OR '1'='1",
            'password': "' OR '1'='1",
        })

        self.assertEqual(response.status_code, 401)
        self.assertNotIn('customer_id', self.client.session)

    def test_password_hash_is_upgraded_after_legacy_login(self):
        self.assertEqual(self.customer.password, 'secret')

        response = self.client.post(reverse('login'), {
            'email': 'customer@example.com',
            'password': 'secret',
        })

        self.assertRedirects(response, reverse('home'))
        self.customer.refresh_from_db()
        self.assertNotEqual(self.customer.password, 'secret')
        self.assertTrue(self.customer.password.startswith(('pbkdf2_', 'argon2', 'bcrypt')))

    def test_logout_flushes_session(self):
        self.login_as_customer()

        response = self.client.get(reverse('logout'))

        self.assertRedirects(response, reverse('home'))
        self.assertNotIn('customer_id', self.client.session)

    def test_csrf_protects_state_changing_customer_post(self):
        csrf_client = Client(enforce_csrf_checks=True)
        session = csrf_client.session
        session['customer_id'] = self.customer.id
        session['customer_name'] = f'{self.customer.first_name} {self.customer.last_name}'
        session['customer_display_id'] = str(self.customer.id)
        session.save()

        response = csrf_client.post(reverse('register_property'), {
            'property_name': 'No CSRF',
            'street_number': '1',
            'street': 'Token Street',
            'city': 'Quezon City',
            'province': 'Metro Manila',
            'zip_code': '1100',
            'property_type': 'Residential',
            'floor_area': '10',
        })

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Property.objects.filter(property_name='No CSRF').exists())

    def test_customer_signup_creates_account_and_blocks_duplicates(self):
        signup_payload = {
            'first_name': 'New',
            'last_name': 'Customer',
            'email': 'new@example.com',
            'phone_number': '09111111111',
            'password': 'secret123',
            'confirm_password': 'secret123',
        }

        response = self.client.post(reverse('signup'), signup_payload)

        self.assertRedirects(response, reverse('login'))
        self.assertTrue(Customer.objects.filter(email='new@example.com').exists())
        self.assertNotEqual(Customer.objects.get(email='new@example.com').password, 'secret123')

        duplicate_response = self.client.post(reverse('signup'), signup_payload)
        self.assertEqual(duplicate_response.status_code, 200)
        self.assertContains(duplicate_response, 'Email already registered')


class CustomerFlowAndValidationTests(LogicProtocolTestCase):
    def test_customer_can_register_property_with_valid_data(self):
        self.login_as_customer()

        response = self.client.post(reverse('register_property'), {
            'property_name': 'Warehouse',
            'street_number': '88',
            'street': 'Storage Avenue',
            'city': 'Pasig',
            'province': 'Metro Manila',
            'zip_code': '1600',
            'property_type': 'Commercial',
            'floor_area': '300.50',
        })

        self.assertRedirects(response, reverse('property_list'))
        self.assertTrue(Property.objects.filter(customer=self.customer, property_name='Warehouse').exists())

    def test_register_property_rejects_missing_and_invalid_fields(self):
        self.login_as_customer()

        response = self.client.post(reverse('register_property'), {
            'property_name': '',
            'street_number': '',
            'street': '',
            'city': '',
            'province': '',
            'zip_code': '',
            'property_type': '',
            'floor_area': '-1',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Property name is required')
        self.assertContains(response, 'Floor area must be a positive number')

    def test_customer_cannot_edit_or_view_other_customer_records(self):
        self.login_as_customer()

        edit_response = self.client.get(reverse('edit_property', args=[self.other_property.id]))
        booking_response = self.client.get(reverse('customer_view_booking', args=[self.other_service.id]))
        invoice_response = self.client.get(reverse('customer_view_invoice', args=[self.pending_payment_service.id + 9999]))
        proof_response = self.client.get(reverse('payment_proof_file', args=[self.payment_proof.id]))

        self.assertRedirects(edit_response, reverse('property_list'))
        self.assertRedirects(booking_response, reverse('service_status'))
        self.assertEqual(invoice_response.status_code, 302)
        self.assertEqual(invoice_response.url, reverse('pending_payment'))
        self.assertEqual(proof_response.status_code, 200)

        self.client.session.flush()
        self.login_as_customer(self.other_customer)
        other_customer_proof_response = self.client.get(reverse('payment_proof_file', args=[self.payment_proof.id]))
        self.assertRedirects(other_customer_proof_response, reverse('login'))

    def test_book_inspection_rejects_invalid_post_without_creating_service(self):
        self.login_as_customer()
        service_count = Service.objects.count()

        response = self.client.post(reverse('book_inspection'), {
            'property_id': '',
            'preferred_service': '',
            'pest_problem': '',
            'date': '',
            'time_slot': '',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Property address is required')
        self.assertEqual(Service.objects.count(), service_count)

    def test_book_inspection_creates_service_with_default_status(self):
        self.login_as_customer()

        response = self.client.post(reverse('book_inspection'), {
            'property_id': str(self.property.id),
            'preferred_service': 'Termite Control',
            'pest_problem': 'Termites',
            'date': (date.today() + timedelta(days=5)).isoformat(),
            'time_slot': '8:00 AM - 9:00 AM',
        })

        self.assertRedirects(response, reverse('service_status'))
        self.assertTrue(Service.objects.filter(customer=self.customer, property=self.property, status='For Confirmation').exists())

    def test_payment_proof_submission_requires_valid_own_service_and_fields(self):
        self.login_as_customer()

        response = self.client.post(reverse('submit_payment_proof'), {
            'service_id': str(self.other_service.id),
            'payment_type': '',
            'bank_used': '',
            'reference_number': '',
            'amount_paid': '',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Payment type is required')
        self.assertFalse(PaymentProof.objects.filter(service=self.other_service, customer=self.customer).exists())

    def test_file_upload_accepts_only_valid_payment_proof_file_types(self):
        self.login_as_customer()
        service = self._create_service(self.customer, self.property, 'Pending Payment')
        invoice = Invoice.objects.create(service=service, operations_manager=self.om)

        invalid_response = self.client.post(reverse('submit_payment_proof'), {
            'service_id': str(service.id),
            'payment_type': 'Bank Transfer',
            'bank_used': 'BPI',
            'reference_number': 'REF-BAD',
            'amount_paid': '3000.00',
            'proof_file': SimpleUploadedFile('proof.pdf', b'<script>alert("xss")</script>', content_type='application/pdf'),
        })

        self.assertEqual(invalid_response.status_code, 200)
        self.assertContains(invalid_response, 'File format not allowed')
        self.assertFalse(PaymentProof.objects.filter(service=service).exists())

        valid_response = self.client.post(reverse('submit_payment_proof'), {
            'service_id': str(service.id),
            'payment_type': 'Bank Transfer',
            'bank_used': 'BPI',
            'reference_number': 'REF-GOOD',
            'amount_paid': '3000.00',
            'proof_file': SimpleUploadedFile('proof.pdf', b'%PDF-1.4\n%test', content_type='application/pdf'),
        })

        self.assertRedirects(valid_response, reverse('service_status'))
        self.assertTrue(PaymentProof.objects.filter(service=service, invoice=invoice).exists())

    def test_xss_payload_is_escaped_when_rendered(self):
        self.login_as_customer()
        payload = '<script>alert("xss")</script>'
        Property.objects.create(
            customer=self.customer,
            property_name=payload,
            street_number='1',
            street='Safe Street',
            city='Quezon City',
            province='Metro Manila',
            zip_code='1100',
            property_type='Residential',
            floor_area=Decimal('10.00'),
        )

        response = self.client.get(reverse('property_list'))
        body = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(payload, body)
        self.assertIn('&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;', body)

    def test_sql_like_search_and_malformed_id_do_not_expose_or_crash(self):
        self.login_as_customer()

        search_response = self.client.get(reverse('property_list'), {'q': "' OR '1'='1"})
        malformed_id_response = self.client.get("/properties/' OR '1'='1/edit/")

        self.assertEqual(search_response.status_code, 200)
        self.assertEqual(malformed_id_response.status_code, 404)


class StatusPaymentAndDatabaseTests(LogicProtocolTestCase):
    def test_om_status_transition_requires_date_and_time_then_persists(self):
        self.login_as_om()

        missing_response = self.client.post(reverse('om_update_service_status', args=[self.service.id]), {
            'new_status': 'For Inspection',
        })
        self.assertEqual(missing_response.status_code, 200)
        self.assertContains(missing_response, 'Required fields must be filled in.')

        response = self.client.post(reverse('om_update_service_status', args=[self.service.id]), {
            'new_status': 'For Inspection',
            'inspection_confirmed_date': (date.today() + timedelta(days=1)).isoformat(),
            'inspection_confirmed_time': '8:00 AM - 9:00 AM',
        })

        self.assertRedirects(response, reverse('om_service_status'))
        self.service.refresh_from_db()
        self.assertEqual(self.service.status, 'For Inspection')
        self.assertEqual(self.service.inspection_confirmed_time, '8:00 AM - 9:00 AM')

    def test_technician_can_only_apply_allowed_status_transitions(self):
        self.login_as_technician()

        invalid_response = self.client.post(reverse('technician_update_service_status', args=[self.service.id]), {
            'new_status': 'Completed',
        })
        self.assertEqual(invalid_response.status_code, 200)
        self.assertContains(invalid_response, 'Invalid status transition for current service status.')

        valid_response = self.client.post(reverse('technician_update_service_status', args=[self.for_inspection_service.id]), {
            'new_status': 'Ongoing Inspection',
        })

        self.assertRedirects(valid_response, reverse('technician_service_status'))
        self.for_inspection_service.refresh_from_db()
        self.assertEqual(self.for_inspection_service.status, 'Ongoing Inspection')

    def test_technician_cannot_access_completed_services_or_other_reports_by_id(self):
        self.login_as_technician()
        self.other_service.status = 'Completed'
        self.other_service.save(update_fields=['status'])

        booking_response = self.client.get(reverse('technician_view_booking', args=[self.other_service.id]))
        report_response = self.client.get(reverse('technician_view_service_report', args=[self.other_report.id]))

        self.assertRedirects(booking_response, reverse('technician_service_status'))
        self.assertRedirects(report_response, reverse('technician_service_reports'))

    def test_sales_validation_updates_payment_proof_service_and_remittance_once(self):
        self.login_as_sales()

        response = self.client.post(reverse('sales_representative_review_payment_proof', args=[self.payment_proof.id]), {
            'action': 'validate',
        })

        self.assertRedirects(response, reverse('sales_representative_payment_proofs'))
        self.payment_proof.refresh_from_db()
        self.pending_payment_service.refresh_from_db()
        self.assertEqual(self.payment_proof.status, PaymentProof.STATUS_VALIDATED)
        self.assertEqual(self.pending_payment_service.status, 'Payment Confirmed')
        self.assertEqual(RemittanceRecord.objects.filter(payment_proof=self.payment_proof).count(), 1)

        second_response = self.client.post(reverse('sales_representative_review_payment_proof', args=[self.payment_proof.id]), {
            'action': 'validate',
        })

        self.assertEqual(second_response.status_code, 200)
        self.assertContains(second_response, 'Validation status is final and can no longer be changed.')
        self.assertEqual(RemittanceRecord.objects.filter(payment_proof=self.payment_proof).count(), 1)

    def test_sales_rejection_requires_reason_and_preserves_state_when_missing(self):
        self.login_as_sales()

        response = self.client.post(reverse('sales_representative_review_payment_proof', args=[self.payment_proof.id]), {
            'action': 'reject',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Rejection reason is required.')
        self.payment_proof.refresh_from_db()
        self.pending_payment_service.refresh_from_db()
        self.assertEqual(self.payment_proof.status, PaymentProof.STATUS_FOR_VALIDATION)
        self.assertEqual(self.pending_payment_service.status, 'Pending Payment')

    def test_sales_invoice_view_matches_invoice_rows_and_total(self):
        self.login_as_sales()

        response = self.client.get(reverse('sales_representative_view_invoice', args=[self.invoice.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Service Items')
        self.assertContains(response, 'Termite Control')
        self.assertContains(response, 'Total Amount: ₱ 3000.00')

    def test_om_account_edit_pages_do_not_display_password_values(self):
        self.login_as_om()

        technician_response = self.client.get(reverse('om_edit_technician_account', args=[self.technician.id]))
        sales_response = self.client.get(reverse('om_edit_sales_representative_account', args=[self.sales.id]))

        self.assertEqual(technician_response.status_code, 200)
        self.assertEqual(sales_response.status_code, 200)
        self.assertNotContains(technician_response, 'Current Password')
        self.assertNotContains(technician_response, self.technician.password)
        self.assertNotContains(sales_response, 'Current Password')
        self.assertNotContains(sales_response, self.sales.password)

    def test_om_created_staff_passwords_are_hashed(self):
        self.login_as_om()

        tech_response = self.client.post(reverse('om_manage_technician_accounts'), {
            'action': 'create_technician',
            'first_name': 'New',
            'last_name': 'Tech',
            'password': 'staffpass123',
        })
        sales_response = self.client.post(reverse('om_manage_sales_accounts'), {
            'action': 'create_sales_representative',
            'first_name': 'New',
            'last_name': 'Sales',
            'password': 'staffpass123',
        })

        self.assertRedirects(tech_response, reverse('om_manage_technician_accounts'))
        self.assertRedirects(sales_response, reverse('om_manage_sales_accounts'))
        self.assertNotEqual(Technician.objects.get(email='tech2@companyemail.com').password, 'staffpass123')
        self.assertNotEqual(SalesRepresentative.objects.get(first_name='New', last_name='Sales').password, 'staffpass123')


class ServiceConfigurationUpdateTests(LogicProtocolTestCase):
    def test_service_form_update_keeps_existing_id_and_does_not_recreate_default(self):
        self.login_as_om()

        treatment, _ = ServiceFormOption.objects.update_or_create(
            form_section='Treatment',
            field_name='Treatment Service',
            option_value='Bed Bug Treatment',
            defaults={
                'scoped_option_id': 6,
                'option_description': 'Old description',
                'option_rate': Decimal('2800.00'),
                'is_active': True,
            },
        )

        response = self.client.post(reverse('om_service_forms') + '?section=Treatment', {
            'action': 'update',
            'option_id': str(treatment.id),
            'form_section': 'Treatment',
            'field_name': 'Treatment Service',
            'option_value': 'Bed Bug Treatments',
            'option_description': 'Updated description',
            'option_rate': '2800.00',
            'is_active': 'on',
        })

        self.assertRedirects(response, reverse('om_service_forms') + '?section=Treatment')
        treatment.refresh_from_db()
        self.assertEqual(treatment.option_value, 'Bed Bug Treatments')
        self.assertFalse(ServiceFormOption.objects.filter(
            form_section='Treatment',
            field_name='Treatment Service',
            option_value='Bed Bug Treatment',
        ).exclude(id=treatment.id).exists())

    def test_chemical_update_keeps_existing_id(self):
        self.login_as_om()
        chemical = Chemical.objects.create(name='Old Chemical', standard_unit_measure='mL', is_active=True)

        response = self.client.post(reverse('om_chemicals'), {
            'action': 'update',
            'chemical_id': str(chemical.id),
            'name': 'Updated Chemical',
            'standard_unit_measure': 'L',
            'is_active': 'on',
        })

        self.assertRedirects(response, reverse('om_chemicals'))
        chemical.refresh_from_db()
        self.assertEqual(chemical.name, 'Updated Chemical')
        self.assertEqual(Chemical.objects.filter(id=chemical.id).count(), 1)

    def test_service_item_update_keeps_existing_id(self):
        self.login_as_om()
        service_item = InvoiceItemOption.objects.create(
            name='Old Service Item',
            default_unit_price=Decimal('1500.00'),
            is_active=True,
        )

        response = self.client.post(reverse('om_service_items'), {
            'action': 'update',
            'item_id': str(service_item.id),
            'name': 'Updated Service Item',
            'default_unit_price': '1750.00',
            'is_active': 'on',
        })

        self.assertRedirects(response, reverse('om_service_items'))
        service_item.refresh_from_db()
        self.assertEqual(service_item.name, 'Updated Service Item')
        self.assertEqual(service_item.default_unit_price, Decimal('1750.00'))
        self.assertEqual(InvoiceItemOption.objects.filter(id=service_item.id).count(), 1)

    def test_service_form_updates_all_required_sections_without_duplicates(self):
        self.login_as_om()
        cases = [
            ('Inspection', 'Type of Property', 'Residential', 'Residential Updated'),
            ('Service Report Submission', 'Levels of Infestation', 'Low', 'Low Updated'),
            ('Payment Proof Submission', 'Payment Type', 'Bank Transfer', 'Bank Transfer Updated'),
        ]

        for form_section, field_name, original_value, updated_value in cases:
            with self.subTest(form_section=form_section, field_name=field_name):
                option, _ = ServiceFormOption.objects.update_or_create(
                    form_section=form_section,
                    field_name=field_name,
                    option_value=original_value,
                    defaults={'is_active': True},
                )

                response = self.client.post(reverse('om_service_forms') + f'?section={form_section}', {
                    'action': 'update',
                    'option_id': str(option.id),
                    'form_section': form_section,
                    'field_name': field_name,
                    'option_value': updated_value,
                    'option_description': 'Updated',
                    'option_rate': '',
                    'is_active': 'on',
                })

                self.assertEqual(response.status_code, 302)
                self.assertIn('section=', response.url)
                self.assertIn('field_filter=', response.url)
                option.refresh_from_db()
                self.assertEqual(option.option_value, updated_value)
                self.assertFalse(ServiceFormOption.objects.filter(
                    form_section=form_section,
                    field_name=field_name,
                    option_value=original_value,
                ).exclude(id=option.id).exists())


class FinalEndToEndRundownTests(LogicProtocolTestCase):
    def assert_page_ok(self, url):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200, msg=f'{url} returned {response.status_code}')
        return response

    def test_public_and_role_major_routes_render(self):
        for url in [reverse('home'), reverse('login'), reverse('signup')]:
            with self.subTest(role='public', url=url):
                self.assert_page_ok(url)

        self.client.cookies.clear()
        self.login_as_customer()
        for url in [
            reverse('home'),
            reverse('profile'),
            reverse('edit_profile'),
            reverse('change_password'),
            reverse('property_list'),
            reverse('register_property'),
            reverse('book_inspection'),
            reverse('service_status'),
            reverse('customer_view_booking', args=[self.service.id]),
            reverse('customer_view_estimated_bill', args=[self.service.id]),
            reverse('customer_view_invoice', args=[self.pending_payment_service.id]),
        ]:
            with self.subTest(role='customer', url=url):
                self.assert_page_ok(url)

        service_status_response = self.client.get(reverse('service_status'))
        self.assertNotContains(service_status_response, 'Book an Inspection')

        self.client.cookies.clear()
        self.login_as_om()
        for url in [
            reverse('om_home'),
            reverse('om_profile'),
            reverse('om_change_password'),
            reverse('om_service_history'),
            reverse('om_service_status'),
            reverse('om_billing'),
            reverse('om_estimated_bills'),
            reverse('om_view_estimated_bill', args=[self.estimated_bill.id]),
            reverse('om_invoices'),
            reverse('om_view_invoice', args=[self.invoice.id]),
            reverse('om_service_reports'),
            reverse('om_view_service_report', args=[self.report.id]),
            reverse('om_remittance_records'),
            reverse('om_manage_service_forms'),
            reverse('om_service_forms'),
            reverse('om_chemicals'),
            reverse('om_service_items'),
            reverse('om_manage_accounts'),
            reverse('om_manage_technician_accounts'),
            reverse('om_manage_sales_accounts'),
            reverse('om_manage_customer_accounts'),
        ]:
            with self.subTest(role='om', url=url):
                self.assert_page_ok(url)

        invoice_items_response = self.client.get(reverse('om_invoice_items'))
        self.assertRedirects(invoice_items_response, reverse('om_service_items'))

        self.client.cookies.clear()
        self.login_as_technician()
        for url in [
            reverse('technician_home'),
            reverse('technician_profile'),
            reverse('technician_service_status'),
            reverse('technician_service_history'),
            reverse('technician_service_reports'),
            reverse('technician_view_service_report', args=[self.report.id]),
            reverse('technician_view_booking', args=[self.for_treatment_service.id]),
        ]:
            with self.subTest(role='technician', url=url):
                self.assert_page_ok(url)

        self.client.cookies.clear()
        self.login_as_sales()
        for url in [
            reverse('sales_representative_home'),
            reverse('sales_representative_profile'),
            reverse('sales_representative_service_history'),
            reverse('sales_representative_service_status'),
            reverse('sales_representative_payment_proofs'),
            reverse('sales_representative_review_payment_proof', args=[self.payment_proof.id]),
            reverse('sales_representative_remittance_records'),
            reverse('sales_representative_view_invoice', args=[self.invoice.id]),
        ]:
            with self.subTest(role='sales', url=url):
                self.assert_page_ok(url)

    def test_navigation_is_role_correct_on_desktop_and_mobile_markup(self):
        expectations = [
            (self.login_as_customer, reverse('home'), ['Manage Properties', 'Service Status', 'Profile'], ['Manage Accounts', 'Proof of Payment']),
            (self.login_as_om, reverse('om_home'), ['Service Configurations', 'Manage Accounts', 'Profile'], ['Book Inspection', 'Proof of Payment']),
            (self.login_as_technician, reverse('technician_home'), ['Service Reports', 'Profile'], ['Manage Accounts', 'Proof of Payment']),
            (self.login_as_sales, reverse('sales_representative_home'), ['Proof of Payment', 'Profile'], ['Manage Accounts', 'Book Inspection']),
        ]

        for login_helper, url, included, excluded in expectations:
            with self.subTest(role=login_helper.__name__):
                self.client.cookies.clear()
                login_helper()
                response = self.assert_page_ok(url)
                body = response.content.decode()

                for label in included:
                    self.assertIn(label, body)
                for label in excluded:
                    self.assertNotIn(label, body)

                drawer_content_index = body.index('<div class="mobile-drawer-content">')
                profile_index = body.index('mobile-drawer-account-title">Profile', drawer_content_index)
                links_index = body.index('mobile-drawer-links', drawer_content_index)
                self.assertLess(profile_index, links_index)

        self.client.cookies.clear()
        public_response = self.assert_page_ok(reverse('home'))
        public_body = public_response.content.decode()
        self.assertIn('Login', public_body)
        self.assertIn('Sign Up', public_body)
        self.assertNotIn('mobile-drawer-account-title">Profile', public_body)

    def test_final_ui_contracts_for_modals_tables_statuses_and_back_buttons(self):
        template_dir = Path(settings.BASE_DIR) / 'sangapp' / 'templates'
        template_text = '\n'.join(path.read_text() for path in template_dir.glob('*.html'))
        base_text = (template_dir / 'base.html').read_text()
        service_forms_text = (template_dir / 'om_service_forms.html').read_text()
        chemicals_text = (template_dir / 'om_chemicals.html').read_text()
        service_items_text = (template_dir / 'om_invoice_items.html').read_text()

        self.assertNotIn('<- Back', template_text)
        self.assertNotIn('← Back', template_text)
        self.assertIn('justify-content: center', base_text)
        self.assertIn('.modal-btn-danger', base_text)
        self.assertIn('#d9534f', base_text)
        self.assertIn('.modal-btn-cancel', base_text)
        self.assertIn('overflow-x: auto', base_text)
        self.assertIn('.mobile-nav-drawer', base_text)
        self.assertIn('status-for-confirmation', base_text)
        self.assertIn('white-space: normal', base_text)
        self.assertNotIn('Service Done', service_forms_text)
        self.assertIn('Manage chemicals in Chemicals page', service_forms_text)
        self.assertNotIn('<th>#</th>', chemicals_text)
        self.assertNotIn('<th>#</th>', service_items_text)

    def test_final_database_relationships_and_crud_behavior(self):
        customer = Customer.objects.create(
            first_name='Final',
            last_name='Customer',
            email='final@example.com',
            phone_number='09111112222',
            password='secret123',
        )
        property_obj = Property.objects.create(
            customer=customer,
            property_name='Final Property',
            street_number='10',
            street='Final Street',
            city='Quezon City',
            province='Metro Manila',
            zip_code='1100',
            property_type='Residential',
            floor_area=Decimal('50.00'),
        )
        service = self._create_service(customer, property_obj, 'Pending Payment')
        invoice = Invoice.objects.create(service=service, operations_manager=self.om)
        InvoiceItem.objects.create(
            invoice=invoice,
            item_type='Termite Control',
            quantity=1,
            unit_price=Decimal('3000.00'),
        )
        proof = PaymentProof.objects.create(
            service=service,
            invoice=invoice,
            customer=customer,
            payment_type='Bank Transfer',
            bank_used='BPI',
            account_number='1234567890',
            reference_number='FINAL-REF',
            amount_paid=Decimal('3000.00'),
            proof_file=SimpleUploadedFile('final.pdf', b'%PDF-1.4\nfinal', content_type='application/pdf'),
        )
        remittance, created = RemittanceRecord.objects.get_or_create(
            payment_proof=proof,
            defaults={'service': service, 'invoice': invoice, 'confirmed_by': self.sales},
        )

        self.assertTrue(created)
        self.assertEqual(service.customer, customer)
        self.assertEqual(service.property, property_obj)
        self.assertEqual(invoice.service, service)
        self.assertEqual(proof.customer, customer)
        self.assertEqual(remittance.invoice, invoice)

        property_obj.property_name = 'Final Property Updated'
        property_obj.save(update_fields=['property_name'])
        self.assertEqual(Property.objects.filter(customer=customer).count(), 1)

        invoice.delete()
        service.refresh_from_db()
        self.assertFalse(Invoice.objects.filter(id=invoice.id).exists())
        self.assertTrue(Service.objects.filter(id=service.id).exists())
