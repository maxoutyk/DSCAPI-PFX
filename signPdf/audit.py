import hashlib
from dataclasses import dataclass

from django.contrib.auth.models import User

from accounts.models import APIKey


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
    """Resolve the external client IP from proxy headers, skipping loopback hops."""
    forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded_for:
        forwarded_ips = [part.strip() for part in forwarded_for.split(',') if part.strip()]
        usable = _first_usable_ip(*forwarded_ips)
        if usable:
            return usable

    x_real_ip = request.META.get('HTTP_X_REAL_IP')
    usable = _first_usable_ip(x_real_ip)
    if usable:
        return usable

    remote_addr = request.META.get('REMOTE_ADDR')
    if remote_addr:
        return remote_addr.strip() or None
    return None


@dataclass
class SigningAuditMeta:
    hash_before: str | None = None
    hash_after: str | None = None
    document_type: str | None = None
    detected_keyword: str | None = None
    detection_confidence: str = 'none'
    client_ip: str | None = None
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
