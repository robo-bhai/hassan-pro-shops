"""WhatsApp par OTP code bhejna (WhatsApp Business Cloud API, Meta).

Purana whatsapp_utils.py sirf wa.me links banata hai (insaan khud bhejta hai) -- OTP ke liye kaam nahi aata.
Settings (.env -> settings.py):
    WHATSAPP_PHONE_NUMBER_ID   Meta -> WhatsApp -> API Setup
    WHATSAPP_ACCESS_TOKEN      permanent (System User) token
    WHATSAPP_OTP_TEMPLATE      approved *Authentication* template ka naam ({{1}} = code, "Copy code" button)
    WHATSAPP_TEMPLATE_LANG     template ki language (default en)
    WHATSAPP_API_VERSION       optional (default v21.0)
    WHATSAPP_NOTICE_TEMPLATE   optional: approved *Utility* template (body mein koi {{variable}} nahi)
Settings na hon to is_configured() False hota hai aur kuch nahi bheja jata.
"""
import json
import logging
import urllib.error
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

TIMEOUT = 8  # seconds


def _cfg(name, default=''):
    return getattr(settings, name, '') or default


def is_configured():
    return bool(_cfg('WHATSAPP_PHONE_NUMBER_ID') and _cfg('WHATSAPP_ACCESS_TOKEN') and _cfg('WHATSAPP_OTP_TEMPLATE'))


def to_international(phone):
    """03001234567 / +923001234567 -> 923001234567 (Meta ko sirf digits, country code ke saath chahiye)."""
    digits = ''.join(ch for ch in str(phone or '') if ch.isdigit())
    if digits.startswith('00'):
        digits = digits[2:]
    if digits.startswith('0'):
        digits = '92' + digits[1:]
    elif not digits.startswith('92') and len(digits) == 10:
        digits = '92' + digits
    return digits


def send_otp(phone, code):
    """Return (ok, error_text). Token kabhi log nahi hota."""
    if not is_configured():
        return False, 'whatsapp not configured'
    to = to_international(phone)
    if len(to) < 11:
        return False, 'invalid phone'
    payload = {
        'messaging_product': 'whatsapp',
        'to': to,
        'type': 'template',
        'template': {
            'name': _cfg('WHATSAPP_OTP_TEMPLATE'),
            'language': {'code': _cfg('WHATSAPP_TEMPLATE_LANG', 'en')},
            'components': [
                {'type': 'body', 'parameters': [{'type': 'text', 'text': str(code)}]},
                {'type': 'button', 'sub_type': 'url', 'index': '0',
                 'parameters': [{'type': 'text', 'text': str(code)}]},
            ],
        },
    }
    return _post(payload)


def _post(payload):
    url = 'https://graph.facebook.com/{}/{}/messages'.format(
        _cfg('WHATSAPP_API_VERSION', 'v21.0'), _cfg('WHATSAPP_PHONE_NUMBER_ID'))
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode('utf-8'), method='POST',
        headers={'Authorization': 'Bearer ' + _cfg('WHATSAPP_ACCESS_TOKEN'),
                 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return (200 <= resp.status < 300), ''
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode('utf-8')).get('error', {}).get('message', '')
        except Exception:
            detail = ''
        logger.warning('WhatsApp OTP HTTP %s: %s', exc.code, detail[:200])
        return False, detail or f'http {exc.code}'
    except Exception as exc:
        logger.warning('WhatsApp OTP failed: %s', exc)
        return False, str(exc)


def send_notice(phone):
    """'Password badal gaya' ki ittela. Sirf tab jab WHATSAPP_NOTICE_TEMPLATE set ho. Return (ok, error)."""
    template = _cfg('WHATSAPP_NOTICE_TEMPLATE')
    if not (template and _cfg('WHATSAPP_PHONE_NUMBER_ID') and _cfg('WHATSAPP_ACCESS_TOKEN')):
        return False, 'notice template not configured'
    to = to_international(phone)
    if len(to) < 11:
        return False, 'invalid phone'
    payload = {'messaging_product': 'whatsapp', 'to': to, 'type': 'template',
               'template': {'name': template, 'language': {'code': _cfg('WHATSAPP_TEMPLATE_LANG', 'en')}}}
    return _post(payload)
