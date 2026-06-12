"""PKCS#11 USB DSC token signing for the IG E-Sign desktop agent."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

CONFIG_PATH = Path.home() / '.ig-esign-agent' / 'config.json'

# Common Windows PKCS#11 drivers for Indian DSC tokens (eMudhra, Watchdata, etc.)
WINDOWS_PKCS11_DLL_CANDIDATES = (
    r'C:\Windows\System32\eps2003csp11.dll',
    r'C:\Windows\System32\eps2003csp11_s.dll',
    r'C:\Windows\System32\wdpkcs.dll',
    r'C:\Windows\System32\IDPrimePKCS11.dll',
    r'C:\Windows\System32\aetpkss1.dll',
    r'C:\Windows\System32\eTPKCS11.dll',
    r'C:\Windows\System32\ngp11v211.dll',
    r'C:\Windows\System32\SignatureP11.dll',
)

_session_pin: str | None = None


def load_agent_config() -> dict:
    if not CONFIG_PATH.is_file():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text())
    except json.JSONDecodeError:
        return {}


def resolve_pkcs11_dll() -> str | None:
    for source in (
        os.environ.get('IG_AGENT_PKCS11_DLL', '').strip(),
        load_agent_config().get('pkcs11_dll', '').strip(),
    ):
        if source and Path(source).is_file():
            return source
    if sys.platform == 'win32':
        for candidate in WINDOWS_PKCS11_DLL_CANDIDATES:
            if Path(candidate).is_file():
                return candidate
    return None


def token_slot_present(dll_path: str | None = None) -> bool:
    dll_path = dll_path or resolve_pkcs11_dll()
    if not dll_path:
        return False
    try:
        import PyKCS11

        lib = PyKCS11.PyKCS11Lib()
        lib.load(dll_path)
        return bool(lib.getSlotList(tokenPresent=True))
    except Exception:
        return False


def prompt_token_pin(*, title: str = 'IG E-Sign Agent') -> str:
    global _session_pin
    if _session_pin:
        return _session_pin

    message = 'Enter your USB DSC token PIN to sign this document.'
    if sys.platform == 'win32':
        try:
            import tkinter as tk
            from tkinter import simpledialog

            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            pin = simpledialog.askstring(title, message, show='*')
            root.destroy()
            if pin:
                _session_pin = pin
                return pin
        except Exception:
            pass

    import getpass

    pin = getpass.getpass(f'{title}: {message}\nPIN: ')
    if pin:
        _session_pin = pin
    return pin


def clear_session_pin():
    global _session_pin
    _session_pin = None


class TokenSigner:
    """endesive HSM-compatible signer backed by a PKCS#11 USB token."""

    def __init__(
        self,
        dll_path: str,
        *,
        token_label: str | None = None,
        pin: str | None = None,
        cert_key_id: bytes | None = None,
    ):
        from endesive import hsm

        self._base = hsm.HSM(dll_path)
        self.pkcs11 = self._base.pkcs11
        self.session = None
        self.token_label = token_label
        self._pin = pin
        self._cert_key_id = cert_key_id
        self._keyid: bytes | None = None
        self._cert_der: bytes | None = None

    def logout(self):
        self._base.logout()
        self.session = None

    def _resolve_token_label(self) -> str:
        if self.token_label:
            return self.token_label
        config_label = load_agent_config().get('token_label', '').strip()
        if config_label:
            return config_label
        slots = self.pkcs11.getSlotList(tokenPresent=True)
        if not slots:
            raise RuntimeError(
                'No USB token detected. Insert your DSC token and try again.',
            )
        info = self.pkcs11.getTokenInfo(slots[0])
        return info.label.split('\0')[0].strip()

    def _ensure_logged_in(self):
        import PyKCS11 as PK11

        if self.session is not None:
            return
        label = self._resolve_token_label()
        pin = self._pin or prompt_token_pin()
        if not pin:
            raise RuntimeError('Token PIN is required to sign.')
        self._base.login(label, pin)
        self.session = self._base.session

    def _find_signing_pairs(self) -> list[tuple[bytes, bytes, str]]:
        import PyKCS11 as PK11

        assert self.session is not None
        pairs: list[tuple[bytes, bytes, str]] = []
        cert_objects = self.session.findObjects([(PK11.CKA_CLASS, PK11.CKO_CERTIFICATE)])
        for cert_obj in cert_objects:
            try:
                value, key_id, label = self.session.getAttributeValue(
                    cert_obj,
                    [PK11.CKA_VALUE, PK11.CKA_ID, PK11.CKA_LABEL],
                )
            except PK11.PyKCS11Error:
                continue
            key_id_bytes = bytes(key_id)
            private_keys = self.session.findObjects(
                [
                    (PK11.CKA_CLASS, PK11.CKO_PRIVATE_KEY),
                    (PK11.CKA_ID, key_id_bytes),
                ],
            )
            if not private_keys:
                continue
            label_text = bytes(label).decode('utf-8', errors='replace').split('\0')[0].strip()
            pairs.append((key_id_bytes, bytes(value), label_text))
        return pairs

    def _select_pair(self) -> tuple[bytes, bytes]:
        if self._keyid is not None and self._cert_der is not None:
            return self._keyid, self._cert_der

        pairs = self._find_signing_pairs()
        if not pairs:
            raise RuntimeError('No signing certificate found on the USB token.')

        preferred = self._cert_key_id
        if preferred is None:
            config_hex = load_agent_config().get('cert_key_id_hex', '').strip()
            if config_hex:
                preferred = bytes.fromhex(config_hex)

        if preferred is not None:
            for key_id, cert_der, _label in pairs:
                if key_id == preferred:
                    self._keyid, self._cert_der = key_id, cert_der
                    return key_id, cert_der

        if len(pairs) == 1:
            key_id, cert_der, _label = pairs[0]
        else:
            key_id, cert_der, _label = max(pairs, key=lambda item: len(item[1]))

        self._keyid, self._cert_der = key_id, cert_der
        return key_id, cert_der

    def certificate(self):
        self._ensure_logged_in()
        key_id, cert_der = self._select_pair()
        return key_id, cert_der

    def sign(self, keyid, data, mech):
        import PyKCS11 as PK11

        self._ensure_logged_in()
        assert self.session is not None
        private_keys = self.session.findObjects(
            [
                (PK11.CKA_CLASS, PK11.CKO_PRIVATE_KEY),
                (PK11.CKA_ID, keyid),
            ],
        )
        if not private_keys:
            raise RuntimeError('Private key for the selected certificate was not found on the token.')
        mechanism_name = f'CKM_{mech.upper()}_RSA_PKCS'
        mechanism = getattr(PK11, mechanism_name, None)
        if mechanism is None:
            raise RuntimeError(f'Unsupported signing mechanism: {mech}')
        signature = self.session.sign(
            private_keys[0],
            data,
            PK11.Mechanism(mechanism, None),
        )
        return bytes(signature)
