from rest_framework.permissions import BasePermission

class HasValidWebhookSecret(BasePermission):
    def has_permission(self, request, view):
        from django.conf import settings

        expected = getattr(settings, "WEBHOOK_SHARED_SECRET", None)
        if not expected:
            # No secret configured (e.g. local dev) -- don't lock yourself out.
            return True
        provided = request.headers.get("X-Webhook-Secret")
        return provided == expected
