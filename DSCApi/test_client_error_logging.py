import json
import logging

from django.http import HttpResponse, JsonResponse
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from rest_framework.response import Response

from DSCApi.client_error_logging import (
    ClientErrorLoggingMiddleware,
    request_actor,
    summarize_response_body,
)
from accounts.authentication import APIKeyUser
from accounts.models import Tenant, TenantStatus


class SummarizeResponseBodyTests(SimpleTestCase):
    def test_drf_response_json(self):
        response = Response({'error': 'Invalid PDF'}, status=400)
        self.assertEqual(summarize_response_body(response), '{"error": "Invalid PDF"}')

    def test_json_response(self):
        response = JsonResponse({'password': 'secret'}, status=400)
        self.assertIn('[REDACTED]', summarize_response_body(response))

    def test_html_response_is_summarized(self):
        response = HttpResponse('<html><body>Forbidden</body></html>', status=403)
        self.assertEqual(summarize_response_body(response), '<html response>')


class ClientErrorLoggingMiddlewareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.log_records: list[logging.LogRecord] = []
        self.handler = logging.Handler()
        self.handler.emit = self.log_records.append
        self.logger = logging.getLogger('http.client_error')
        self.previous_level = self.logger.level
        self.logger.addHandler(self.handler)
        self.logger.setLevel(logging.WARNING)

    def tearDown(self):
        self.logger.removeHandler(self.handler)
        self.logger.setLevel(self.previous_level)

    def _middleware_for_status(self, status_code, body=None, *, path='/api/signpdf-pfx'):
        def get_response(request):
            if body is None:
                return JsonResponse({'error': 'bad input'}, status=status_code)
            return body

        middleware = ClientErrorLoggingMiddleware(get_response)
        request = self.factory.post(path)
        request.user = type('User', (), {'is_authenticated': False})()
        return middleware(request)

    @override_settings(LOG_CLIENT_ERROR_STATUS_CODES=(400, 403, 404))
    def test_logs_400_with_detail(self):
        self._middleware_for_status(400)
        self.assertEqual(len(self.log_records), 1)
        message = self.log_records[0].getMessage()
        self.assertIn('HTTP 400 POST /api/signpdf-pfx', message)
        self.assertIn('bad input', message)

    @override_settings(LOG_CLIENT_ERROR_STATUS_CODES=(400, 403, 404))
    def test_does_not_log_200_or_302(self):
        self._middleware_for_status(200, HttpResponse('ok', status=200))
        self._middleware_for_status(302, HttpResponse(status=302))
        self.assertEqual(self.log_records, [])

    @override_settings(LOG_CLIENT_ERROR_STATUS_CODES=(400, 403, 404))
    def test_logs_403_and_404(self):
        self._middleware_for_status(403)
        self._middleware_for_status(404, path='/missing')
        self.assertEqual(len(self.log_records), 2)
        self.assertIn('HTTP 403', self.log_records[0].getMessage())
        self.assertIn('HTTP 404', self.log_records[1].getMessage())

    def test_request_actor_includes_tenant(self):
        tenant = Tenant.objects.create(
            name='Acme',
            slug='acme',
            status=TenantStatus.ACTIVE,
        )
        request = self.factory.post('/api/signpdf-pfx')
        request.user = APIKeyUser(api_key=type('Key', (), {'prefix': 'abc'})(), tenant=tenant)
        self.assertEqual(request_actor(request), 'tenant:acme')
