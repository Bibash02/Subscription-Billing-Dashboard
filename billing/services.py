from django.db import transaction
from django.utils import timezone
from .models import Invoice, PaymentEvent, Subscription

class WebhookProcessingError(Exception):
    pass

def process_webhook_event(external_event_id, event_type, payload):
    with transaction.atomic():
        event, created = PaymentEvent.objects.select_for_update().get_or_create(
            external_event_id=external_event_id,
            defaults={"event_type": event_type, "payload": payload},
        )

        if not created and event.status == PaymentEvent.Status.PROCESSED:
            return event

        handler = _HANDLERS.get(event_type)
        if handler is None:
            event.status = PaymentEvent.Status.IGNORED
            event.error_message = f"No handler registered for event type '{event_type}'"
            event.save(update_fields=["status", "error_message", "updated_at"])
            return event

        try:
            handler(payload)
        except Exception as exc:  
            event.status = PaymentEvent.Status.FAILED
            event.error_message = str(exc)
            event.save(update_fields=["status", "error_message", "updated_at"])
            raise WebhookProcessingError(str(exc)) from exc

        event.status = PaymentEvent.Status.PROCESSED
        event.processed_at = timezone.now()
        event.save(update_fields=["status", "processed_at", "updated_at"])
        return event

def _get_subscription(payload):
    sub_id = payload.get("subscription_external_id")
    if not sub_id:
        raise WebhookProcessingError("payload missing 'subscription_external_id'")
    try:
        return Subscription.objects.select_for_update().get(external_subscription_id=sub_id)
    except Subscription.DoesNotExist as exc:
        raise WebhookProcessingError(f"No subscription with external id {sub_id}") from exc

def _get_invoice(payload):
    invoice_id = payload.get("invoice_external_id")
    if not invoice_id:
        raise WebhookProcessingError("payload missing 'invoice_external_id'")
    try:
        return Invoice.objects.select_for_update().get(external_invoice_id=invoice_id)
    except Invoice.DoesNotExist as exc:
        raise WebhookProcessingError(f"No invoice with external id {invoice_id}") from exc

def handle_subscription_activated(payload):
    sub = _get_subscription(payload)
    period_end = payload.get("current_period_end")
    if sub.status in (Subscription.Status.TRIALING, Subscription.Status.PAST_DUE):
        sub.activate(period_end=period_end or sub.current_period_end)

def handle_subscription_past_due(payload):
    sub = _get_subscription(payload)
    if sub.status != Subscription.Status.PAST_DUE:
        sub.mark_past_due()

def handle_subscription_canceled(payload):
    sub = _get_subscription(payload)
    if sub.status != Subscription.Status.CANCELED:
        sub.cancel(at_period_end=payload.get("cancel_at_period_end", False))

def handle_subscription_expired(payload):
    sub = _get_subscription(payload)
    if sub.status != Subscription.Status.EXPIRED:
        sub.expire()

def handle_invoice_payment_succeeded(payload):
    invoice = _get_invoice(payload)
    if invoice.status != Invoice.Status.PAID:
        invoice.mark_paid()
    if invoice.subscription_id and invoice.subscription.status == Subscription.Status.PAST_DUE:
        invoice.subscription.activate()

def handle_invoice_payment_failed(payload):
    invoice = _get_invoice(payload)
    if invoice.status not in (Invoice.Status.PAID, Invoice.Status.VOID):
        invoice.mark_uncollectible()
    if invoice.subscription_id and invoice.subscription.status == Subscription.Status.ACTIVE:
        invoice.subscription.mark_past_due()

_HANDLERS = {
    "subscription.activated": handle_subscription_activated,
    "subscription.past_due": handle_subscription_past_due,
    "subscription.canceled": handle_subscription_canceled,
    "subscription.expired": handle_subscription_expired,
    "invoice.payment_succeeded": handle_invoice_payment_succeeded,
    "invoice.payment_failed": handle_invoice_payment_failed,
}
