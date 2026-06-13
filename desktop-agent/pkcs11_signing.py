"""PKCS#11 USB DSC token signing for the IG E-Sign desktop agent."""

from __future__ import annotations

import json
import os
import queue
import sys
import threading
import time
from dataclasses import dataclass
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
_session_slot_id: int | None = None
_pin_ui_in: queue.Queue | None = None
_pin_ui_out: queue.Queue | None = None
_main_ui_root = None


_TOKEN_CACHE_LOCK = threading.Lock()
_TOKEN_CACHE: tuple[float, list['TokenDescriptor']] | None = None
_TOKEN_CACHE_TTL_SECONDS = 15
_SIGNER_PROBE_TIMEOUT_SECONDS = 4


@dataclass(frozen=True)
class TokenDescriptor:
    slot_id: int
    label: str
    serial: str
    signer_name: str = ''

    def display_name(self) -> str:
        return format_token_display(self)


def register_main_ui_root(root) -> None:
    """Use the dashboard Tk root for PIN prompts on the main thread."""
    global _main_ui_root
    _main_ui_root = root


def unregister_main_ui_root() -> None:
    global _main_ui_root
    _main_ui_root = None


def _prompt_pin_on_main_thread(root, *, title: str, message: str) -> str:
    result_queue: queue.Queue[str] = queue.Queue(maxsize=1)
    done = threading.Event()

    def show():
        from tkinter import simpledialog

        try:
            pin = simpledialog.askstring(title, message, show='*', parent=root)
            result_queue.put(pin or '')
        except Exception:
            result_queue.put('')
        finally:
            done.set()

    root.after(0, show)
    if not done.wait(timeout=300):
        return ''
    try:
        return result_queue.get_nowait()
    except queue.Empty:
        return ''


def _pkcs11_bytes(value) -> bytes:
    """Normalize PKCS#11 attribute values to bytes."""
    if value is None:
        return b''
    if isinstance(value, bytes):
        return value
    if isinstance(value, bytearray):
        return bytes(value)
    if isinstance(value, str):
        return value.encode('latin1')
    if isinstance(value, (list, tuple)):
        return bytes(bytearray(value))
    return bytes(value)


def _pkcs11_text(value) -> str:
    return _pkcs11_bytes(value).decode('utf-8', errors='replace').split('\0')[0].strip()


def load_agent_config() -> dict:
    if not CONFIG_PATH.is_file():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text())
    except json.JSONDecodeError:
        return {}


def save_agent_config(data: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(data, indent=2))


def format_token_display(token: TokenDescriptor) -> str:
    label = token.label or 'USB token'
    if token.signer_name:
        return f'{label} · {token.signer_name}'
    return label


def saved_token_display() -> str:
    pref = get_token_preference()
    label = pref.get('token_label', '')
    signer = pref.get('signer_name', '')
    if label and signer:
        return f'{label} · {signer}'
    return label or signer or ''


def invalidate_token_cache() -> None:
    global _TOKEN_CACHE
    with _TOKEN_CACHE_LOCK:
        _TOKEN_CACHE = None


def get_token_preference() -> dict:
    config = load_agent_config()
    slot_id = config.get('token_slot_id')
    return {
        'token_slot_id': int(slot_id) if slot_id is not None else None,
        'token_serial': str(config.get('token_serial', '') or '').strip(),
        'token_label': str(config.get('token_label', '') or '').strip(),
        'signer_name': str(config.get('signer_name', '') or '').strip(),
        'cert_key_id_hex': str(config.get('cert_key_id_hex', '') or '').strip(),
    }


def save_token_preference(
    slot_id: int,
    *,
    label: str = '',
    serial: str = '',
    signer_name: str = '',
    cert_key_id_hex: str = '',
) -> None:
    config = load_agent_config()
    config['token_slot_id'] = int(slot_id)
    if label:
        config['token_label'] = label
    if serial:
        config['token_serial'] = serial
    if signer_name:
        config['signer_name'] = signer_name
    if cert_key_id_hex:
        config['cert_key_id_hex'] = cert_key_id_hex
    save_agent_config(config)
    invalidate_token_cache()


def match_saved_token(tokens: list[TokenDescriptor], preference: dict | None = None) -> TokenDescriptor | None:
    if not tokens:
        return None
    pref = preference or get_token_preference()
    saved_slot = pref.get('token_slot_id')
    if saved_slot is not None:
        for token in tokens:
            if token.slot_id == saved_slot:
                return token
    saved_serial = pref.get('token_serial', '')
    saved_label = pref.get('token_label', '')
    if saved_serial:
        for token in tokens:
            if token.serial == saved_serial and (not saved_label or token.label == saved_label):
                return token
    return None


def resolve_signing_slot_from_tokens(
    tokens: list[TokenDescriptor],
    *,
    preference: dict | None = None,
    allow_prompt: bool = False,
    prompt_fn=None,
) -> int:
    if not tokens:
        raise RuntimeError('No USB token detected. Insert your DSC token and try again.')
    if len(tokens) == 1:
        return tokens[0].slot_id
    matched = match_saved_token(tokens, preference)
    if matched is not None:
        return matched.slot_id
    if allow_prompt and prompt_fn is not None:
        slot_id = prompt_fn(tokens)
        if slot_id is not None:
            chosen = next((token for token in tokens if token.slot_id == slot_id), None)
            if chosen is not None:
                save_token_preference(
                    chosen.slot_id,
                    label=chosen.label,
                    serial=chosen.serial,
                    signer_name=chosen.signer_name,
                )
            return slot_id
    raise RuntimeError(
        'Multiple USB tokens detected. Open the IG E-Sign Agent window, choose a token under '
        '"USB signing token", and click "Use for signing".',
    )


def _probe_signer_name_inner(pkcs11, slot_id: int) -> str:
    import PyKCS11 as PK11

    session = None
    try:
        session = pkcs11.openSession(slot_id, PK11.CKF_SERIAL_SESSION)
        cert_objects = session.findObjects([(PK11.CKA_CLASS, PK11.CKO_CERTIFICATE)])
        candidates: list[tuple[int, str]] = []
        for cert_obj in cert_objects:
            try:
                key_id, cert_label = session.getAttributeValue(
                    cert_obj,
                    [PK11.CKA_ID, PK11.CKA_LABEL],
                )
            except PK11.PyKCS11Error:
                continue
            private_keys = session.findObjects(
                [
                    (PK11.CKA_CLASS, PK11.CKO_PRIVATE_KEY),
                    (PK11.CKA_ID, key_id),
                ],
            )
            if not private_keys:
                continue
            name = _pkcs11_text(cert_label)
            if name:
                candidates.append((len(name), name))
        if not candidates:
            return ''
        return max(candidates, key=lambda item: item[0])[1]
    except Exception:
        return ''
    finally:
        if session is not None:
            try:
                session.closeSession()
            except Exception:
                pass


def _probe_signer_name(pkcs11, slot_id: int) -> str:
    result: list[str] = ['']
    done = threading.Event()

    def worker():
        try:
            result[0] = _probe_signer_name_inner(pkcs11, slot_id)
        finally:
            done.set()

    threading.Thread(target=worker, daemon=True, name=f'ig-agent-signer-probe-{slot_id}').start()
    if not done.wait(timeout=_SIGNER_PROBE_TIMEOUT_SECONDS):
        return ''
    return result[0]


def _list_usb_tokens_fast(dll_path: str | None = None) -> list[TokenDescriptor]:
    dll_path = dll_path or resolve_pkcs11_dll()
    if not dll_path:
        return []
    try:
        import PyKCS11

        lib = PyKCS11.PyKCS11Lib()
        lib.load(dll_path)
        tokens: list[TokenDescriptor] = []
        for slot_id in lib.getSlotList(tokenPresent=True):
            info = lib.getTokenInfo(slot_id)
            tokens.append(
                TokenDescriptor(
                    slot_id=int(slot_id),
                    label=_pkcs11_text(info.label),
                    serial=_pkcs11_text(info.serialNumber),
                ),
            )
        return tokens
    except Exception:
        return []


def _attach_signer_names(pkcs11, tokens: list[TokenDescriptor]) -> list[TokenDescriptor]:
    enriched: list[TokenDescriptor] = []
    for token in tokens:
        signer_name = _probe_signer_name(pkcs11, token.slot_id)
        enriched.append(
            TokenDescriptor(
                slot_id=token.slot_id,
                label=token.label,
                serial=token.serial,
                signer_name=signer_name,
            ),
        )
    return enriched


def list_usb_tokens(
    dll_path: str | None = None,
    *,
    include_signer: bool = False,
    use_cache: bool = True,
) -> list[TokenDescriptor]:
    global _TOKEN_CACHE
    now = time.monotonic()
    if use_cache:
        with _TOKEN_CACHE_LOCK:
            cached = _TOKEN_CACHE
            if cached is not None and (now - cached[0]) < _TOKEN_CACHE_TTL_SECONDS:
                tokens = cached[1]
                if not include_signer:
                    return [
                        TokenDescriptor(token.slot_id, token.label, token.serial, '')
                        for token in tokens
                    ]
                return list(tokens)

    dll_path = dll_path or resolve_pkcs11_dll()
    if not dll_path:
        return []

    tokens = _list_usb_tokens_fast(dll_path)
    if include_signer and tokens:
        try:
            import PyKCS11

            lib = PyKCS11.PyKCS11Lib()
            lib.load(dll_path)
            tokens = _attach_signer_names(lib, tokens)
        except Exception:
            pass

    if use_cache:
        with _TOKEN_CACHE_LOCK:
            _TOKEN_CACHE = (now, list(tokens))

    if not include_signer:
        return [TokenDescriptor(token.slot_id, token.label, token.serial, '') for token in tokens]
    return tokens


def refresh_usb_tokens(dll_path: str | None = None) -> list[TokenDescriptor]:
    invalidate_token_cache()
    return list_usb_tokens(dll_path, include_signer=True, use_cache=True)


def selected_token_summary(dll_path: str | None = None) -> dict:
    tokens = list_usb_tokens(dll_path, include_signer=False, use_cache=True)
    display = saved_token_display()
    if not display:
        matched = match_saved_token(tokens)
        if matched is not None:
            display = matched.display_name()
    return {
        'token_count': len(tokens),
        'selected_token_display': display,
    }


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


def ensure_pin_ui_thread() -> None:
    """Fallback Tk thread for PIN prompts when no dashboard root is registered."""
    global _pin_ui_in, _pin_ui_out
    if sys.platform != 'win32' or _main_ui_root is not None or (_pin_ui_in is not None and _pin_ui_out is not None):
        return

    q_in: queue.Queue = queue.Queue()
    q_out: queue.Queue = queue.Queue()

    def worker():
        import tkinter as tk
        from tkinter import simpledialog

        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        while True:
            item = q_in.get()
            if item is None:
                root.destroy()
                break
            title, message = item
            pin = simpledialog.askstring(title, message, show='*', parent=root)
            q_out.put(pin or '')

    threading.Thread(target=worker, daemon=True, name='ig-agent-pin-ui').start()
    _pin_ui_in = q_in
    _pin_ui_out = q_out


def prompt_token_pin(*, title: str = 'IG E-Sign Agent') -> str:
    global _session_pin
    if _session_pin:
        return _session_pin

    message = 'Enter your USB DSC token PIN to sign this document.'
    if sys.platform == 'win32':
        root = _main_ui_root
        if root is not None:
            try:
                pin = _prompt_pin_on_main_thread(root, title=title, message=message)
            except Exception:
                pin = ''
            if pin:
                _session_pin = pin
                return pin

        ensure_pin_ui_thread()
        if _pin_ui_in is not None and _pin_ui_out is not None:
            _pin_ui_in.put((title, message))
            try:
                pin = _pin_ui_out.get(timeout=300)
            except queue.Empty:
                pin = ''
            if pin:
                _session_pin = pin
                return pin

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
    global _session_pin, _session_slot_id
    _session_pin = None
    _session_slot_id = None


def _prompt_token_choice_on_main_thread(root, tokens: list[TokenDescriptor]) -> int | None:
    result_queue: queue.Queue[int | None] = queue.Queue(maxsize=1)
    done = threading.Event()

    def show():
        import tkinter as tk
        from tkinter import ttk

        dialog = tk.Toplevel(root)
        dialog.title('Select USB token')
        dialog.geometry('460x300')
        dialog.minsize(400, 260)
        dialog.transient(root)
        dialog.grab_set()

        frame = ttk.Frame(dialog, padding=12)
        frame.pack(fill='both', expand=True)

        ttk.Label(
            frame,
            text='Multiple USB tokens detected. Choose which token to use for signing:',
            wraplength=400,
        ).pack(anchor='w')

        listbox = tk.Listbox(frame, height=min(8, max(3, len(tokens))), exportselection=False)
        for token in tokens:
            listbox.insert('end', format_token_display(token))
        listbox.selection_set(0)
        listbox.pack(fill='both', expand=True, pady=(10, 10))

        def accept():
            selection = listbox.curselection()
            if not selection:
                result_queue.put(None)
            else:
                result_queue.put(tokens[selection[0]].slot_id)
            done.set()
            dialog.destroy()

        def cancel():
            result_queue.put(None)
            done.set()
            dialog.destroy()

        buttons = ttk.Frame(frame)
        ttk.Button(buttons, text='Use this token', command=accept).pack(side='left')
        ttk.Button(buttons, text='Cancel', command=cancel).pack(side='left', padx=(8, 0))
        buttons.pack(anchor='w')
        dialog.protocol('WM_DELETE_WINDOW', cancel)
        listbox.bind('<Double-Button-1>', lambda _event: accept())
        listbox.focus_set()

    root.after(0, show)
    if not done.wait(timeout=300):
        return None
    try:
        return result_queue.get_nowait()
    except queue.Empty:
        return None


def prompt_token_choice(tokens: list[TokenDescriptor]) -> int | None:
    if not tokens:
        return None
    if len(tokens) == 1:
        return tokens[0].slot_id

    root = _main_ui_root
    if root is not None:
        try:
            return _prompt_token_choice_on_main_thread(root, tokens)
        except Exception:
            pass

    ensure_pin_ui_thread()

    if sys.platform == 'win32':
        try:
            import tkinter as tk
            from tkinter import ttk

            result: dict[str, int | None] = {'slot_id': None}
            picker_root = tk.Tk()
            picker_root.withdraw()
            picker_root.attributes('-topmost', True)

            dialog = tk.Toplevel(picker_root)
            dialog.title('Select USB token')
            dialog.geometry('460x300')
            dialog.attributes('-topmost', True)

            frame = ttk.Frame(dialog, padding=12)
            frame.pack(fill='both', expand=True)
            ttk.Label(
                frame,
                text='Multiple USB tokens detected. Choose which token to use for signing:',
                wraplength=400,
            ).pack(anchor='w')

            listbox = tk.Listbox(frame, height=min(8, max(3, len(tokens))), exportselection=False)
            for token in tokens:
                listbox.insert('end', format_token_display(token))
            listbox.selection_set(0)
            listbox.pack(fill='both', expand=True, pady=(10, 10))

            def accept():
                selection = listbox.curselection()
                if selection:
                    result['slot_id'] = tokens[selection[0]].slot_id
                dialog.destroy()
                picker_root.destroy()

            def cancel():
                dialog.destroy()
                picker_root.destroy()

            buttons = ttk.Frame(frame)
            ttk.Button(buttons, text='Use this token', command=accept).pack(side='left')
            ttk.Button(buttons, text='Cancel', command=cancel).pack(side='left', padx=(8, 0))
            buttons.pack(anchor='w')
            dialog.protocol('WM_DELETE_WINDOW', cancel)
            picker_root.wait_window(dialog)
            return result['slot_id']
        except Exception:
            pass

    return None


class TokenSigner:
    """endesive HSM-compatible signer backed by a PKCS#11 USB token."""

    def __init__(
        self,
        dll_path: str,
        *,
        token_label: str | None = None,
        slot_id: int | None = None,
        pin: str | None = None,
        cert_key_id: bytes | None = None,
    ):
        from endesive import hsm

        self._base = hsm.HSM(dll_path)
        self.pkcs11 = self._base.pkcs11
        self.session = None
        self.token_label = token_label
        self._slot_id = slot_id
        self._pin = pin
        self._cert_key_id = cert_key_id
        self._keyid = None
        self._cert_der: bytes | None = None

    def logout(self):
        if self.session is not None:
            try:
                self.session.logout()
            except Exception:
                pass
            try:
                self.session.closeSession()
            except Exception:
                pass
        self._base.logout()
        self.session = None

    def _resolve_signing_slot(self) -> int:
        global _session_slot_id
        if self._slot_id is not None:
            return self._slot_id
        if _session_slot_id is not None:
            return _session_slot_id

        tokens = list_usb_tokens()
        slot_id = resolve_signing_slot_from_tokens(
            tokens,
            allow_prompt=True,
            prompt_fn=prompt_token_choice,
        )
        _session_slot_id = slot_id
        self._slot_id = slot_id
        return slot_id

    def _login_slot(self, slot_id: int, pin: str):
        import PyKCS11 as PK11

        self.session = self.pkcs11.openSession(
            slot_id,
            PK11.CKF_SERIAL_SESSION | PK11.CKF_RW_SESSION,
        )
        self.session.login(pin)

    def _ensure_logged_in(self):
        if self.session is not None:
            return
        slot_id = self._resolve_signing_slot()
        pin = self._pin or prompt_token_pin()
        if not pin:
            raise RuntimeError('Token PIN is required to sign.')
        self._login_slot(slot_id, pin)

    def _find_signing_pairs(self) -> list[tuple[object, bytes, str]]:
        import PyKCS11 as PK11

        assert self.session is not None
        pairs: list[tuple[object, bytes, str]] = []
        cert_objects = self.session.findObjects([(PK11.CKA_CLASS, PK11.CKO_CERTIFICATE)])
        for cert_obj in cert_objects:
            try:
                value, key_id, label = self.session.getAttributeValue(
                    cert_obj,
                    [PK11.CKA_VALUE, PK11.CKA_ID, PK11.CKA_LABEL],
                )
            except PK11.PyKCS11Error:
                continue
            private_keys = self.session.findObjects(
                [
                    (PK11.CKA_CLASS, PK11.CKO_PRIVATE_KEY),
                    (PK11.CKA_ID, key_id),
                ],
            )
            if not private_keys:
                continue
            pairs.append((key_id, _pkcs11_bytes(value), _pkcs11_text(label)))
        return pairs

    def _select_pair(self) -> tuple[object, bytes]:
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
                if _pkcs11_bytes(key_id) == _pkcs11_bytes(preferred):
                    self._keyid, self._cert_der = key_id, cert_der
                    return key_id, cert_der

        if len(pairs) == 1:
            key_id, cert_der, _label = pairs[0]
        else:
            key_id, cert_der, _label = max(pairs, key=lambda item: len(item[1]))

        self._keyid, self._cert_der = key_id, cert_der
        self._maybe_cache_signer_name(cert_der)
        return key_id, cert_der

    def _maybe_cache_signer_name(self, cert_der: bytes) -> None:
        try:
            from cryptography import x509
            from cryptography.x509.oid import NameOID

            cert = x509.load_der_x509_certificate(cert_der)
            attrs = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
            signer_name = str(attrs[0].value) if attrs else ''
            if not signer_name or self._slot_id is None:
                return
            pref = get_token_preference()
            if pref.get('signer_name') == signer_name:
                return
            save_token_preference(
                self._slot_id,
                label=pref.get('token_label', '') or self.token_label or '',
                serial=pref.get('token_serial', ''),
                signer_name=signer_name,
                cert_key_id_hex=pref.get('cert_key_id_hex', ''),
            )
        except Exception:
            pass

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
        sign_data = _pkcs11_bytes(data) if isinstance(data, str) else data
        if not isinstance(sign_data, (bytes, bytearray)):
            sign_data = bytes(sign_data)
        signature = self.session.sign(
            private_keys[0],
            sign_data,
            PK11.Mechanism(mechanism, None),
        )
        return bytes(signature)
