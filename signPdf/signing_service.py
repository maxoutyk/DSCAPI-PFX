from dataclasses import dataclass

import fitz
from endesive import pdf

from accounts.models import UsageLog
from accounts.services import (
    QuotaExceededError,
    ensure_tenant_can_sign,
    get_stored_certificate_bytes,
    record_signing_event,
)

from .audit import SigningAuditMeta, get_client_ip, sha256_hex
from .document_detection import detect_document_type
from .pdf_signing import (
    build_signing_dict,
    find_text_in_pdf,
    get_cn_from_certificate,
    get_indian_time_str,
    load_pfx_credentials,
    read_pfx_file,
    sign_pdf_at_positions,
)
from .signature_style import resolve_signature_style


class SigningFailure(Exception):
    def __init__(self, message: str, *, record_failure: bool = True):
        super().__init__(message)
        self.message = message
        self.record_failure = record_failure


@dataclass
class SigningResult:
    signed_pdf_data: bytes
    signing_event: UsageLog


@dataclass
class PdfAnalysis:
    page_count: int
    signature_slots: int
    anchor_text: str
    document_type_label: str
    ready: bool


def build_audit_for_http_request(request, *, endpoint: str = 'signpdf-pfx', user=None, api_key=None) -> SigningAuditMeta:
    audit = SigningAuditMeta(client_ip=get_client_ip(request), endpoint=endpoint)
    if api_key is not None:
        audit.api_key = api_key
    if user is not None:
        audit.user = user
    return audit


def analyze_pdf_for_signing(pdf_data: bytes, tenant) -> PdfAnalysis:
    style = resolve_signature_style(tenant)
    positions = find_text_in_pdf(pdf_data, style=style)
    detection = detect_document_type(pdf_data)
    from accounts.models import DocumentType

    type_labels = dict(DocumentType.choices)
    label = type_labels.get(detection.document_type, detection.document_type)

    try:
        doc = fitz.open(stream=pdf_data, filetype='pdf')
        page_count = len(doc)
        doc.close()
    except Exception:
        page_count = 0

    return PdfAnalysis(
        page_count=page_count,
        signature_slots=len(positions),
        anchor_text=style.anchor_text,
        document_type_label=label,
        ready=len(positions) > 0,
    )


def sign_pdf_for_tenant(
    *,
    tenant,
    pdf_data: bytes,
    password: str,
    audit: SigningAuditMeta,
    cert_alias: str = '',
    pfx_data: bytes | None = None,
    pfx_path: str = '',
) -> SigningResult:
    ensure_tenant_can_sign(tenant)
    audit.populate_from_pdf(pdf_data)
    signature_style = resolve_signature_style(tenant)

    try:
        if cert_alias:
            pfx_data = get_stored_certificate_bytes(tenant, cert_alias)
        elif pfx_path:
            pfx_data = read_pfx_file(pfx_path)
        elif pfx_data is None:
            raise SigningFailure('Provide a certificate source.')
    except SigningFailure:
        raise
    except Exception as exc:
        if cert_alias:
            raise SigningFailure(f'Certificate not found: {cert_alias}') from exc
        raise SigningFailure(str(exc)) from exc

    try:
        private_key, certificate, additional_certs = load_pfx_credentials(pfx_data, password)
    except ValueError as exc:
        raise SigningFailure(str(exc)) from exc

    text_positions = find_text_in_pdf(pdf_data, style=signature_style)
    if not text_positions:
        raise SigningFailure(
            f"No position found for anchor text: {signature_style.anchor_text!r}",
        )

    indian_time_str, indian_time = get_indian_time_str()
    cn = get_cn_from_certificate(certificate)
    dct = build_signing_dict(cn, indian_time_str, indian_time, style=signature_style)

    try:
        signed_pdf_data = sign_pdf_at_positions(
            pdf_data,
            text_positions,
            dct,
            lambda data, position_dct: pdf.cms.sign(
                data,
                position_dct,
                private_key,
                certificate,
                additional_certs,
                'sha256',
            ),
            style=signature_style,
        )
    except Exception as exc:
        raise SigningFailure(f'Failed to sign PDF: {exc}', record_failure=True) from exc

    audit.hash_after = sha256_hex(signed_pdf_data)
    try:
        signing_event = record_signing_event(tenant, success=True, audit=audit)
    except QuotaExceededError as exc:
        raise SigningFailure(str(exc), record_failure=False) from exc

    return SigningResult(signed_pdf_data=signed_pdf_data, signing_event=signing_event)


def record_signing_failure(tenant, audit: SigningAuditMeta):
    record_signing_event(tenant, success=False, audit=audit)
