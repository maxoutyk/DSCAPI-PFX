import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

AGENT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(AGENT_DIR))

from app_ui_helpers import humanize_agent_error  # noqa: E402


class HumanizeAgentErrorTests(unittest.TestCase):
    def test_empty_returns_network_message(self):
        self.assertIn('network', humanize_agent_error('').lower())

    def test_json_detail_extracted(self):
        payload = json.dumps({'detail': 'Invalid pairing code'})
        self.assertEqual(humanize_agent_error(payload), 'Invalid pairing code')

    def test_revoked_message(self):
        self.assertIn('revoked', humanize_agent_error('Device token revoked').lower())

    def test_truncates_long_text(self):
        long_text = 'x' * 200
        self.assertTrue(len(humanize_agent_error(long_text)) <= 140)


if __name__ == '__main__':
    unittest.main()
