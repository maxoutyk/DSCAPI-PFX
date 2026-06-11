import hashlib
from dataclasses import dataclass

from django.contrib.auth.models import User

from accounts.models import APIKey


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def get_client_ip(request) -> str | None:
    forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip() or None
    return request.META.get('REMOTE_ADDR')


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
