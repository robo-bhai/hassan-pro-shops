"""
License core: signed key -> status (valid / grace / readonly / trial).

Key format:   LIC1.<payload>.<signature>        (payload = base64url JSON, signature = Ed25519 over the payload bytes)
Payload:      {"v":1, "c":"Customer name", "m":"MACHINE-ID or *", "e":"YYYY-MM-DD expiry", "i":"YYYY-MM-DD issued"}

What it does and does not do: a key only works on the machine it was issued for, cannot be edited or
invented without the vendor's private key, and stops working after expiry (+ grace). It cannot stop
someone who edits the application code itself; it raises the bar from "copy the folder and run it
anywhere" to "have to modify the program".

evaluate() and the helpers above it need no Django, so they are easy to test. get_status() is the part
the middleware calls (reads the key file, applies the trial and the clock-rollback guard).
"""
import base64
import hashlib
import json
import os
import platform
import re
import time
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from . import ed25519

PREFIX = 'LIC1'
DEFAULT_GRACE_DAYS = 7
DEFAULT_TRIAL_DAYS = 14
WARN_DAYS = 14                     # show the "expires soon" bar this many days before expiry


# ---------------------------------------------------------------------------------------------- tokens
def _b64e(b):
    return base64.urlsafe_b64encode(b).decode().rstrip('=')


def _b64d(s):
    return base64.urlsafe_b64decode(s + '=' * (-len(s) % 4))


def make_token(secret_seed, customer, machine, expires, issued=None):
    """Vendor side. secret_seed = 32 bytes. machine = 'XXXX-XXXX-XXXX-XXXX' or '*' (any machine)."""
    payload = json.dumps({'v': 1, 'c': customer, 'm': machine or '*', 'e': expires.isoformat(),
                          'i': (issued or date.today()).isoformat()}, separators=(',', ':'), ensure_ascii=False).encode()
    return f'{PREFIX}.{_b64e(payload)}.{_b64e(ed25519.sign(secret_seed, payload))}'


def parse_token(token, public_key):
    """Returns the payload dict if the signature is valid, else None. Never raises."""
    try:
        prefix, body, sig = (token or '').strip().split('.')
        if prefix != PREFIX:
            return None
        payload = _b64d(body)
        if not ed25519.verify(public_key, payload, _b64d(sig)):
            return None
        data = json.loads(payload.decode())
        date.fromisoformat(data['e'])
        return data if data.get('v') == 1 else None
    except Exception:
        return None


# ------------------------------------------------------------------------------------------ machine id
def _read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return ''


def _install_id_file():
    try:
        from django.conf import settings
        base = getattr(settings, 'BASE_DIR', os.getcwd())
    except Exception:
        base = os.getcwd()
    return os.path.join(str(base), '.install_id')


def machine_id():
    """Stable id of this computer, like 'A1B2-C3D4-E5F6-0789'. Built from the OS machine id where one
    exists (Linux, Windows); otherwise a real MAC address; otherwise a random id saved next to the app."""
    raw = _read('/etc/machine-id') or _read('/var/lib/dbus/machine-id')
    if not raw:
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\Cryptography') as k:
                raw = winreg.QueryValueEx(k, 'MachineGuid')[0]
        except Exception:
            raw = ''
    if not raw:
        node = uuid.getnode()
        if not (node >> 40) & 1:                      # multicast bit set = Python made the number up
            raw = f'mac:{node:012x}'
    if not raw:
        path = _install_id_file()
        raw = _read(path)
        if not raw:
            raw = uuid.uuid4().hex
            try:
                with open(path, 'w') as f:
                    f.write(raw)
            except OSError:
                pass
    digest = hashlib.sha256(f'agri-pos|{raw}'.encode()).hexdigest()[:16].upper()
    return '-'.join(digest[i:i + 4] for i in range(0, 16, 4))


# ----------------------------------------------------------------------------------------------- status
@dataclass
class Status:
    state: str            # valid | grace | readonly | trial
    reason: str           # ok | expiring | grace | expired | invalid | wrong_machine | clock | no_license | trial | trial_expired | disabled
    message: str
    customer: str = ''
    expires: date = None
    days_left: int = None  # negative once expired

    @property
    def read_only(self):
        return self.state == 'readonly'

    @property
    def needs_banner(self):
        return self.reason in ('expiring', 'grace', 'expired', 'invalid', 'wrong_machine', 'clock', 'trial', 'trial_expired', 'no_license')


def evaluate(token, public_key, machine, today, grace_days=DEFAULT_GRACE_DAYS):
    """Pure decision: token + this machine + today's date -> Status. No files, no database."""
    data = parse_token(token, public_key)
    if data is None:
        return Status('readonly', 'invalid', 'The license key is not valid. Enter a key issued for this software.')
    if data['m'] not in ('*', machine):
        return Status('readonly', 'wrong_machine', 'This license key was issued for a different computer.', data['c'])
    expires = date.fromisoformat(data['e'])
    left = (expires - today).days
    who = data['c']
    if left >= 0:
        if left <= WARN_DAYS:
            return Status('valid', 'expiring', f'License expires in {left} day(s) on {expires:%d %b %Y}. Please renew.', who, expires, left)
        return Status('valid', 'ok', 'License active.', who, expires, left)
    if -left <= grace_days:
        return Status('grace', 'grace', f'License expired on {expires:%d %b %Y}. Everything still works for {grace_days + left} more day(s) - renew now.',
                      who, expires, left)
    return Status('readonly', 'expired', f'License expired on {expires:%d %b %Y}. The system is read-only: you can view and print, but not add or change records.',
                  who, expires, left)


def license_file():
    from django.conf import settings
    return getattr(settings, 'LICENSE_FILE', None) or os.path.join(str(settings.BASE_DIR), 'license.key')


def public_key_bytes():
    from django.conf import settings
    hexkey = (getattr(settings, 'LICENSE_PUBLIC_KEY', '') or '').strip()
    return bytes.fromhex(hexkey) if hexkey else None


def validate_configuration():
    """Called when the server starts. An empty LICENSE_PUBLIC_KEY means 'licensing off' (development);
    a key that is set but malformed (for example a pasted placeholder) must stop the server instead of
    silently switching the license check off."""
    from django.conf import settings
    from django.core.exceptions import ImproperlyConfigured
    hexkey = (getattr(settings, 'LICENSE_PUBLIC_KEY', '') or '').strip()
    if hexkey and not re.fullmatch(r'[0-9a-fA-F]{64}', hexkey):
        raise ImproperlyConfigured(
            'LICENSE_PUBLIC_KEY in settings.py is not a 64-character hex key. Run "python make_license.py keygen" '
            'and paste the public key it prints (or leave it empty to run without license checks).')


def save_token(token):
    path = license_file()
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        f.write(token.strip())
    os.replace(tmp, path)
    _cache.clear()


def _clock_rolled_back(today):
    """Remember the latest date ever seen; a clock set back before it is treated as tampering."""
    from app.models import License
    row, _ = License.objects.get_or_create(key='last-seen', defaults={'expiry_date': today, 'is_active': False})
    if today > row.expiry_date:
        row.expiry_date = today
        row.save(update_fields=['expiry_date'])
        return False
    return (row.expiry_date - today).days > 1


def _trial_status(today):
    from django.conf import settings
    from app.models import License
    days = getattr(settings, 'LICENSE_TRIAL_DAYS', DEFAULT_TRIAL_DAYS)
    row, _ = License.objects.get_or_create(key='trial-start', defaults={'expiry_date': today + timedelta(days=days), 'is_active': False})
    left = (row.expiry_date - today).days
    if left >= 0:
        return Status('trial', 'trial', f'Trial version: {left} day(s) left. Enter a license key to continue after that.', '', row.expiry_date, left)
    return Status('readonly', 'trial_expired', 'The trial has ended. The system is read-only until a license key is entered.', '', row.expiry_date, left)


_cache = {}


def get_status(today=None):
    """Status of THIS installation right now (cached for a few seconds). Used by the middleware."""
    from django.conf import settings
    public = public_key_bytes()
    if not public:
        return Status('valid', 'disabled', 'License checking is switched off (LICENSE_PUBLIC_KEY is not set).')
    today = today or date.today()
    path = license_file()
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = None
    key = (today, mtime, public)
    hit = _cache.get('s')
    if hit and hit[0] == key and time.time() - hit[1] < 30:
        return hit[2]
    grace = getattr(settings, 'LICENSE_GRACE_DAYS', DEFAULT_GRACE_DAYS)
    if _clock_rolled_back(today):
        status = Status('readonly', 'clock', 'The computer date looks wrong (it is earlier than a date already seen). Correct the date and try again.')
    elif mtime is None:
        status = _trial_status(today)
    else:
        status = evaluate(_read(path), public, machine_id(), today, grace)
    _cache['s'] = (key, time.time(), status)
    return status
