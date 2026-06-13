"""Runtime helpers for the frozen (windowed) Windows agent."""

from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path


def prepare_windowed_runtime() -> None:
    """PyInstaller windowed builds set stdout/stderr to None; fix before signing."""
    if not getattr(sys, 'frozen', False):
        return

    log_path = Path.home() / '.ig-esign-agent' / 'agent.log'
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = log_path.open('a', encoding='utf-8', errors='replace')

    if sys.stdout is None:
        sys.stdout = log_file
    if sys.stderr is None:
        sys.stderr = log_file

    os.environ.setdefault('PYTHONWARNINGS', 'ignore')
    warnings.simplefilter('ignore')
