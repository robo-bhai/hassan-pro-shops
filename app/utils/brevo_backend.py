"""Django email backend jo Brevo ki HTTP API (v3/smtp/email) se email bhejta hai.

Settings (P1/settings.py) in environment variables se bharti hain (GitHub Secrets / .env):
    BREVO_API_KEY, BREVO_SENDER_NAME, BREVO_SENDER_EMAIL
API key kabhi log ya error message mein nahi likhi jati.
"""
import base64
import json
import logging
import urllib.error
import urllib.request
from email.utils import parseaddr

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)

BREVO_URL = 'https://api.brevo.com/v3/smtp/email'
TIMEOUT_SECONDS = 15


def _addr(value):
    name, email = parseaddr(value or '')
    d = {'email': email}
    if name:
        d['name'] = name
    return d


def build_payload(message, sender_name, sender_email):
    """EmailMessage -> Brevo JSON body (dict)."""
    sender = {'email': sender_email}
    if sender_name:
        sender['name'] = sender_name

    payload = {
        'sender': sender,
        'to': [_addr(a) for a in message.to],
        'subject': message.subject or '(no subject)',
    }
    if message.cc:
        payload['cc'] = [_addr(a) for a in message.cc]
    if message.bcc:
        payload['bcc'] = [_addr(a) for a in message.bcc]
    if message.reply_to:
        payload['replyTo'] = _addr(message.reply_to[0])

    html = None
    for content, mimetype in (getattr(message, 'alternatives', None) or []):
        if mimetype == 'text/html':
            html = content
    if html:
        payload['htmlContent'] = html
        if message.body:
            payload['textContent'] = message.body
    elif getattr(message, 'content_subtype', 'plain') == 'html':
        payload['htmlContent'] = message.body or ' '
    else:
        payload['textContent'] = message.body or ' '

    attachments = []
    for att in (getattr(message, 'attachments', None) or []):
        if isinstance(att, (tuple, list)) and len(att) >= 2:
            filename, content = att[0], att[1]
            if isinstance(content, str):
                content = content.encode('utf-8')
            attachments.append({'name': filename or 'file',
                                'content': base64.b64encode(content).decode('ascii')})
    if attachments:
        payload['attachment'] = attachments
    return payload


class BrevoAPIEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        api_key = getattr(settings, 'BREVO_API_KEY', '')
        sender_email = getattr(settings, 'BREVO_SENDER_EMAIL', '')
        sender_name = getattr(settings, 'BREVO_SENDER_NAME', '')
        if not api_key or not sender_email:
            if self.fail_silently:
                return 0
            raise ImproperlyConfigured(
                'BREVO_API_KEY aur BREVO_SENDER_EMAIL set nahi hain (GitHub Secret / .env).')

        sent = 0
        for message in email_messages:
            if not message.to:
                continue
            body = json.dumps(build_payload(message, sender_name, sender_email)).encode('utf-8')
            req = urllib.request.Request(
                BREVO_URL, data=body, method='POST',
                headers={'accept': 'application/json',
                         'content-type': 'application/json',
                         'api-key': api_key})
            try:
                with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
                    if 200 <= resp.status < 300:
                        sent += 1
            except urllib.error.HTTPError as e:
                detail = e.read().decode('utf-8', 'replace')[:300]
                logger.error('Brevo API error %s: %s', e.code, detail)
                if not self.fail_silently:
                    raise
            except Exception as e:
                logger.error('Brevo API request failed: %s', e)
                if not self.fail_silently:
                    raise
        return sent
