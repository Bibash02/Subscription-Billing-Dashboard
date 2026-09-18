import uuid

from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Customer(TimeStampedModel):
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    # id assigned by whatever payment provider we're integrating with
    # (Stripe customer id, etc). Nullable because a customer can exist
    # in our system before they're ever pushed to the provider.
    external_customer_id = models.CharField(max_length=255, blank=True, null=True, unique=True)

    def __str__(self):
        return f"{self.name} <{self.email}>"


class Plan(TimeStampedModel):
    class Interval(models.TextChoices):
        MONTHLY = "monthly", "Monthly"
        YEARLY = "yearly", "Yearly"

    name = models.CharField(max_length=100)
    code = models.SlugField(unique=True)
    interval = models.CharField(max_length=10, choices=Interval.choices, default=Interval.MONTHLY)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    trial_period_days = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.amount} {self.currency}/{self.interval})"


class InvalidTransitionError(Exception):
    """Raised when a status transition is not allowed by the state machine."""


class Subscription(TimeStampedModel):
    class Status(models.TextChoices):
        TRIALING = "trialing", "Trialing"
        ACTIVE = "active", "Active"
        PAST_DUE = "past_due", "Past due"
        CANCELED = "canceled", "Canceled"
        EXPIRED = "expired", "Expired"

    # Which transitions are legal, keyed by current status. This is the
    # single source of truth for how a subscription is allowed to move --
    # nothing else in the codebase (views included) should set `status`
    # directly. See services.py for the functions that call these.
    ALLOWED_TRANSITIONS = {
        Status.TRIALING: {Status.ACTIVE, Status.CANCELED, Status.PAST_DUE, Status.EXPIRED},
        Status.ACTIVE: {Status.PAST_DUE, Status.CANCELED, Status.EXPIRED},
        Status.PAST_DUE: {Status.ACTIVE, Status.CANCELED, Status.EXPIRED},
        Status.CANCELED: set(),   # terminal
        Status.EXPIRED: set(),    # terminal
    }

    customer = models.ForeignKey(Customer, related_name="subscriptions", on_delete=models.CASCADE)
    plan = models.ForeignKey(Plan, related_name="subscriptions", on_delete=models.PROTECT)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.TRIALING)

    current_period_start = models.DateTimeField(default=timezone.now)
    current_period_end = models.DateTimeField(null=True, blank=True)
    trial_end = models.DateTimeField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)
    canceled_at = models.DateTimeField(null=True, blank=True)

    external_subscription_id = models.CharField(max_length=255, blank=True, null=True, unique=True)

    class Meta:
        constraints = [
            # A customer shouldn't have two live subscriptions to the same plan.
            models.UniqueConstraint(
                fields=["customer", "plan"],
                condition=models.Q(status__in=["trialing", "active", "past_due"]),
                name="unique_live_subscription_per_customer_plan",
            )
        ]

    def __str__(self):
        return f"{self.customer} - {self.plan} [{self.status}]"

    def _transition_to(self, new_status, **field_updates):
        """
        Central choke point for every status change. Raises if the
        transition isn't in ALLOWED_TRANSITIONS so a bug elsewhere can't
        silently push a subscription into a nonsense state.
        """
        allowed = self.ALLOWED_TRANSITIONS.get(self.status, set())
        if new_status != self.status and new_status not in allowed:
            raise InvalidTransitionError(
                f"Cannot move subscription {self.pk} from '{self.status}' to '{new_status}'"
            )
        for field, value in field_updates.items():
            setattr(self, field, value)
        self.status = new_status
        self.save(update_fields=list(field_updates.keys()) + ["status", "updated_at"])

    def activate(self, period_end=None):
        self._transition_to(
            self.Status.ACTIVE,
            current_period_end=period_end or self.current_period_end,
        )

    def mark_past_due(self):
        self._transition_to(self.Status.PAST_DUE)

    def cancel(self, at_period_end=False):
        self._transition_to(
            self.Status.CANCELED,
            canceled_at=timezone.now(),
            cancel_at_period_end=at_period_end,
        )

    def expire(self):
        self._transition_to(self.Status.EXPIRED)


class Invoice(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        OPEN = "open", "Open"
        PAID = "paid", "Paid"
        VOID = "void", "Void"
        UNCOLLECTIBLE = "uncollectible", "Uncollectible"

    ALLOWED_TRANSITIONS = {
        Status.DRAFT: {Status.OPEN, Status.VOID},
        Status.OPEN: {Status.PAID, Status.VOID, Status.UNCOLLECTIBLE},
        Status.PAID: set(),
        Status.VOID: set(),
        Status.UNCOLLECTIBLE: {Status.OPEN, Status.VOID},
    }

    customer = models.ForeignKey(Customer, related_name="invoices", on_delete=models.CASCADE)
    subscription = models.ForeignKey(
        Subscription, related_name="invoices", on_delete=models.SET_NULL, null=True, blank=True
    )
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.DRAFT)
    amount_due = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")

    period_start = models.DateTimeField(null=True, blank=True)
    period_end = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    external_invoice_id = models.CharField(max_length=255, blank=True, null=True, unique=True)

    def __str__(self):
        return f"Invoice {self.pk} - {self.customer} [{self.status}]"

    def _transition_to(self, new_status, **field_updates):
        allowed = self.ALLOWED_TRANSITIONS.get(self.status, set())
        if new_status != self.status and new_status not in allowed:
            raise InvalidTransitionError(
                f"Cannot move invoice {self.pk} from '{self.status}' to '{new_status}'"
            )
        for field, value in field_updates.items():
            setattr(self, field, value)
        self.status = new_status
        self.save(update_fields=list(field_updates.keys()) + ["status", "updated_at"])

    def mark_open(self):
        self._transition_to(self.Status.OPEN)

    def mark_paid(self):
        self._transition_to(self.Status.PAID, paid_at=timezone.now())

    def mark_uncollectible(self):
        self._transition_to(self.Status.UNCOLLECTIBLE)

    def void(self):
        self._transition_to(self.Status.VOID)


class PaymentEvent(TimeStampedModel):
    """
    One row per inbound event from the payment provider (Stripe-style
    webhook, or whatever you're simulating). `external_event_id` is
    unique so the same event landing twice -- which providers explicitly
    warn you will happen -- is a no-op the second time, not a double
    application of side effects.
    """

    class Status(models.TextChoices):
        RECEIVED = "received", "Received"
        PROCESSED = "processed", "Processed"
        FAILED = "failed", "Failed"
        IGNORED = "ignored", "Ignored"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    external_event_id = models.CharField(max_length=255, unique=True)
    event_type = models.CharField(max_length=100)
    payload = models.JSONField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RECEIVED)
    error_message = models.TextField(blank=True, default="")
    processed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.event_type} ({self.external_event_id}) [{self.status}]"
