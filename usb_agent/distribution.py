import io
import zipfile
from pathlib import Path

from django.conf import settings

AGENT_DIR = Path(__file__).resolve().parents[1] / 'desktop-agent'
AGENT_RELEASE_INSTALLER = AGENT_DIR / 'releases' / 'IG-E-Sign-Agent-Setup.exe'
PACKAGE_FILES = (
    'agent.py',
    'README.md',
    'VERSION',
    'start-agent.sh',
    'start-agent.bat',
)


def resolve_agent_installer_path() -> Path | None:
    configured = getattr(settings, 'USB_AGENT_INSTALLER_PATH', '').strip()
    if configured:
        path = Path(configured)
        if path.is_file():
            return path
    if AGENT_RELEASE_INSTALLER.is_file():
        return AGENT_RELEASE_INSTALLER
    return None


def read_agent_version() -> str:
    version_file = AGENT_DIR / 'VERSION'
    if version_file.is_file():
        return version_file.read_text().strip() or '0.0.0'
    return getattr(settings, 'USB_AGENT_VERSION', '0.0.0')


def build_agent_zip(*, api_base: str) -> bytes:
    buffer = io.BytesIO()
    version = read_agent_version()
    quickstart = (
        'IG E-Sign USB Agent\n'
        f'Version: {version}\n\n'
        f'Portal: {api_base}\n\n'
        '1. Windows: double-click start-agent.bat\n'
        '2. macOS/Linux: chmod +x start-agent.sh && ./start-agent.sh\n'
        '3. In the portal go to USB Agent → Generate pairing code\n'
        '4. Enter the code when the launcher prompts you\n'
        '5. Use USB Sign in the portal to sign PDFs\n\n'
        'Dev signing (until PKCS#11 USB support ships):\n'
        '  Set IG_AGENT_DEV_PFX_PATH and IG_AGENT_DEV_PFX_PASSWORD before starting.\n'
    )
    portal_url = f'api_base={api_base.rstrip("/")}\n'

    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name in PACKAGE_FILES:
            path = AGENT_DIR / name
            if path.is_file():
                archive.write(path, arcname=f'ig-esign-agent/{name}')
        archive.writestr('ig-esign-agent/QUICKSTART.txt', quickstart)
        archive.writestr('ig-esign-agent/portal.url', portal_url)

    return buffer.getvalue()


def agent_zip_filename(version: str | None = None) -> str:
    version = version or read_agent_version()
    safe_version = version.replace('/', '-')
    return f'ig-esign-agent-{safe_version}.zip'
