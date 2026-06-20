"""Host machine identifiers for the desktop USB signing agent."""

from __future__ import annotations


def get_primary_mac_address() -> str:
    """Best-effort primary MAC; empty when unavailable or randomised."""
    import uuid

    node = uuid.getnode()
    if (node >> 40) % 2:
        return ''
    return ':'.join(f'{(node >> shift) & 0xff:02X}' for shift in range(40, -1, -8))
