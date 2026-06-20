"""Redact sensitive field values from log messages."""

from __future__ import annotations

import logging
import re

_SENSITIVE_PATTERNS = (
    re.compile(r'("password"\s*:\s*)"[^"]*"', re.IGNORECASE),
    re.compile(r'("nicPassword"\s*:\s*)"[^"]*"', re.IGNORECASE),
    re.compile(r'("pfx_base64"\s*:\s*)"[^"]{0,200}', re.IGNORECASE),
    re.compile(r'(sign_token=)[^&\s"]+', re.IGNORECASE),
    re.compile(r'(X-Sign-Token:\s*)[^\s]+', re.IGNORECASE),
)


def redact_sensitive_text(text: str) -> str:
    redacted = text
    for pattern in _SENSITIVE_PATTERNS:
        if 'pfx_base64' in pattern.pattern:
            redacted = pattern.sub(r'\1"[REDACTED]"', redacted)
        elif 'sign_token' in pattern.pattern or 'X-Sign-Token' in pattern.pattern:
            redacted = pattern.sub(r'\1[REDACTED]', redacted)
        else:
            redacted = pattern.sub(r'\1"[REDACTED]"', redacted)
    return redacted


class SensitiveDataFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            return True
        redacted = redact_sensitive_text(message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True
