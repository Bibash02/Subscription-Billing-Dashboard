from rest_framework import status as http_status
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Customer, Invoice, Plan, PaymentEvent, Subscription
from .permissions import HasValidWebhookSecret
from .serializers import (
    CustomerSerializer,
    InvoiceSerializer,
    PaymentEventSerializer,
    PlanSerializer,
    SubscriptionSerializer,
    WebhookEventInputSerializer,
)
from .services import WebhookProcessingError, process_webhook_event


class CustomerViewSet(viewsets.ModelViewSet):
    queryset = Customer.objects.all().order_by("-created_at")
    serializer_class = CustomerSerializer
    permission_classes = [IsAuthenticated]


class PlanViewSet(viewsets.ModelViewSet):
    queryset = Plan.objects.all().order_by("name")
    serializer_class = PlanSerializer
    permission_classes = [IsAuthenticated]


class SubscriptionViewSet(viewsets.ModelViewSet):
    """
    Create/read/list only touch plain fields. `status` is read-only on
    the serializer, so there is no code path here that lets a client
    flip a subscription to "active" directly -- that only happens
    through a webhook event via services.process_webhook_event, or an
    explicit admin action.
    """
    queryset = Subscription.objects.select_related("customer", "plan").order_by("-created_at")
    serializer_class = SubscriptionSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "head", "options"]  # no PATCH/PUT/DELETE from the API

    def get_queryset(self):
        qs = super().get_queryset()
        customer_id = self.request.query_params.get("customer")
        status_filter = self.request.query_params.get("status")
        if customer_id:
            qs = qs.filter(customer_id=customer_id)
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs


class InvoiceViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Invoice.objects.select_related("customer", "subscription").order_by("-created_at")
    serializer_class = InvoiceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        customer_id = self.request.query_params.get("customer")
        status_filter = self.request.query_params.get("status")
        if customer_id:
            qs = qs.filter(customer_id=customer_id)
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs


class PaymentEventViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only audit trail of every webhook event we've ever received."""
    queryset = PaymentEvent.objects.all().order_by("-created_at")
    serializer_class = PaymentEventSerializer
    permission_classes = [IsAuthenticated]


class WebhookIntakeView(APIView):
    """
    POST /api/webhooks/payments/

    Body shape:
        {"id": "evt_123", "type": "invoice.payment_succeeded", "data": {...}}

    This view does almost nothing on purpose: validate the shape, hand
    off to services.process_webhook_event, report the outcome. All the
    actual state-transition logic lives in services.py so it stays
    testable without spinning up HTTP.
    """
    permission_classes = [HasValidWebhookSecret]

    def post(self, request):
        serializer = WebhookEventInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        try:
            event = process_webhook_event(
                external_event_id=validated["id"],
                event_type=validated["type"],
                payload=validated["data"],
            )
        except WebhookProcessingError as exc:
            # Still 200: telling the provider "no, retry me" on a bad
            # payload just causes it to hammer the same broken event
            # forever. We've recorded the failure on the PaymentEvent row
            # for a human to look at instead.
            return Response(
                {"received": True, "status": "failed", "detail": str(exc)},
                status=http_status.HTTP_200_OK,
            )

        return Response(
            {"received": True, "status": event.status, "event_id": str(event.id)},
            status=http_status.HTTP_200_OK,
        )
