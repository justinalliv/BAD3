import json
from unittest.mock import patch

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import (
	Customer,
	EstimatedBill,
	EstimatedBillItem,
	InvoiceItemOption,
	OperationsManager,
	PaymentProof,
	Property,
	SalesRepresentative,
	Service,
	ServiceFormOption,
	Technician,
	WorkflowNotificationLog,
)
from .workflow_notifications import (
	WORKFLOW_EVENT_ESTIMATED_BILL_CONFIRMED,
	WORKFLOW_EVENT_ESTIMATED_BILL_CREATED,
	WORKFLOW_EVENT_INVOICE_CREATED_PENDING_PAYMENT,
	WORKFLOW_EVENT_SERVICE_REPORT_SUBMITTED,
	notify_customer_next_step,
)


@override_settings(
	EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
	WORKFLOW_NOTIFICATION_OM_EMAIL="supreme.biotech.om@gmail.com",
	WORKFLOW_NOTIFICATION_CUSTOMER_EMAIL="justinvilya@gmail.com",
	WORKFLOW_NOTIFICATION_CUSTOMER_NAME="Justin Villavicencio",
)
class WorkflowNotificationTests(TestCase):
	def setUp(self):
		self.om = OperationsManager.objects.create(
			first_name="Ops",
			last_name="Manager",
			email="om@test.local",
			password="secret",
		)
		self.technician = Technician.objects.create(
			technician_id="TECH-001",
			first_name="Tech",
			last_name="User",
			email="tech@test.local",
			password="secret",
			is_active=True,
		)
		self.sales = SalesRepresentative.objects.create(
			first_name="Sales",
			last_name="Rep",
			email="sales@test.local",
			password="secret",
			is_active=True,
		)
		self.customer = Customer.objects.create(
			first_name="Real",
			last_name="Customer",
			email="real.customer@test.local",
			phone_number="09123456789",
			password="secret",
			is_active=True,
		)
		self.property = Property.objects.create(
			customer=self.customer,
			property_name="Sample Property",
			street_number="123",
			street="Main Street",
			city="Quezon City",
			province="Metro Manila",
			zip_code="1100",
			property_type="Residential",
			floor_area="100",
		)

	def _set_session(self, **entries):
		session = self.client.session
		session.update(entries)
		session.save()

	def _create_service(self, status):
		return Service.objects.create(
			customer=self.customer,
			property=self.property,
			preferred_service="Termite Control",
			pest_problem="Termites",
			date="2026-04-22",
			time_slot="8:00 AM - 9:00 AM",
			status=status,
		)

	def test_estimated_bill_created_notifies_customer(self):
		service = self._create_service("Ongoing Inspection")
		ServiceFormOption.objects.get_or_create(
			form_section="Treatment",
			field_name="Treatment Service",
			option_value="Termite Control",
			defaults={"is_active": True},
		)
		self._set_session(om_id=self.om.id, om_name="Ops Manager")

		response = self.client.post(
			reverse("om_create_estimated_bill"),
			{
				"selected_service_id": str(service.id),
				"items_json": json.dumps([
					{"service_type": "Termite Control", "quantity": "1"}
				]),
			},
		)

		self.assertEqual(response.status_code, 302)
		service.refresh_from_db()
		self.assertEqual(service.status, "Estimated Bill Created")
		self.assertEqual(len(mail.outbox), 1)
		self.assertEqual(mail.outbox[0].to, ["justinvilya@gmail.com"])
		self.assertIn("Estimated Bill", mail.outbox[0].subject)

		log = WorkflowNotificationLog.objects.get(event_type=WORKFLOW_EVENT_ESTIMATED_BILL_CREATED)
		self.assertEqual(log.status, WorkflowNotificationLog.STATUS_SENT)
		self.assertEqual(log.recipient_role, "customer")

	def test_customer_confirm_estimated_bill_notifies_om_only_on_true_transition(self):
		service = self._create_service("Estimated Bill Created")
		bill = EstimatedBill.objects.create(service=service, operations_manager=self.om)
		EstimatedBillItem.objects.create(
			estimated_bill=bill,
			service_type="Termite Control",
			quantity=1,
			unit_price="3000.00",
		)
		self._set_session(customer_id=self.customer.id, customer_name="Customer")

		response = self.client.post(reverse("customer_confirm_estimated_bill", args=[bill.id]))
		self.assertEqual(response.status_code, 302)

		service.refresh_from_db()
		self.assertEqual(service.status, "For Treatment Booking")
		self.assertEqual(len(mail.outbox), 1)
		self.assertEqual(mail.outbox[0].to, ["supreme.biotech.om@gmail.com"])
		self.assertIn("Estimated Bill Confirmed", mail.outbox[0].subject)
		self.assertTrue(
			WorkflowNotificationLog.objects.filter(event_type=WORKFLOW_EVENT_ESTIMATED_BILL_CONFIRMED).exists()
		)

		mail.outbox.clear()
		response = self.client.post(reverse("customer_confirm_estimated_bill", args=[bill.id]))
		self.assertEqual(response.status_code, 302)
		self.assertEqual(len(mail.outbox), 0)

	def test_service_report_submission_notifies_om(self):
		service = self._create_service("Ongoing Treatment")
		self._set_session(technician_id=self.technician.id, technician_name="Tech User")

		select_response = self.client.post(
			reverse("technician_create_service_report"),
			{
				"step": "select",
				"action": "continue",
				"selected_service_id": str(service.id),
			},
		)
		self.assertEqual(select_response.status_code, 200)

		submit_response = self.client.post(
			reverse("technician_create_service_report"),
			{
				"step": "details",
				"action": "submit",
				"chemicals_json": json.dumps([]),
				"treated_areas_json": json.dumps([
					{
						"area_name": "Kitchen",
						"infestation_level": "Low",
						"spray": True,
						"mist": False,
						"rat_bait": False,
						"powder": False,
						"date": "2026-04-22",
						"remarks": "",
						"recommendation": "",
					}
				]),
			},
		)

		self.assertEqual(submit_response.status_code, 302)
		self.assertEqual(len(mail.outbox), 1)
		self.assertEqual(mail.outbox[0].to, ["supreme.biotech.om@gmail.com"])
		self.assertIn("Service Report Submitted", mail.outbox[0].subject)
		self.assertTrue(
			WorkflowNotificationLog.objects.filter(event_type=WORKFLOW_EVENT_SERVICE_REPORT_SUBMITTED).exists()
		)

	def test_invoice_created_pending_payment_notifies_customer(self):
		service = self._create_service("Ongoing Treatment")
		bill = EstimatedBill.objects.create(service=service, operations_manager=self.om)
		EstimatedBillItem.objects.create(
			estimated_bill=bill,
			service_type="Termite Control",
			quantity=1,
			unit_price="3000.00",
		)
		item_option = InvoiceItemOption.objects.create(
			name="Transportation Fee",
			description="Travel fee",
			default_unit_price="500.00",
			is_active=True,
		)
		self._set_session(om_id=self.om.id, om_name="Ops Manager")

		response = self.client.post(
			reverse("om_create_invoice"),
			{
				"selected_service_id": str(service.id),
				"items_json": json.dumps([
					{
						"service_item_id": str(item_option.id),
						"quantity": "2",
					}
				]),
			},
		)

		self.assertEqual(response.status_code, 302)
		service.refresh_from_db()
		self.assertEqual(service.status, "Pending Payment")
		self.assertEqual(len(mail.outbox), 1)
		self.assertEqual(mail.outbox[0].to, ["justinvilya@gmail.com"])
		self.assertIn("Payment Proof", mail.outbox[0].subject)
		self.assertTrue(
			WorkflowNotificationLog.objects.filter(
				event_type=WORKFLOW_EVENT_INVOICE_CREATED_PENDING_PAYMENT
			).exists()
		)

	def test_notification_failure_does_not_break_transition_and_logs_failure(self):
		service = self._create_service("Estimated Bill Created")
		bill = EstimatedBill.objects.create(service=service, operations_manager=self.om)
		self._set_session(customer_id=self.customer.id, customer_name="Customer")

		with patch("sangapp.workflow_notifications.send_mail", side_effect=RuntimeError("smtp down")):
			response = self.client.post(reverse("customer_confirm_estimated_bill", args=[bill.id]))

		self.assertEqual(response.status_code, 302)
		service.refresh_from_db()
		self.assertEqual(service.status, "For Treatment Booking")

		log = WorkflowNotificationLog.objects.get(event_type=WORKFLOW_EVENT_ESTIMATED_BILL_CONFIRMED)
		self.assertEqual(log.status, WorkflowNotificationLog.STATUS_FAILED)
		self.assertGreaterEqual(log.attempts, 1)

	def test_duplicate_event_key_sends_only_once(self):
		service = self._create_service("Estimated Bill Created")

		sent_first = notify_customer_next_step(
			event_type=WORKFLOW_EVENT_ESTIMATED_BILL_CREATED,
			service=service,
			next_action="Review the bill.",
			event_key=f"duplicate-key:{service.id}",
			related_record_id="Estimated Bill #1",
		)
		sent_second = notify_customer_next_step(
			event_type=WORKFLOW_EVENT_ESTIMATED_BILL_CREATED,
			service=service,
			next_action="Review the bill.",
			event_key=f"duplicate-key:{service.id}",
			related_record_id="Estimated Bill #1",
		)

		self.assertTrue(sent_first)
		self.assertFalse(sent_second)
		self.assertEqual(len(mail.outbox), 1)
		self.assertEqual(WorkflowNotificationLog.objects.filter(event_key=f"duplicate-key:{service.id}").count(), 1)

	def test_payment_reject_notifies_customer(self):
		service = self._create_service("Pending Payment")
		bill = EstimatedBill.objects.create(service=service, operations_manager=self.om)
		EstimatedBillItem.objects.create(
			estimated_bill=bill,
			service_type="Termite Control",
			quantity=1,
			unit_price="3000.00",
		)

		item_option = InvoiceItemOption.objects.create(
			name="Labor Fee",
			description="Labor",
			default_unit_price="500.00",
			is_active=True,
		)
		self._set_session(om_id=self.om.id, om_name="Ops Manager")
		invoice_response = self.client.post(
			reverse("om_create_invoice"),
			{
				"selected_service_id": str(service.id),
				"items_json": json.dumps([
					{
						"service_item_id": str(item_option.id),
						"quantity": "1",
					}
				]),
			},
		)
		self.assertEqual(invoice_response.status_code, 302)
		service.refresh_from_db()
		service.status = "Pending Payment"
		service.save(update_fields=["status"])

		proof = PaymentProof.objects.create(
			service=service,
			invoice=service.invoices.first(),
			customer=self.customer,
			payment_type="Online Bank Transfer",
			bank_used="BDO",
			account_number="0000-0000-0000",
			reference_number="REF-123",
			amount_paid="3500.00",
			proof_file="payment_proofs/sample.pdf",
			status=PaymentProof.STATUS_FOR_VALIDATION,
		)

		self._set_session(sales_representative_id=self.sales.id)
		mail.outbox.clear()
		response = self.client.post(
			reverse("sales_representative_review_payment_proof", args=[proof.id]),
			{
				"action": "reject",
				"rejection_reason": "Unreadable proof",
			},
		)

		self.assertEqual(response.status_code, 302)
		self.assertEqual(len(mail.outbox), 1)
		self.assertEqual(mail.outbox[0].to, ["justinvilya@gmail.com"])
