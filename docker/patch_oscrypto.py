"""Patch oscrypto 1.3.0 to detect OpenSSL 3.x versions like 3.0.20."""
import pathlib
import sys

site_packages = pathlib.Path(sys.prefix) / f'lib/python{sys.version_info.major}.{sys.version_info.minor}' / 'site-packages'
target = site_packages / 'oscrypto' / '_openssl' / '_libcrypto_cffi.py'
if not target.exists():
    raise SystemExit(f'oscrypto file missing: {target}')

lines = target.read_text().splitlines()
patched = False
for index, line in enumerate(lines):
    if 'version_match = re.search' in line and 'version_string' in line and '[a-z]' in line:
        lines[index] = "version_match = re.search(r'\\b(\\d+\\.\\d+\\.\\d+[a-z]*)\\b', version_string)"
        patched = True
        break
if not patched:
    matches = [line for line in lines if 'version_match' in line]
    raise SystemExit(f'oscrypto patch target not found in {target}: {matches!r}')
target.write_text('\n'.join(lines) + '\n')
print(f'Patched {target} for OpenSSL 3.x')
