import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

AGENT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(AGENT_DIR))

from pkcs11_signing import (  # noqa: E402
    TokenDescriptor,
    _pkcs11_bytes,
    _pkcs11_text,
    format_token_display,
    match_saved_token,
    resolve_pkcs11_dll,
    resolve_signing_slot_from_tokens,
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
        TokenDescriptor(0, 'ePass2003', 'AAA111', 'Watchdata', ('Alice Signer',)),
        TokenDescriptor(1, 'ePass2003', 'BBB222', 'Watchdata', ('Bob Signer',)),
    ]


class TokenSelectionTests(unittest.TestCase):
    def test_format_token_display_includes_slot_serial_and_subject(self):
        token = _sample_tokens()[0]
        display = format_token_display(token)
        self.assertIn('Slot 0', display)
        self.assertIn('ePass2003', display)
        self.assertIn('SN AAA111', display)
        self.assertIn('Alice Signer', display)

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


if __name__ == '__main__':
    unittest.main()
