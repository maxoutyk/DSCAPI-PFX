"""GST field validation shared by lookup handlers and company profile forms."""

from __future__ import annotations

import re

GSTIN_RE = re.compile(r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$')


def normalize_gstin(value: str) -> str:
    return (value or '').strip().upper()


def is_valid_gstin(value: str) -> bool:
    return bool(GSTIN_RE.match(normalize_gstin(value)))


EWB_NUMBER_RE = re.compile(r'^[0-9]{12}$')
IRN_RE = re.compile(r'^[a-fA-F0-9]{64}$')


def normalize_ewb_number(value: str) -> str:
    return (value or '').strip()


def is_valid_ewb_number(value: str) -> bool:
    return bool(EWB_NUMBER_RE.match(normalize_ewb_number(value)))


def normalize_irn(value: str) -> str:
    return (value or '').strip().lower()


def is_valid_irn(value: str) -> bool:
    return bool(IRN_RE.match(normalize_irn(value)))
