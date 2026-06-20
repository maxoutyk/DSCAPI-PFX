import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agent import (
    OriginValidationError,
    add_allowed_origin,
    list_extra_allowed_origins,
    normalize_origin,
    portal_origin_from_config,
    remove_allowed_origin,
)


class AgentOriginsTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.config_path = Path(self._tmpdir.name) / 'config.json'
        self._patch = mock.patch('agent.CONFIG_PATH', self.config_path)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self._tmpdir.cleanup()

    def _write_config(self, data: dict):
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(data))

    def test_normalize_origin(self):
        self.assertEqual(
            normalize_origin('https://businesscentral.dynamics.com/'),
            'https://businesscentral.dynamics.com',
        )

    def test_normalize_origin_rejects_path(self):
        with self.assertRaises(OriginValidationError):
            normalize_origin('https://example.com/app')

    def test_add_and_remove_allowed_origin(self):
        self._write_config({'api_base': 'https://sign.example.com', 'device_token': 'x'})
        extras = add_allowed_origin('https://businesscentral.dynamics.com')
        self.assertEqual(extras, ['https://businesscentral.dynamics.com'])
        self.assertEqual(
            list_extra_allowed_origins(),
            ['https://businesscentral.dynamics.com'],
        )
        extras = remove_allowed_origin('https://businesscentral.dynamics.com')
        self.assertEqual(extras, [])

    def test_add_duplicate_portal_origin_rejected(self):
        self._write_config({'api_base': 'https://sign.example.com'})
        with self.assertRaises(OriginValidationError):
            add_allowed_origin('https://sign.example.com')

    def test_portal_origin_from_config(self):
        self._write_config({'api_base': 'https://sign.example.com/dashboard/'})
        self.assertEqual(portal_origin_from_config(), 'https://sign.example.com')


if __name__ == '__main__':
    unittest.main()
