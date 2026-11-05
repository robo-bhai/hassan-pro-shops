#!/usr/bin/env python3
"""Runs the site with waitress (works the same on Windows and Linux).   python deploy/run_server.py
Environment: PORT (default 8000), THREADS (default 8). Reach it from other computers at http://<this-computer-ip>:PORT"""
import os
import socket
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'P1.settings')

from waitress import serve                       # noqa: E402
from P1.wsgi import application                  # noqa: E402


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('10.255.255.255', 1))         # no packet is sent; just picks the outgoing interface
        return s.getsockname()[0]
    except Exception:
        return '127.0.0.1'


if __name__ == '__main__':
    port = int(os.environ.get('PORT', '8000'))
    print(f'Open on this computer:  http://localhost:{port}\nOpen from other computers: http://{lan_ip()}:{port}\nCtrl+C to stop.')
    try:
        serve(application, host='0.0.0.0', port=port, threads=int(os.environ.get('THREADS', '8')))
    except OSError as exc:
        if exc.errno in (98, 48, 10048):               # Linux/Android, macOS, Windows: address already in use
            sys.exit(f'Port {port} is already in use - another copy of the server is running. Close it, '
                     f'or use another port:  PORT=8001 python deploy/run_server.py')
        raise
