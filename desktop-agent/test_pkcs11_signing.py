import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

AGENT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(AGENT_DIR))

from pkcs11_signing import _pkcs11_bytes, _pkcs11_text, resolve_pkcs11_dll  # noqa: E402


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


if __name__ == '__main__':
    unittest.main()
