import hashlib
import re
from dataclasses import dataclass

from django.contrib.auth.models import User

from accounts.models import APIKey

_MAC_RE = re.compile(r'^([0-9A-F]{2}[:-]){5}([0-9A-F]{2})$')
_USER_AGENT_MAX_LEN = 512


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


_LOOPBACK_IPS = frozenset({'127.0.0.1', '::1'})


def _first_usable_ip(*candidates: str | None) -> str | None:
    for candidate in candidates:
        if not candidate:
            continue
        ip = candidate.strip()
        if ip and ip not in _LOOPBACK_IPS:
            return ip
    return None


def get_client_ip(request) -> str | None:
    """Resolve client IP; honor X-Forwarded-For only when TRUSTED_PROXY_COUNT is set."""
    from django.conf import settings

    trusted_hops = int(getattr(settings, 'TRUSTED_PROXY_COUNT', 0) or 0)
    if trusted_hops > 0:
        forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if forwarded_for:
            forwarded_ips = [part.strip() for part in forwarded_for.split(',') if part.strip()]
            if len(forwarded_ips) >= trusted_hops:
                candidate = forwarded_ips[-trusted_hops]
                if candidate and candidate not in _LOOPBACK_IPS:
                    return candidate

        x_real_ip = request.META.get('HTTP_X_REAL_IP')
        if x_real_ip:
            ip = x_real_ip.strip()
            if ip and ip not in _LOOPBACK_IPS:
                return ip

    remote_addr = request.META.get('REMOTE_ADDR')
    if remote_addr:
        return remote_addr.strip() or None
    return None


def normalize_client_mac(value: str | None) -> str | None:
    if not value:
        return None
    mac = value.strip().upper().replace('-', ':')
    if not _MAC_RE.match(mac):
        return None
    return mac


def get_client_user_agent(request) -> str | None:
    raw = (request.META.get('HTTP_USER_AGENT') or '').strip()
    if not raw:
        return None
    return raw[:_USER_AGENT_MAX_LEN]


def _client_mac_from_request(request) -> str | None:
    candidates: list[str] = []
    header_mac = (request.META.get('HTTP_X_CLIENT_MAC') or '').strip()
    if header_mac:
        candidates.append(header_mac)
    if hasattr(request, 'data'):
        body_mac = (request.data.get('client_mac') or '').strip()
        if body_mac:
            candidates.append(body_mac)
    post_mac = (getattr(request, 'POST', None) or {}).get('client_mac', '')
    if post_mac:
        candidates.append(str(post_mac).strip())
    for candidate in candidates:
        normalized = normalize_client_mac(candidate)
        if normalized:
            return normalized
    return None


def apply_request_client_context(audit: 'SigningAuditMeta', request) -> None:
    audit.client_ip = get_client_ip(request)
    audit.user_agent = get_client_user_agent(request)
    audit.client_mac = _client_mac_from_request(request)


@dataclass
class SigningAuditMeta:
    hash_before: str | None = None
    hash_after: str | None = None
    document_type: str | None = None
    detected_keyword: str | None = None
    detection_confidence: str = 'none'
    client_ip: str | None = None
    user_agent: str | None = None
    client_mac: str | None = None
    api_key: APIKey | None = None
    user: User | None = None
    endpoint: str = 'signpdf-pfx'

    def populate_from_pdf(self, pdf_data: bytes) -> None:
        from .document_detection import detect_document_type

        self.hash_before = sha256_hex(pdf_data)
        result = detect_document_type(pdf_data)
        self.document_type = result.document_type
        self.detected_keyword = result.detected_keyword
        self.detection_confidence = result.detection_confidence
