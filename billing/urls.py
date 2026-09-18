from rest_framework.routers import DefaultRouter

from django.urls import path

from .views import (
    CustomerViewSet,
    InvoiceViewSet,
    PaymentEventViewSet,
    PlanViewSet,
    SubscriptionViewSet,
    WebhookIntakeView,
)

router = DefaultRouter()
router.register("customers", CustomerViewSet, basename="customer")
router.register("plans", PlanViewSet, basename="plan")
router.register("subscriptions", SubscriptionViewSet, basename="subscription")
router.register("invoices", InvoiceViewSet, basename="invoice")
router.register("events", PaymentEventViewSet, basename="paymentevent")

urlpatterns = router.urls + [
    path("webhooks/payments/", WebhookIntakeView.as_view(), name="webhook-payments"),
]
