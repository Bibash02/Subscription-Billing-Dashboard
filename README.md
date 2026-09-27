# Subscription Billing Dashboard (DRF)

A learning project modeling plans, customers, subscriptions, invoices, and
payment events, with an emphasis on **handling change safely** rather than
CRUD for its own sake.

## Setup

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Billing endpoints live under `/billing/`, account endpoints under `/accounts/`,
and the OpenAPI/Swagger documentation is available at `/api/docs/`. The webhook
accepts `POST /billing/webhooks/payments/`; Swagger's **Try it out** form
includes its JSON request body and the optional `X-Webhook-Secret` header.

## Models (`billing/models.py`)

- **Customer** — name, email, optional `external_customer_id` (provider's id).
- **Plan** — name, price, interval, trial length.
- **Subscription** — status is one of `trialing / active / past_due /
  canceled / expired`. A `UniqueConstraint` stops a customer holding two
  live subscriptions to the same plan at once.
- **Invoice** — status is one of `draft / open / paid / void /
  uncollectible`.
- **PaymentEvent** — one row per inbound webhook, keyed on the provider's
  `external_event_id` (unique). This is what makes duplicate deliveries safe.

## The state machine

`Subscription` and `Invoice` each define `ALLOWED_TRANSITIONS`: a dict of
which status can move to which. Every status change goes through a single
private method (`_transition_to`) that checks the transition is legal before
saving — raising `InvalidTransitionError` otherwise. Public methods
(`activate()`, `cancel()`, `mark_paid()`, etc.) are the only way to change
status.

**Nothing else writes to `.status` directly.** The DRF serializers mark
`status` read-only, the `SubscriptionViewSet` disables PATCH/PUT/DELETE
entirely, and the admin makes `status` a readonly field with explicit
actions (Activate / Mark past due / Cancel / Expire) instead of a raw
dropdown. If you want a subscription to change status, there's exactly one
path in and it's auditable.

## Idempotent webhook handling (`billing/services.py`)

`process_webhook_event(external_event_id, event_type, payload)` is the only
entry point for reacting to the payment provider:

1. `get_or_create`s a `PaymentEvent` row keyed on `external_event_id`,
   inside `select_for_update()` — two near-simultaneous deliveries of the
   same event serialize instead of racing.
2. If that event was already `processed`, it returns immediately. Nothing
   fires twice.
3. Otherwise it dispatches to a small handler function per `event_type`
   (e.g. `handle_invoice_payment_succeeded`), each of which is itself
   written to be safe to re-run (checks current status before acting).
4. Unrecognised event types are stored as `ignored`, not silently dropped —
   you can see them in the admin and add a handler later.
5. A handler that raises is caught, the event is marked `failed` with the
   error message saved, and the webhook view still returns `200` (so the
   provider doesn't retry-storm a payload that will never succeed) while
   the failure sits visibly in the `PaymentEvent` table for a human.

`billing/views.py::WebhookIntakeView` is intentionally thin — it validates
the request shape and calls `process_webhook_event`. All the actual
decision-making is in `services.py`, so it can be unit tested (see
`billing/tests/test_billing.py`) without touching HTTP at all.

## Simulating provider events without a real payment account

```bash
python manage.py simulate_webhook invoice.payment_succeeded \
    --invoice-id inv_ext_1 --event-id evt_1

# run it again with the same --event-id: second call is a no-op
python manage.py simulate_webhook invoice.payment_succeeded \
    --invoice-id inv_ext_1 --event-id evt_1
```

Event types wired up in `services._HANDLERS`:
`subscription.activated`, `subscription.past_due`, `subscription.canceled`,
`subscription.expired`, `invoice.payment_succeeded`, `invoice.payment_failed`.

## Webhook auth

`billing/permissions.py::HasValidWebhookSecret` checks a shared-secret
header (`X-Webhook-Secret`) against `settings.WEBHOOK_SHARED_SECRET`
(from the `WEBHOOK_SHARED_SECRET` env var). It's a stand-in for real
signature verification (e.g. Stripe's `Stripe-Signature` HMAC scheme) —
swap the body of `has_permission()` for the real thing once you're
pointing this at an actual provider's test mode.

## Tests

```bash
python manage.py test billing
```

Covers: every allowed/disallowed state transition, duplicate webhook
delivery being a no-op, and cross-model effects (a paid invoice reactivating
a past-due subscription; a failed one pushing an active subscription to
past-due).

## Where to take it next

- Swap the shared-secret check for real HMAC verification against a
  provider's test mode (Stripe, Paddle, LemonSqueezy all have one).
- Add a periodic task that expires subscriptions whose `current_period_end`
  has passed and are still `past_due`.
- Add a `dunning` flow: retry schedule + emails for `past_due` subscriptions
  before they hit `canceled`.
