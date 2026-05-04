from datetime import date, timedelta
from decimal import Decimal
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
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
            (self.login_as_customer, [reverse('om_home'), reverse('technician_home'), reverse('sales_representative_home')]),
            (self.login_as_technician, [reverse('profile'), reverse('om_home'), reverse('sales_representative_home')]),
            (self.login_as_sales, [reverse('profile'), reverse('om_home'), reverse('technician_home')]),
            (self.login_as_om, [reverse('profile'), reverse('technician_home'), reverse('sales_representative_home')]),
        ]

        for login_helper, blocked_urls in role_sessions:
            self.client.session.flush()
            login_helper()
            for url in blocked_urls:
                with self.subTest(login_helper=login_helper.__name__, url=url):
                    response = self.client.get(url)
                    self.assertEqual(response.status_code, 302)
                    self.assertEqual(response.url, reverse('login'))

    def test_valid_login_redirects_to_correct_role_home(self):
        credentials = [
            ('om@example.com', 'secret', reverse('om_home'), 'om_id'),
            ('tech@example.com', 'secret', reverse('technician_home'), 'technician_id'),
            ('sales@example.com', 'secret', reverse('sales_representative_home'), 'sales_representative_id'),
            ('customer@example.com', 'secret', reverse('home'), 'customer_id'),
        ]

        for email, password, expected_url, session_key in credentials:
            with self.subTest(email=email):
                self.client.session.flush()
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

    def test_logout_flushes_session(self):
        self.login_as_customer()

        response = self.client.get(reverse('logout'))

        self.assertRedirects(response, reverse('home'))
        self.assertNotIn('customer_id', self.client.session)

    def test_customer_signup_creates_account_and_blocks_duplicates(self):
        signup_payload = {
            'first_name': 'New',
            'last_name': 'Customer',
            'email': 'new@example.com',
            'phone_number': '09111111111',
            'password': 'secret',
            'confirm_password': 'secret',
        }

        response = self.client.post(reverse('signup'), signup_payload)

        self.assertRedirects(response, reverse('login'))
        self.assertTrue(Customer.objects.filter(email='new@example.com').exists())

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

        self.assertRedirects(edit_response, reverse('property_list'))
        self.assertRedirects(booking_response, reverse('service_status'))

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
