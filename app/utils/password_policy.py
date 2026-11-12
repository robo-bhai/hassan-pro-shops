"""Customer / vendor / rider ke password ke qaide (staff ka policy security/admin_reset.py mein)."""
import re

from django.conf import settings
from django.contrib.auth.password_validation import CommonPasswordValidator
from django.core.exceptions import ValidationError

MIN_LENGTH = int(getattr(settings, 'PORTAL_PASSWORD_MIN_LENGTH', 8))
_common = CommonPasswordValidator()


def password_errors(password, hints=()):
    """Errors ki list (khali = password theek). `hints` = naam/phone/username jaisi cheezen jo password mein na hon."""
    pw = password or ''
    errors = []
    if len(pw) < MIN_LENGTH:
        errors.append(f'Password kam az kam {MIN_LENGTH} characters ka ho.')
    if len(pw) > 128:
        errors.append('Password 128 characters se lamba na ho.')
    if pw and not (re.search(r'[A-Za-z]', pw) and re.search(r'\d', pw)):
        errors.append('Password mein kam az kam ek harf aur ek number ho.')
    if pw and len(set(pw)) <= 2:
        errors.append('Password mein sirf ek-do characters dohraye na hon.')
    try:
        _common.validate(pw)
    except ValidationError:
        errors.append('Yeh password bohat aam hai, koi mushkil password chunein.')
    low = pw.lower()
    for h in hints:
        h = str(h or '').strip().lower()
        if len(h) >= 4 and h in low:
            errors.append('Password mein apna naam, phone ya username na ho.')
            break
    return errors
