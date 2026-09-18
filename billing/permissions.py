from rest_framework.permissions import BasePermission


class HasValidWebhookSecret(BasePermission):
    """
    Stand-in for provider signature verification (e.g. Stripe's
    Stripe-Signature header + webhook signing secret). For learning
    purposes this checks a shared-secret header so the endpoint isn't
    wide open, without needing a real provider account.

    Swap the body of has_permission() for real HMAC signature
    verification once you're pointing this at an actual provider.
    """

    def has_permission(self, request, view):
        from django.conf import settings

        expected = getattr(settings, "WEBHOOK_SHARED_SECRET", None)
        if not expected:
            # No secret configured (e.g. local dev) -- don't lock yourself out.
            return True
        provided = request.headers.get("X-Webhook-Secret")
        return provided == expected
