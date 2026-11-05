#!/usr/bin/env python3
"""
One-time setup for a customer install. Run from the project folder with the virtual environment active
(install_windows.bat / install_linux.sh do all of this for you):

    python deploy/setup_install.py            # .env, database, static files, admin user, checks
    python deploy/setup_install.py --no-superuser

Safe to run again: it never overwrites an existing .env or touches existing data (migrate only adds).
"""
import argparse
import importlib.util
import os
import secrets
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def new_env_text():
    return (
        '# Written by deploy/setup_install.py - keep this file private and back it up.\n'
        'DEBUG=False\n'
        f'DJANGO_SECRET_KEY={secrets.token_urlsafe(64)}\n'
        f'DJANGO_SALT_KEY={secrets.token_urlsafe(32)}\n'
        'ALLOWED_HOSTS=\nCSRF_TRUSTED_ORIGINS=\nHTTPS=false\nBEHIND_PROXY=false\nMEDIA_STORAGE=local\n'
    )


def ensure_env(path):
    """Create .env with random secrets. Returns True if it was created, False if one already existed."""
    if os.path.exists(path):
        return False
    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_env_text())
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return True


def manage(*args, check=True):
    return subprocess.run([sys.executable, os.path.join(ROOT, 'manage.py'), *args], cwd=ROOT, check=check)


def machine_id():
    pkg_dir = os.path.join(ROOT, 'app', 'licensing')
    try:
        spec = importlib.util.spec_from_file_location('licensing', os.path.join(pkg_dir, '__init__.py'), submodule_search_locations=[pkg_dir])
        pkg = importlib.util.module_from_spec(spec)
        sys.modules['licensing'] = pkg
        spec.loader.exec_module(pkg)
        return importlib.import_module('licensing.core').machine_id()
    except Exception as exc:                                        # never block the install on this
        return f'(could not read: {exc})'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--no-superuser', action='store_true')
    args = ap.parse_args()
    if sys.version_info < (3, 10):
        sys.exit('Python 3.10 or newer is required.')
    for needed in ('manage.py', 'P1', 'app'):
        if not os.path.exists(os.path.join(ROOT, needed)):
            sys.exit(f'Missing "{needed}" in {ROOT}. The customer package must contain manage.py, P1/, app/, ceo_module/, templates/ and static/.')

    print('1/5  .env file')
    print('     created with new random secret keys' if ensure_env(os.path.join(ROOT, '.env')) else '     already exists - left unchanged')
    print('2/5  database')
    manage('migrate', '--noinput')
    print('3/5  static files')
    manage('collectstatic', '--noinput', '-v', '0')
    print('4/5  administrator account')
    if args.no_superuser:
        print('     skipped')
    else:
        manage('createsuperuser')
    print('5/5  security check (anything listed here should be read, not ignored)')
    manage('check', '--deploy', check=False)

    print('\n' + '=' * 62)
    print(' Install finished.')
    print(f' This computer\'s ID for the license key:  {machine_id()}')
    print(' Start the server:  Windows: deploy\\start_server.bat   Linux: deploy/start_server.sh')
    print('=' * 62)


if __name__ == '__main__':
    main()
