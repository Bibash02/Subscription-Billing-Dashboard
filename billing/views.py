from rest_framework import generics, status as http_status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from drf_spectacular.utils import OpenApiParameter, extend_schema

from .models import Customer, Invoice, Plan, PaymentEvent, Subscription
from .permissions import HasValidWebhookSecret
from .serializers import (
    CustomerSerializer,
    InvoiceSerializer,
    PaymentEventSerializer,
    PlanSerializer,
    SubscriptionSerializer,
    WebhookEventInputSerializer,
    WebhookEventResponseSerializer,
)
from .services import WebhookProcessingError, process_webhook_event

@extend_schema(tags=["Customer"])
class CustomerViewSet(viewsets.ModelViewSet):
    queryset = Customer.objects.all().order_by("-created_at")
    serializer_class = CustomerSerializer
    permission_classes = [IsAuthenticated]

@extend_schema(tags=["Plan"])
class PlanViewSet(viewsets.ModelViewSet):
    queryset = Plan.objects.all().order_by("name")
    serializer_class = PlanSerializer
    permission_classes = [IsAuthenticated]

@extend_schema(tags=["Subscription"])
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

@extend_schema(tags=["Invoice"])
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

@extend_schema(tags=["Payment Event"])
class PaymentEventViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = PaymentEvent.objects.all().order_by("-created_at")
    serializer_class = PaymentEventSerializer
    permission_classes = [IsAuthenticated]

@extend_schema(tags=["Webhook Intake"])
class WebhookIntakeView(generics.GenericAPIView):
    permission_classes = [HasValidWebhookSecret]
    serializer_class = WebhookEventInputSerializer

    @extend_schema(
        request=WebhookEventInputSerializer,
        responses={http_status.HTTP_200_OK: WebhookEventResponseSerializer},
        parameters=[
            OpenApiParameter(
                name="X-Webhook-Secret",
                type=str,
                location=OpenApiParameter.HEADER,
                description="Shared webhook secret, when configured by the server.",
            )
        ],
    )
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
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
