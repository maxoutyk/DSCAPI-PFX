"""Entry point for the Windows DSCAPI-PFX executable."""
import os
import sys
from pathlib import Path


def _app_dir() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parents[2]


def main():
    app_dir = _app_dir()
    os.chdir(app_dir)
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'DSCApi.settings')

    (app_dir / 'certs').mkdir(exist_ok=True)

    from django.core.management import execute_from_command_line

    execute_from_command_line(['launcher', 'migrate', '--noinput'])

    from waitress import serve
    from DSCApi.wsgi import application

    host = os.environ.get('DSCAPI_HOST', '0.0.0.0')
    port = int(os.environ.get('DSCAPI_PORT', '8080'))
    print(f'DSCAPI-PFX listening on port {port} (all interfaces: {host})')
    print('Local:  http://127.0.0.1:{0}/api/signpdf-pfx'.format(port))
    print('LAN:    http://<your-ip>:{0}/api/signpdf-pfx'.format(port))
    print('Allow port {0} in Windows Firewall if other PCs cannot connect.'.format(port))
    serve(application, host=host, port=port)


if __name__ == '__main__':
    main()
