from pathlib import Path

from django.conf import settings

AGENT_DIR = Path(__file__).resolve().parents[1] / 'desktop-agent'
DEFAULT_MICROSOFT_STORE_AGENT_URL = (
    'https://apps.microsoft.com/store/detail/9MSNF2CD9JTC?cid=DevShareMCLPCS'
)


def read_agent_version() -> str:
    version_file = AGENT_DIR / 'VERSION'
    if version_file.is_file():
        return version_file.read_text().strip() or '0.0.0'
    return getattr(settings, 'USB_AGENT_VERSION', '0.0.0')


def compare_agent_versions(left: str, right: str) -> int:
    """Return -1 if left < right, 0 if equal, 1 if left > right."""

    def _parts(value: str) -> list[int]:
        chunks: list[int] = []
        for piece in (value or '0').strip().split('.'):
            digits = ''.join(ch for ch in piece if ch.isdigit())
            chunks.append(int(digits or '0'))
        return chunks or [0]

    left_parts = _parts(left)
    right_parts = _parts(right)
    width = max(len(left_parts), len(right_parts))
    left_parts.extend([0] * (width - len(left_parts)))
    right_parts.extend([0] * (width - len(right_parts)))
    if left_parts < right_parts:
        return -1
    if left_parts > right_parts:
        return 1
    return 0


def microsoft_store_agent_url() -> str:
    configured = getattr(settings, 'USB_AGENT_MICROSOFT_STORE_URL', '').strip()
    return configured or DEFAULT_MICROSOFT_STORE_AGENT_URL
