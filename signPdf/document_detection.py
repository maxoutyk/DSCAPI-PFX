import re
from dataclasses import dataclass

import fitz

from accounts.models import DocumentType

# Longer phrases first when flattened for scanning.
DOCUMENT_TYPE_KEYWORDS: list[tuple[str, list[str]]] = [
    (DocumentType.TAX_INVOICE, ['TAX INVOICE NUMBER', 'TAX INVOICE NO', 'TAX INVOICE']),
    (DocumentType.PURCHASE_ORDER, ['PURCHASE ORDER', 'PO NUMBER', 'PO NO', 'P.O.']),
    (DocumentType.DELIVERY_CHALLAN, ['DELIVERY CHALLAN NO', 'DELIVERY CHALLAN']),
    (DocumentType.CREDIT_NOTE, ['CREDIT NOTE NO', 'CREDIT NOTE']),
    (DocumentType.DEBIT_NOTE, ['DEBIT NOTE NO', 'DEBIT NOTE']),
    (DocumentType.PROFORMA_INVOICE, ['PRO FORMA INVOICE', 'PROFORMA INVOICE']),
    (DocumentType.QUOTATION, ['QUOTATION NO', 'QUOTE NO', 'QUOTATION']),
]


@dataclass(frozen=True)
class DocumentDetectionResult:
    document_type: str
    detected_keyword: str | None
    detection_confidence: str


def extract_pdf_text(pdf_data: bytes) -> str:
    try:
        doc = fitz.open(stream=pdf_data, filetype='pdf')
    except Exception:
        return ''

    parts = []
    for page_num in range(len(doc)):
        parts.append(doc.load_page(page_num).get_text())
    doc.close()
    return '\n'.join(parts)


def normalize_pdf_text(text: str) -> str:
    return re.sub(r'\s+', ' ', text.upper()).strip()


def detect_document_type(pdf_data: bytes) -> DocumentDetectionResult:
    normalized = normalize_pdf_text(extract_pdf_text(pdf_data))
    if not normalized:
        return DocumentDetectionResult(
            document_type=DocumentType.UNKNOWN,
            detected_keyword=None,
            detection_confidence='none',
        )

    matched_types: list[str] = []
    matches_by_type: dict[str, list[str]] = {}

    for doc_type, keywords in DOCUMENT_TYPE_KEYWORDS:
        type_matches = [keyword for keyword in sorted(keywords, key=len, reverse=True) if keyword in normalized]
        if type_matches:
            matched_types.append(doc_type)
            matches_by_type[doc_type] = type_matches

    if not matched_types:
        return DocumentDetectionResult(
            document_type=DocumentType.UNKNOWN,
            detected_keyword=None,
            detection_confidence='none',
        )

    winner_type = matched_types[0]
    winner_keyword = matches_by_type[winner_type][0]
    confidence = 'low' if len(matched_types) > 1 else 'high'
    return DocumentDetectionResult(
        document_type=winner_type,
        detected_keyword=winner_keyword,
        detection_confidence=confidence,
    )
