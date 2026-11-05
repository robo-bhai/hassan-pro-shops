"""Language selection (English / Urdu / Arabic): cookie + session, RTL info for templates."""

COOKIE_NAME = 'erp_lang'
DEFAULT_LANG = 'en'

LANGUAGES = [
    {'code': 'en', 'native': 'English', 'dir': 'ltr'},
    {'code': 'ur', 'native': '\u0627\u0631\u062f\u0648', 'dir': 'rtl'},
    {'code': 'ar', 'native': '\u0627\u0644\u0639\u0631\u0628\u064a\u0629', 'dir': 'rtl'},
]
LANGUAGE_CODES = {l['code'] for l in LANGUAGES}


def get_language(request):
    """Current language dict (cookie first, then session, else English)."""
    code = None
    if request is not None:
        code = request.COOKIES.get(COOKIE_NAME)
        if code not in LANGUAGE_CODES:
            session = getattr(request, 'session', None)
            code = session.get(COOKIE_NAME) if session is not None else None
    if code not in LANGUAGE_CODES:
        code = DEFAULT_LANG
    return next(l for l in LANGUAGES if l['code'] == code)
