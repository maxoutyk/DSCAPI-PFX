import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

AGENT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(AGENT_DIR))

from pkcs11_signing import (  # noqa: E402
    PinCancelledError,
    TokenDescriptor,
    _pkcs11_bytes,
    _pkcs11_text,
    _record_session_pin,
    clear_session_pin,
    ensure_pin_cache_valid,
    format_token_display,
    get_pin_cache_settings,
    match_saved_token,
    pin_cache_env_locked,
    pin_cache_managed_by_env,
    prompt_token_pin,
    resolve_pkcs11_dll,
    resolve_signing_slot_from_tokens,
    save_pin_cache_settings,
)


class Pkcs11AttributeTests(unittest.TestCase):
    def test_pkcs11_bytes_accepts_string(self):
        self.assertEqual(_pkcs11_bytes('abc'), b'abc')

    def test_pkcs11_bytes_accepts_int_list(self):
        self.assertEqual(_pkcs11_bytes([65, 66]), b'AB')

    def test_pkcs11_text_strips_null_padding(self):
        self.assertEqual(_pkcs11_text('signer\x00pad'), 'signer')


class Pkcs11DiscoveryTests(unittest.TestCase):
    def test_resolve_pkcs11_dll_honours_env_override(self):
        with patch.dict(os.environ, {'IG_AGENT_PKCS11_DLL': __file__}, clear=False):
            self.assertEqual(resolve_pkcs11_dll(), __file__)

    def test_resolve_pkcs11_dll_returns_none_when_unavailable(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch('pkcs11_signing.sys.platform', 'darwin'):
                with patch('pkcs11_signing.WINDOWS_PKCS11_DLL_CANDIDATES', ()):
                    self.assertIsNone(resolve_pkcs11_dll())


def _sample_tokens() -> list[TokenDescriptor]:
    return [
        TokenDescriptor(0, 'ePass2003', 'AAA111', 'Alice Signer'),
        TokenDescriptor(1, 'ePass2003', 'BBB222', 'Bob Signer'),
    ]


class TokenSelectionTests(unittest.TestCase):
    def test_format_token_display_shows_label_and_signer(self):
        token = _sample_tokens()[0]
        display = format_token_display(token)
        self.assertEqual(display, 'ePass2003 · Alice Signer')
        self.assertNotIn('Slot', display)
        self.assertNotIn('SN', display)

    def test_match_saved_token_prefers_slot_id(self):
        tokens = _sample_tokens()
        matched = match_saved_token(tokens, {'token_slot_id': 1, 'token_serial': 'AAA111'})
        self.assertEqual(matched.slot_id, 1)

    def test_match_saved_token_uses_serial_when_slot_missing(self):
        tokens = _sample_tokens()
        matched = match_saved_token(
            tokens,
            {'token_slot_id': None, 'token_serial': 'BBB222', 'token_label': 'ePass2003'},
        )
        self.assertEqual(matched.slot_id, 1)

    def test_resolve_signing_slot_auto_picks_single_token(self):
        token = _sample_tokens()[0]
        slot_id = resolve_signing_slot_from_tokens([token], allow_prompt=False)
        self.assertEqual(slot_id, 0)

    def test_resolve_signing_slot_uses_saved_preference(self):
        tokens = _sample_tokens()
        slot_id = resolve_signing_slot_from_tokens(
            tokens,
            preference={'token_slot_id': 1, 'token_serial': '', 'token_label': ''},
            allow_prompt=False,
        )
        self.assertEqual(slot_id, 1)

    def test_resolve_signing_slot_requires_choice_when_ambiguous(self):
        tokens = _sample_tokens()
        with self.assertRaises(RuntimeError):
            resolve_signing_slot_from_tokens(tokens, allow_prompt=False)


class PinPromptTests(unittest.TestCase):
    def test_prompt_token_pin_raises_when_user_cancels_on_main_thread(self):
        import threading

        import pkcs11_signing as module

        class FakeRoot:
            def after(self, _delay, callback):
                callback()

        done = threading.Event()

        def fake_prompt(*_args, **_kwargs):
            done.set()
            return ''

        module.clear_session_pin()
        with patch.object(module, '_main_ui_root', FakeRoot()):
            with patch.object(module.sys, 'platform', 'win32'):
                with patch('tkinter.simpledialog.askstring', fake_prompt):
                    with self.assertRaises(PinCancelledError):
                        module.prompt_token_pin()
        self.assertTrue(done.is_set())


class PinCacheTests(unittest.TestCase):
    def setUp(self):
        clear_session_pin()
        self._config_path = AGENT_DIR / '.test-pin-cache-config.json'

    def tearDown(self):
        clear_session_pin()
        if self._config_path.exists():
            self._config_path.unlink()

    def test_get_pin_cache_settings_defaults(self):
        with patch('pkcs11_signing.CONFIG_PATH', self._config_path):
            with patch.dict(os.environ, {}, clear=True):
                settings = get_pin_cache_settings()
        self.assertTrue(settings['enabled'])
        self.assertEqual(settings['hours'], 6.0)
        self.assertTrue(settings['clear_on_disconnect'])

    def test_env_overrides_pin_cache_settings(self):
        with patch('pkcs11_signing.CONFIG_PATH', self._config_path):
            with patch.dict(
                os.environ,
                {
                    'IG_AGENT_PIN_CACHE_ENABLED': '0',
                    'IG_AGENT_PIN_CACHE_HOURS': '12',
                    'IG_AGENT_PIN_CLEAR_ON_DISCONNECT': 'false',
                },
                clear=False,
            ):
                settings = get_pin_cache_settings()
        self.assertFalse(settings['enabled'])
        self.assertEqual(settings['hours'], 12.0)
        self.assertFalse(settings['clear_on_disconnect'])

    def test_pin_cache_env_locked_flags(self):
        with patch.dict(os.environ, {'IG_AGENT_PIN_CACHE_HOURS': '8'}, clear=False):
            locked = pin_cache_env_locked()
            self.assertFalse(locked['enabled'])
            self.assertTrue(locked['hours'])
            self.assertTrue(pin_cache_managed_by_env())

    def test_prompt_token_pin_reuses_cached_pin(self):
        import pkcs11_signing as module

        module.clear_session_pin()
        module._record_session_pin('1234')
        with patch.object(module, 'ensure_pin_cache_valid'):
            self.assertEqual(module.prompt_token_pin(), '1234')

    def test_ensure_pin_cache_valid_clears_when_disabled(self):
        import pkcs11_signing as module

        with patch('pkcs11_signing.CONFIG_PATH', self._config_path):
            save_pin_cache_settings(enabled=False, hours=6, clear_on_disconnect=True)
            module._record_session_pin('1234')
            ensure_pin_cache_valid()
            self.assertIsNone(module._session_pin)

    def test_ensure_pin_cache_valid_clears_on_token_disconnect(self):
        import pkcs11_signing as module

        with patch('pkcs11_signing.CONFIG_PATH', self._config_path):
            save_pin_cache_settings(enabled=True, hours=6, clear_on_disconnect=True)
            module._record_session_pin('1234', slot_id=0)
            module._pin_cache_fingerprint = (0, 'AAA111')
            with patch('pkcs11_signing.token_slot_present', return_value=False):
                ensure_pin_cache_valid()
            self.assertIsNone(module._session_pin)

    def test_ensure_pin_cache_valid_clears_after_ttl(self):
        import pkcs11_signing as module

        with patch('pkcs11_signing.CONFIG_PATH', self._config_path):
            save_pin_cache_settings(enabled=True, hours=1, clear_on_disconnect=False)
            module._record_session_pin('1234')
            module._pin_cache_fingerprint = (0, 'AAA111')
            module._pin_cached_at = 0.0
            with patch('pkcs11_signing.time.monotonic', return_value=4000.0):
                ensure_pin_cache_valid()
            self.assertIsNone(module._session_pin)


if __name__ == '__main__':
    unittest.main()
