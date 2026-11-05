#!/usr/bin/env python3
"""Builds a CLEAN zip for a customer from your working folder (run it from your computer, not the customer's):

    python deploy/make_package.py            ->  ../customer_package_YYYYMMDD.zip

Leaves out secrets and junk (.env, databases, license files, vendor tools, logs, backups, *.bak*, caches) and
refuses to build if the project is incomplete or the license public key is not filled in."""
import fnmatch
import os
import re
import sys
import zipfile
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REQUIRED = ['manage.py', 'requirements.txt', 'P1/settings.py', 'P1/urls.py', 'P1/wsgi.py', 'app', 'ceo_module', 'templates', 'static', 'deploy']
EXCLUDE_DIRS = {'__pycache__', '.git', 'venv', '.venv', 'logs', 'dbbackup', '_backups', 'django_cache', 'staticfiles', 'media',
                'wheelhouse', 'node_modules', '.idea', '.vscode'}
EXCLUDE_FILES = ['.env', '.env.*', 'db.sqlite3*', '*.sqlite3', 'license.key', 'license_private.key', 'make_license.py',
                 '.install_id', '*.pyc', '*.bak', '*.bak_*', '*.bad', '*.orig', '*.log', '*.zip', '.DS_Store']
KEEP = {'.env.example'}


def skip(name):
    return name not in KEEP and any(fnmatch.fnmatch(name, p) for p in EXCLUDE_FILES)


def problems():
    out = [f'missing: {p}' for p in REQUIRED if not os.path.exists(os.path.join(ROOT, p))]
    settings = os.path.join(ROOT, 'P1', 'settings.py')
    if os.path.exists(settings):
        text = open(settings, encoding='utf-8').read()
        m = re.search(r"^LICENSE_PUBLIC_KEY\s*=\s*'([^']*)'", text, re.M)
        if not m or not re.fullmatch(r'[0-9a-fA-F]{64}', m.group(1)):
            out.append("P1/settings.py: LICENSE_PUBLIC_KEY is empty or not a 64-character hex key (run make_license.py keygen)")
    return out


def main():
    bad = problems()
    if bad:
        print('Cannot build the package:\n  - ' + '\n  - '.join(bad))
        sys.exit(1)
    target = os.path.join(os.path.dirname(ROOT), f'customer_package_{date.today():%Y%m%d}.zip')
    count = 0
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as z:
        for folder, dirs, files in os.walk(ROOT):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for name in files:
                if not skip(name):
                    full = os.path.join(folder, name)
                    z.write(full, os.path.relpath(full, ROOT))
                    count += 1
    print(f'{count} files -> {target}')


if __name__ == '__main__':
    main()
