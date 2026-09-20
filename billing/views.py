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
    queryset = PaymentEvent.objects.all().order_by("-created_at")
    serializer_class = PaymentEventSerializer
    permission_classes = [IsAuthenticated]

class WebhookIntakeView(APIView):
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
            return Response(
                {"received": True, "status": "failed", "detail": str(exc)},
                status=http_status.HTTP_200_OK,
            )

        return Response(
            {"received": True, "status": event.status, "event_id": str(event.id)},
            status=http_status.HTTP_200_OK,
        )
