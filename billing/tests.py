from django.test import SimpleTestCase
from drf_spectacular.generators import SchemaGenerator


class WebhookSchemaTests(SimpleTestCase):
    def test_webhook_post_is_available_in_openapi_schema(self):
        schema = SchemaGenerator().get_schema(public=True)
        operation = schema["paths"]["/billing/webhooks/payments/"]["post"]

        self.assertIn("requestBody", operation)
        self.assertIn("200", operation["responses"])
        self.assertIn(
            "X-Webhook-Secret",
            [parameter["name"] for parameter in operation["parameters"]],
        )

    def test_browsable_api_renders_webhook_post_form(self):
        response = self.client.get(
            "/billing/webhooks/payments/",
            HTTP_ACCEPT="text/html",
        )

        self.assertEqual(response.status_code, 405)
        self.assertContains(response, 'method="POST"', status_code=405)
        self.assertContains(response, "<textarea", status_code=405)
