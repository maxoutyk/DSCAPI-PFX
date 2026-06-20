from django.test import SimpleTestCase

from accounts.log_filters import redact_sensitive_text


class SensitiveLogRedactionTests(SimpleTestCase):
    def test_redacts_password_fields(self):
        raw = '{"password":"secret123","nicPassword":"abc"}'
        redacted = redact_sensitive_text(raw)
        self.assertNotIn('secret123', redacted)
        self.assertNotIn('abc', redacted)
        self.assertIn('[REDACTED]', redacted)

    def test_redacts_sign_token_query_values(self):
        raw = 'GET /api/agent/jobs/1/?sign_token=super-secret-token'
        redacted = redact_sensitive_text(raw)
        self.assertNotIn('super-secret-token', redacted)
        self.assertIn('[REDACTED]', redacted)
