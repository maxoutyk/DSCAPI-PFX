"""PyInstaller entry point for IG E-Sign USB Agent."""

import os
import sys
from pathlib import Path

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'agent_settings')

root = Path(__file__).resolve().parents[2]
agent_dir = root / 'desktop-agent'
for path in (str(root), str(agent_dir)):
    if path not in sys.path:
        sys.path.insert(0, path)

from agent import main  # noqa: E402

if __name__ == '__main__':
    main()
