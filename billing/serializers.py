from rest_framework import serializers

from .models import Customer, Invoice, Plan, Subscription, PaymentEvent


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ["id", "name", "email", "external_customer_id", "created_at"]


class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = [
            "id", "name", "code", "interval", "amount", "currency",
            "trial_period_days", "is_active",
        ]


class SubscriptionSerializer(serializers.ModelSerializer):
    # status is intentionally read-only here: the only supported way to
    # change it is through the state-machine methods in services.py /
    # models.py, never a raw PATCH from the API.
    status = serializers.CharField(read_only=True)
    customer = serializers.PrimaryKeyRelatedField(queryset=Customer.objects.all())
    plan = serializers.PrimaryKeyRelatedField(queryset=Plan.objects.all())

    class Meta:
        model = Subscription
        fields = [
            "id", "customer", "plan", "status",
            "current_period_start", "current_period_end", "trial_end",
            "cancel_at_period_end", "canceled_at",
            "external_subscription_id", "created_at", "updated_at",
        ]
        read_only_fields = ["canceled_at", "created_at", "updated_at"]

class InvoiceSerializer(serializers.ModelSerializer):
    status = serializers.CharField(read_only=True)

    class Meta:
        model = Invoice
        fields = [
            "id", "customer", "subscription", "status", "amount_due", "currency",
            "period_start", "period_end", "paid_at", "external_invoice_id",
            "created_at", "updated_at",
        ]
        read_only_fields = ["paid_at", "created_at", "updated_at"]


class PaymentEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentEvent
        fields = [
            "id", "external_event_id", "event_type", "status",
            "error_message", "processed_at", "created_at",
        ]
        read_only_fields = fields


class WebhookEventInputSerializer(serializers.Serializer):
    """Shape of an inbound webhook payload from the (simulated) provider."""
    id = serializers.CharField(help_text="Provider's unique event id")
    type = serializers.CharField(help_text="Event type, e.g. invoice.payment_succeeded")
    data = serializers.DictField()
