import sys
import unittest
from pathlib import Path
from unittest.mock import patch

AGENT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(AGENT_DIR))

from agent import (  # noqa: E402
    AGENT_VERSION,
    compare_agent_versions,
    fetch_latest_agent_version,
    is_agent_update_available,
    refresh_agent_update_state,
)
from tray import AgentRuntimeState  # noqa: E402


class AgentVersionTests(unittest.TestCase):
    def test_compare_agent_versions(self):
        self.assertEqual(compare_agent_versions('0.2.9', '0.3.0'), -1)
        self.assertEqual(compare_agent_versions('0.3.0', '0.3.0'), 0)
        self.assertEqual(compare_agent_versions('1.0.0', '0.9.9'), 1)
        self.assertEqual(compare_agent_versions('0.2.10', '0.2.9'), 1)

    def test_is_agent_update_available(self):
        self.assertTrue(is_agent_update_available('0.2.9', '0.3.0'))
        self.assertFalse(is_agent_update_available('0.3.0', '0.3.0'))
        self.assertFalse(is_agent_update_available('0.3.0', ''))

    @patch('agent.api_request')
    def test_fetch_latest_agent_version(self, mock_api_request):
        mock_api_request.return_value = {'version': '0.3.0'}
        self.assertEqual(fetch_latest_agent_version('https://sign.example.com'), '0.3.0')
        mock_api_request.assert_called_once_with('GET', 'https://sign.example.com/api/agent/version/')

    @patch('agent.fetch_latest_agent_version')
    def test_refresh_agent_update_state(self, mock_fetch):
        state = AgentRuntimeState()
        mock_fetch.return_value = '9.9.9'
        refresh_agent_update_state(state, 'https://sign.example.com')
        snap = state.snapshot()
        self.assertEqual(snap['latest_agent_version'], '9.9.9')
        self.assertTrue(snap['update_available'])

        mock_fetch.return_value = AGENT_VERSION
        refresh_agent_update_state(state, 'https://sign.example.com')
        snap = state.snapshot()
        self.assertFalse(snap['update_available'])


if __name__ == '__main__':
    unittest.main()
