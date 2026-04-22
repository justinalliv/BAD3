import logging

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from .models import WorkflowNotificationLog


logger = logging.getLogger(__name__)

ROLE_CUSTOMER = "customer"
ROLE_OM = "operations_manager"
ROLE_TECHNICIAN = "technician"
ROLE_SALES = "sales"

WORKFLOW_EVENT_ESTIMATED_BILL_CREATED = "estimated_bill_created"
WORKFLOW_EVENT_ESTIMATED_BILL_CONFIRMED = "estimated_bill_confirmed"
WORKFLOW_EVENT_SERVICE_REPORT_SUBMITTED = "service_report_submitted"
WORKFLOW_EVENT_INVOICE_CREATED_PENDING_PAYMENT = "invoice_created_pending_payment"
WORKFLOW_EVENT_PAYMENT_PROOF_REJECTED = "payment_proof_rejected"
WORKFLOW_EVENT_INSPECTION_BOOKED_FOR_CONFIRMATION = "inspection_booked_for_confirmation"


def _customer_notification_email():
    return getattr(settings, "WORKFLOW_NOTIFICATION_CUSTOMER_EMAIL", "justinvilya@gmail.com")


def _customer_notification_name():
    return getattr(settings, "WORKFLOW_NOTIFICATION_CUSTOMER_NAME", "Justin Villavicencio")


def _om_notification_email():
    return getattr(settings, "WORKFLOW_NOTIFICATION_OM_EMAIL", "supreme.biotech.om@gmail.com")


def _full_name(first_name, last_name, default_value=""):
    name = f"{(first_name or '').strip()} {(last_name or '').strip()}".strip()
    return name or default_value


def _compose_email_message(service, *, greeting_name, intro, next_action, related_record_id=""):
    customer = getattr(service, "customer", None)
    property_obj = getattr(service, "property", None)
    customer_name = _full_name(
        getattr(customer, "first_name", ""),
        getattr(customer, "last_name", ""),
        _customer_notification_name(),
    )
    property_name = getattr(property_obj, "property_name", "") or "-"
    city = getattr(property_obj, "city", "") or "-"
    province = getattr(property_obj, "province", "") or "-"
    timestamp = timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M:%S %Z")

    details = [
        f"Customer: {customer_name}",
        f"Service ID: {service.id}",
        f"Property: {property_name}",
        f"Location: {city}, {province}",
        f"Current Status: {service.status}",
        f"Triggered At: {timestamp}",
    ]
    if related_record_id:
        details.append(f"Reference: {related_record_id}")

    return (
        f"Hello {greeting_name},\n\n"
        f"{intro}\n\n"
        f"Next Required Action:\n{next_action}\n\n"
        f"Record Details:\n- "
        + "\n- ".join(details)
        + "\n\nPlease log in to continue the workflow."
    )


def _build_customer_email_content(event_type, service, *, next_action, related_record_id=""):
    subject_map = {
        WORKFLOW_EVENT_ESTIMATED_BILL_CREATED: "Action Needed: Review Your Estimated Bill",
        WORKFLOW_EVENT_INVOICE_CREATED_PENDING_PAYMENT: "Action Needed: Submit Your Payment Proof",
        WORKFLOW_EVENT_PAYMENT_PROOF_REJECTED: "Action Needed: Submit Your Payment Proof",
    }
    intro_map = {
        WORKFLOW_EVENT_ESTIMATED_BILL_CREATED: "Your service workflow has advanced. The estimated bill is now ready for your review and confirmation.",
        WORKFLOW_EVENT_INVOICE_CREATED_PENDING_PAYMENT: "Your service workflow has advanced. Your invoice is now available and payment proof submission is needed.",
        WORKFLOW_EVENT_PAYMENT_PROOF_REJECTED: "Your payment proof was reviewed and needs correction before processing can continue.",
    }
    subject = subject_map.get(event_type, "Update on Your Service Request")
    intro = intro_map.get(event_type, "Your service workflow has advanced and your action is required.")
    message = _compose_email_message(
        service,
        greeting_name=_customer_notification_name(),
        intro=intro,
        next_action=next_action,
        related_record_id=related_record_id,
    )
    return subject, message


def _build_om_email_content(event_type, service, *, next_action, related_record_id=""):
    subject_map = {
        WORKFLOW_EVENT_INSPECTION_BOOKED_FOR_CONFIRMATION: "Action Required: New Inspection Booking Awaiting Confirmation",
        WORKFLOW_EVENT_ESTIMATED_BILL_CONFIRMED: "Action Required: Estimated Bill Confirmed",
        WORKFLOW_EVENT_SERVICE_REPORT_SUBMITTED: "Action Required: Service Report Submitted",
    }
    intro_map = {
        WORKFLOW_EVENT_INSPECTION_BOOKED_FOR_CONFIRMATION: "A customer submitted a new inspection booking and the workflow is now in For Confirmation.",
        WORKFLOW_EVENT_ESTIMATED_BILL_CONFIRMED: "A customer confirmed the estimated bill and the workflow moved to Operations Manager.",
        WORKFLOW_EVENT_SERVICE_REPORT_SUBMITTED: "A service report has been submitted and the workflow moved to Operations Manager.",
    }
    subject = subject_map.get(event_type, "Action Required: Workflow Advanced to OM")
    intro = intro_map.get(event_type, "The workflow advanced and Operations Manager action is now needed.")
    message = _compose_email_message(
        service,
        greeting_name="Operations Manager",
        intro=intro,
        next_action=next_action,
        related_record_id=related_record_id,
    )
    return subject, message


def send_workflow_email(
    *,
    event_type,
    recipient_role,
    recipient_email,
    subject,
    message,
    event_key,
    service=None,
    metadata=None,
):
    metadata = metadata or {}
    notification, created = WorkflowNotificationLog.objects.get_or_create(
        event_key=event_key,
        defaults={
            "event_type": event_type,
            "recipient_role": recipient_role,
            "recipient_email": recipient_email,
            "service": service,
            "status": WorkflowNotificationLog.STATUS_PENDING,
            "metadata": metadata,
        },
    )

    if not created and notification.status == WorkflowNotificationLog.STATUS_SENT:
        logger.warning(
            "Workflow notification duplicate skipped: event=%s recipient=%s service_id=%s",
            event_type,
            recipient_email,
            getattr(service, "id", None),
        )
        return False

    logger.warning(
        "Workflow notification triggered: event=%s recipient=%s role=%s service_id=%s key=%s",
        event_type,
        recipient_email,
        recipient_role,
        getattr(service, "id", None),
        event_key,
    )

    try:
        notification.event_type = event_type
        notification.recipient_role = recipient_role
        notification.recipient_email = recipient_email
        notification.service = service
        notification.metadata = metadata
        notification.attempts += 1
        notification.status = WorkflowNotificationLog.STATUS_PENDING
        notification.error_message = ""
        notification.save(
            update_fields=[
                "event_type",
                "recipient_role",
                "recipient_email",
                "service",
                "metadata",
                "attempts",
                "status",
                "error_message",
                "updated_at",
            ]
        )

        send_mail(
            subject=subject,
            message=message,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@supreme.local"),
            recipient_list=[recipient_email],
            fail_silently=False,
        )

        notification.status = WorkflowNotificationLog.STATUS_SENT
        notification.sent_at = timezone.now()
        notification.save(update_fields=["status", "sent_at", "updated_at"])
        logger.warning(
            "Workflow notification sent: event=%s recipient=%s service_id=%s",
            event_type,
            recipient_email,
            getattr(service, "id", None),
        )
        return True
    except Exception as exc:
        notification.status = WorkflowNotificationLog.STATUS_FAILED
        notification.error_message = str(exc)[:1000]
        notification.save(update_fields=["status", "error_message", "updated_at"])
        logger.exception(
            "Workflow notification failed: event=%s recipient=%s service_id=%s",
            event_type,
            recipient_email,
            getattr(service, "id", None),
        )
        return False


def notify_customer_next_step(*, event_type, service, next_action, event_key, related_record_id="", metadata=None):
    subject, message = _build_customer_email_content(
        event_type,
        service,
        next_action=next_action,
        related_record_id=related_record_id,
    )
    return send_workflow_email(
        event_type=event_type,
        recipient_role=ROLE_CUSTOMER,
        recipient_email=_customer_notification_email(),
        subject=subject,
        message=message,
        event_key=event_key,
        service=service,
        metadata=metadata,
    )


def notify_om_next_step(*, event_type, service, next_action, event_key, related_record_id="", metadata=None):
    subject, message = _build_om_email_content(
        event_type,
        service,
        next_action=next_action,
        related_record_id=related_record_id,
    )
    return send_workflow_email(
        event_type=event_type,
        recipient_role=ROLE_OM,
        recipient_email=_om_notification_email(),
        subject=subject,
        message=message,
        event_key=event_key,
        service=service,
        metadata=metadata,
    )


def notify_technician_next_step(*args, **kwargs):
    logger.warning("Technician workflow notifications are not enabled yet.")
    return False


def notify_sales_next_step(*args, **kwargs):
    logger.warning("Sales workflow notifications are not enabled yet.")
    return False