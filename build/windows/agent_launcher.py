"""PyInstaller entry point for IG E-Sign USB Agent."""

import os
import sys
import traceback
from pathlib import Path

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'agent_settings')

if getattr(sys, 'frozen', False):
    bundle = Path(getattr(sys, '_MEIPASS', Path(sys.executable).parent))
    for path in (str(bundle),):
        if path not in sys.path:
            sys.path.insert(0, path)
else:
    root = Path(__file__).resolve().parents[2]
    agent_dir = root / 'desktop-agent'
    for path in (str(root), str(agent_dir)):
        if path not in sys.path:
            sys.path.insert(0, path)

from runtime import prepare_windowed_runtime  # noqa: E402

prepare_windowed_runtime()

from agent import main  # noqa: E402


def _pause_on_windows():
    if sys.platform != 'win32':
        return
    if getattr(sys, 'frozen', False):
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(
                0,
                'The agent exited due to an error. Check %USERPROFILE%\\.ig-esign-agent\\agent.log',
                'IG E-Sign Agent',
                0x10,
            )
        except Exception:
            pass
        return
    try:
        input('\nPress Enter to exit...')
    except (EOFError, RuntimeError):
        pass


if __name__ == '__main__':
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        _pause_on_windows()
        sys.exit(1)
